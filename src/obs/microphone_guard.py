# SPDX-License-Identifier: GPL-2.0-or-later
"""Recording microphone watchdog. Runs in OBS, without backend dependencies."""
from __future__ import annotations

import ctypes
import logging
import math
import sys
import threading
import time


logger = logging.getLogger(__name__)


class SilenceWatch:
    def __init__(self, timeout_seconds=30.0):
        self.timeout = float(timeout_seconds)
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("Microphone silence_seconds must be a positive finite number")
        self.started_at = None
        self.last_signal_at = None

    def update(self, now, recording, paused, signal_at=None):
        if not recording or paused:
            self.started_at = self.last_signal_at = None
            return False, 0.0
        if self.started_at is None:
            self.started_at = self.last_signal_at = now
        if signal_at is not None and self.started_at <= signal_at <= now:
            self.last_signal_at = max(self.last_signal_at, signal_at)
        silent_for = max(0.0, now - self.last_signal_at)
        return silent_for >= self.timeout, silent_for


class RepeatingAlarm:
    """Play short alternating tones on a worker, never on OBS's UI/audio thread."""
    def __init__(self):
        self.active = threading.Event()
        self.closed = threading.Event()
        self.thread = None

    def set_active(self, active):
        if active:
            self.active.set()
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, name="SayClip mic alarm", daemon=True)
                self.thread.start()
        else:
            self.active.clear()

    def _run(self):
        while not self.closed.is_set():
            if not self.active.wait(0.1):
                continue
            for frequency in (1800, 900):
                if self.closed.is_set() or not self.active.is_set():
                    break
                try:
                    import winsound
                    winsound.Beep(frequency, 180)
                except Exception:
                    logger.exception("Could not play microphone alarm")
                    self.closed.wait(1.0)
                    break
            self.closed.wait(0.15)

    def close(self):
        self.closed.set()
        self.active.set()
        if self.thread is not None:
            self.thread.join(timeout=1.0)


class ObsSourceMeter:
    """Use libobs's actual post-fader meter, not a separate microphone capture.

    Python scripting does not wrap the audio meter callback. Bind the public C
    ABI directly and retain the callback until it is removed. CDLL releases the
    GIL during detach/remove, allowing in-flight audio callbacks to finish.
    ABI: https://github.com/obsproject/obs-studio/blob/master/libobs/obs-audio-controls.h
    """
    def __init__(self, source_name, threshold_db):
        if sys.platform != "win32":
            raise RuntimeError("Native microphone guard currently requires Windows OBS")
        self.source_name = source_name
        self.threshold_db = float(threshold_db)
        if not math.isfinite(self.threshold_db) or not -120 <= self.threshold_db <= 0:
            raise ValueError("Microphone threshold_db must be between -120 and 0")
        self.lib = ctypes.CDLL("obs.dll")
        pointer = ctypes.c_void_p
        floats = ctypes.POINTER(ctypes.c_float)
        self.callback_type = ctypes.CFUNCTYPE(None, pointer, floats, floats, floats)
        signatures = {
            "obs_get_source_by_name": ([ctypes.c_char_p], pointer),
            "obs_source_release": ([pointer], None),
            "obs_source_get_ref": ([pointer], pointer),
            "obs_source_muted": ([pointer], ctypes.c_bool),
            "obs_source_active": ([pointer], ctypes.c_bool),
            "obs_source_get_audio_mixers": ([pointer], ctypes.c_uint32),
            "obs_source_get_monitoring_type": ([pointer], ctypes.c_int),
            "obs_volmeter_create": ([ctypes.c_int], pointer),
            "obs_volmeter_attach_source": ([pointer, pointer], ctypes.c_bool),
            "obs_volmeter_destroy": ([pointer], None),
            "obs_volmeter_add_callback": ([pointer, self.callback_type, pointer], None),
            "obs_volmeter_remove_callback": ([pointer, self.callback_type, pointer], None),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, result
        self.meter = None
        self.source = None
        self.last_signal_at = None
        self.last_callback_at = None
        self.peak_db = None
        self.callback = self.callback_type(self._on_level)

    def _on_level(self, param, magnitude, peak, input_peak):
        # No OBS calls, I/O, logging or locks in the audio callback.
        value = max(float(peak[channel]) for channel in range(8))
        now = time.monotonic()
        self.peak_db = value if math.isfinite(value) else None
        self.last_callback_at = now
        if math.isfinite(value) and value > self.threshold_db:
            self.last_signal_at = now

    def sample(self, recording_tracks):
        source = self.lib.obs_get_source_by_name(self.source_name.encode("utf-8"))
        if not source:
            self.close()
            return None, None, "Microphone source was not found"
        try:
            if source != self.source:
                self.close()
                self.meter = self.lib.obs_volmeter_create(2)  # OBS_FADER_LOG
                if not self.meter:
                    raise RuntimeError("Could not create OBS microphone meter")
                self.lib.obs_volmeter_add_callback(self.meter, self.callback, None)
                if not self.lib.obs_volmeter_attach_source(self.meter, source):
                    self.close()
                    raise RuntimeError("Could not attach OBS microphone meter")
                self.source = self.lib.obs_source_get_ref(source)
            if self.lib.obs_source_muted(source):
                return None, self.peak_db, "Microphone is muted in OBS"
            if not self.lib.obs_source_active(source):
                return None, self.peak_db, "Microphone source is inactive in OBS"
            if self.lib.obs_source_get_monitoring_type(source) == 1:
                return None, self.peak_db, "Microphone is set to monitor only, with output muted"
            if not (self.lib.obs_source_get_audio_mixers(source) & recording_tracks):
                return None, self.peak_db, "Microphone is not assigned to a recorded audio track"
            if self.last_callback_at is None or time.monotonic() - self.last_callback_at > 2.0:
                return None, self.peak_db, "No audio updates from microphone"
            return self.last_signal_at, self.peak_db, None
        finally:
            self.lib.obs_source_release(source)

    def close(self):
        if self.meter:
            self.lib.obs_volmeter_remove_callback(self.meter, self.callback, None)
            self.lib.obs_volmeter_destroy(self.meter)
        if self.source:
            self.lib.obs_source_release(self.source)
        self.meter = self.source = None
        self.last_signal_at = self.last_callback_at = self.peak_db = None


class MicrophoneGuard:
    def __init__(self, config, notify, meter_factory=ObsSourceMeter, alarm=None, clock=time.monotonic):
        self.enabled = bool(config.get("enabled", True))
        self.source_name = str(config.get("source_name", "Mic/Aux"))
        self.watch = SilenceWatch(config.get("silence_seconds", 30))
        self.threshold_db = float(config.get("threshold_db", -60))
        if not math.isfinite(self.threshold_db) or not -120 <= self.threshold_db <= 0:
            raise ValueError("Microphone threshold_db must be between -120 and 0")
        self.notify = notify
        self.meter_factory = meter_factory
        self.alarm = alarm or RepeatingAlarm()
        self.clock = clock
        self.meter = None
        self.retry_at = 0.0
        self.payload = self._payload("idle", False, 0.0, None, "")

    def _payload(self, state, alarm, silent_for, peak, message):
        return {"state": state, "alarm": alarm, "source_name": self.source_name,
                "silence_seconds": round(silent_for, 2), "timeout_seconds": self.watch.timeout,
                "threshold_db": self.threshold_db, "peak_db": peak, "message": message}

    def tick(self, recording, paused, recording_tracks):
        now = self.clock()
        if not self.enabled or not recording or paused:
            self.watch.update(now, False, False)
            self.alarm.set_active(False)
            if self.meter is not None:
                self.meter.close()
                self.meter = None
            self._publish(self._payload("disabled" if not self.enabled else "paused" if paused else "idle",
                                        False, 0.0, None, ""))
            return
        signal_at = peak = None
        error = "Microphone level monitoring is unavailable"
        try:
            if self.meter is None and now >= self.retry_at:
                self.retry_at = now + 1.0
                self.meter = self.meter_factory(self.source_name, self.threshold_db)
            if self.meter is not None:
                signal_at, peak, error = self.meter.sample(recording_tracks)
        except Exception as exc:
            error = "Microphone monitoring failed: %s" % exc
            if self.meter is not None:
                self.meter.close()
                self.meter = None
        alarm, silent_for = self.watch.update(now, True, False, signal_at if error is None else None)
        self.alarm.set_active(alarm)
        message = ((error or "No microphone signal") + ": " + self.source_name +
                   ". Check your microphone; recording is still running.") if alarm else ""
        self._publish(self._payload("alarm" if alarm else "monitoring", alarm, silent_for, peak, message))

    def _publish(self, payload):
        previous = self.payload
        self.payload = payload
        if payload["alarm"] != previous["alarm"]:
            self.notify(payload)

    def close(self):
        self.alarm.close()
        if self.meter is not None:
            self.meter.close()
            self.meter = None
