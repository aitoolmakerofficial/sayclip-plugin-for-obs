from pathlib import Path
import importlib.util
import ctypes
import sys
import threading
from types import SimpleNamespace

import pytest


def load_guard():
    path = Path(__file__).resolve().parents[1] / "src/obs/microphone_guard.py"
    spec = importlib.util.spec_from_file_location("guard_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Alarm:
    def __init__(self):
        self.active = False
        self.closed = False

    def set_active(self, value):
        self.active = value

    def close(self):
        self.closed = True


class Meter:
    def __init__(self, *args):
        self.signal_at = None
        self.error = None
        self.closed = False

    def sample(self, tracks):
        if tracks == 0:
            return None, None, "Microphone is not assigned to a recorded audio track"
        return self.signal_at, -20.0 if self.signal_at is not None else None, self.error

    def close(self):
        self.closed = True


def make_guard(config=None):
    module = load_guard()
    clock = [0.0]
    alarm = Alarm()
    notices = []
    meters = []

    def factory(*args):
        meter = Meter()
        meters.append(meter)
        return meter

    guard = module.MicrophoneGuard(config or {}, notices.append, factory, alarm, lambda: clock[0])
    return guard, clock, alarm, notices, meters


def test_thirty_seconds_of_silence_from_start_triggers_persistent_alarm():
    guard, clock, alarm, notices, meters = make_guard()
    guard.tick(True, False, 3)
    clock[0] = 29.99
    guard.tick(True, False, 3)
    assert not alarm.active
    clock[0] = 30.0
    guard.tick(True, False, 3)
    assert alarm.active
    assert guard.payload["state"] == "alarm"
    assert notices[-1]["alarm"] is True
    clock[0] = 120
    guard.tick(True, False, 3)
    assert alarm.active
    assert len(notices) == 1  # No log/banner spam while the sound repeats.


def test_brief_signal_resets_timer_and_alarm_can_recur_later():
    guard, clock, alarm, notices, meters = make_guard()
    guard.tick(True, False, 3)
    clock[0] = 25
    meters[0].signal_at = 24.9  # A short sound between timer ticks must count.
    guard.tick(True, False, 3)
    clock[0] = 54.8
    guard.tick(True, False, 3)
    assert not alarm.active
    clock[0] = 55
    guard.tick(True, False, 3)
    assert alarm.active
    meters[0].signal_at = 55
    guard.tick(True, False, 3)
    assert not alarm.active
    assert notices[-1]["alarm"] is False
    clock[0] = 85
    guard.tick(True, False, 3)
    assert alarm.active


@pytest.mark.parametrize("recording,paused", [(False, False), (True, True)])
def test_stop_and_pause_silence_alarm_and_resume_with_fresh_timeout(recording, paused):
    guard, clock, alarm, notices, meters = make_guard()
    guard.tick(True, False, 3)
    clock[0] = 30
    guard.tick(True, False, 3)
    assert alarm.active
    guard.tick(recording, paused, 3)
    assert not alarm.active
    assert meters[0].closed
    clock[0] = 100
    guard.tick(True, False, 3)
    assert not alarm.active
    clock[0] = 129.9
    guard.tick(True, False, 3)
    assert not alarm.active
    clock[0] = 130
    guard.tick(True, False, 3)
    assert alarm.active


def test_missing_recording_route_does_not_allow_input_signal_to_hide_alarm():
    guard, clock, alarm, notices, meters = make_guard()
    guard.tick(True, False, 0)
    clock[0] = 30
    meters[0].signal_at = 30
    guard.tick(True, False, 0)
    assert alarm.active
    assert "recorded audio track" in guard.payload["message"]


@pytest.mark.parametrize("error", ["Microphone is muted in OBS", "No audio updates from microphone"])
def test_unusable_source_cannot_report_healthy_signal(error):
    guard, clock, alarm, notices, meters = make_guard()
    guard.tick(True, False, 3)
    clock[0] = 30
    meters[0].signal_at = 30
    meters[0].error = error
    guard.tick(True, False, 3)
    assert alarm.active
    assert error in guard.payload["message"]


def test_meter_initialization_failure_alarms_and_recovers_on_retry():
    guard, clock, alarm, notices, meters = make_guard()
    working_factory = guard.meter_factory

    def broken(*args):
        raise RuntimeError("meter unavailable")

    guard.meter_factory = broken
    guard.tick(True, False, 3)
    clock[0] = 30
    guard.tick(True, False, 3)
    assert alarm.active
    assert "meter unavailable" in guard.payload["message"]
    guard.meter_factory = working_factory
    clock[0] = 31
    guard.tick(True, False, 3)
    meters[0].signal_at = 31
    guard.tick(True, False, 3)
    assert not alarm.active


def test_custom_timeout_and_close():
    guard, clock, alarm, notices, meters = make_guard({"silence_seconds": 7})
    guard.tick(True, False, 3)
    clock[0] = 7
    guard.tick(True, False, 3)
    assert alarm.active
    guard.close()
    assert alarm.closed
    assert meters[0].closed


def test_explicitly_disabled_guard_does_not_open_meter_or_alarm():
    guard, clock, alarm, notices, meters = make_guard({"enabled": False})
    guard.tick(True, False, 3)
    clock[0] = 300
    guard.tick(True, False, 3)
    assert not meters
    assert not alarm.active
    assert guard.payload["state"] == "disabled"


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_timeout_rejected(timeout):
    with pytest.raises(ValueError):
        make_guard({"silence_seconds": timeout})


def test_repeating_alarm_repeats_until_cleared_without_blocking_caller(monkeypatch):
    module = load_guard()
    tones = []
    repeated = threading.Event()

    def beep(frequency, duration):
        tones.append((frequency, duration))
        if len(tones) >= 4:
            repeated.set()

    monkeypatch.setitem(sys.modules, "winsound", SimpleNamespace(Beep=beep))
    alarm = module.RepeatingAlarm()
    try:
        alarm.set_active(True)
        assert repeated.wait(2)
        alarm.set_active(False)
        count = len(tones)
        assert not threading.Event().wait(0.3)
        assert len(tones) == count
        assert [frequency for frequency, duration in tones[:4]] == [1800, 900, 1800, 900]
    finally:
        alarm.close()
    assert not alarm.thread.is_alive()


def test_native_meter_reads_post_fader_peaks_and_owns_source_until_detach(monkeypatch):
    module = load_guard()
    clock = [0.0]
    refs = [0]
    events = []

    class Function:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    def acquire(*args):
        refs[0] += 1
        return 42

    def release(*args):
        refs[0] -= 1

    functions = {
        "obs_get_source_by_name": acquire,
        "obs_source_get_ref": acquire,
        "obs_source_release": release,
        "obs_source_muted": lambda source: False,
        "obs_source_active": lambda source: True,
        "obs_source_get_audio_mixers": lambda source: 2,
        "obs_source_get_monitoring_type": lambda source: 0,
        "obs_volmeter_create": lambda kind: 100,
        "obs_volmeter_attach_source": lambda meter, source: True,
        "obs_volmeter_add_callback": lambda *args: events.append("add"),
        "obs_volmeter_remove_callback": lambda *args: events.append("remove"),
        "obs_volmeter_destroy": lambda *args: events.append("destroy"),
    }
    lib = SimpleNamespace(**{name: Function(callback) for name, callback in functions.items()})
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(module.ctypes, "CDLL", lambda name: lib)
    meter = module.ObsSourceMeter("Mic/Aux", -60)
    try:
        assert meter.sample(3)[2] == "No audio updates from microphone"
        assert refs[0] == 1
        silence = (ctypes.c_float * 8)(*([-float("inf")] * 8))
        signal = (ctypes.c_float * 8)(-float("inf"), -20, *([-float("inf")] * 6))
        clock[0] = 1
        meter.callback(None, silence, signal, silence)  # Ignore the pre-fader input peak.
        assert meter.sample(3) == (1, -20, None)
        clock[0] = 2
        meter.callback(None, silence, silence, signal)
        assert meter.sample(3) == (1, None, None)
        assert "recorded audio track" in meter.sample(1)[2]
        clock[0] = 5
        assert meter.sample(3)[2] == "No audio updates from microphone"
    finally:
        meter.close()
    assert refs[0] == 0
    assert events == ["add", "remove", "destroy"]
