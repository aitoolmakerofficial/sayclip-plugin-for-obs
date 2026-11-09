from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from instant_easy_rename_server.api import BackendApi
from instant_easy_rename_server.audio import AudioPayload, DefaultMicrophoneRecorder, FakeAudioRecorder
from instant_easy_rename_server.config import load_config
from instant_easy_rename_server.jobs import Job
from instant_easy_rename_server.stt import FakeSpeechToTextEngine, FasterWhisperTinyCpuEngine


class NoopRenamer:
    def rename(self, job: Job, transcript: str) -> Path:
        return Path(job.original_path)


class CapturingSoundPlayer:
    def __init__(self) -> None:
        self.events: list[str] = []

    def listening_started(self) -> None:
        self.events.append("start")

    def listening_finished(self) -> None:
        self.events.append("finish")


def test_fake_recorder_returns_known_audio_payload() -> None:
    recorder = FakeAudioRecorder(AudioPayload(data=b"known-audio"), level=0.7)
    levels: list[float] = []

    payload = recorder.record(on_level=levels.append)

    assert payload.data == b"known-audio"
    assert levels == [0.7]


def test_fake_stt_drives_job_flow_to_transcription(tmp_path: Path) -> None:
    sound_player = CapturingSoundPlayer()
    api = BackendApi(
        load_config(tmp_path),
        audio_recorder=FakeAudioRecorder(),
        stt_engine=FakeSpeechToTextEngine("overtime clutch"),
        media_renamer=NoopRenamer(),
        sound_player=sound_player,
    )

    created = api.create_job({"type": "moment", "original_path": "D:/Recordings/Game/clip.mkv"})
    job = api.list_jobs()["jobs"][0]

    assert created["status"] == "done"
    assert job["transcript"] == "overtime clutch"
    assert Path(job["final_path"]) == Path("D:/Recordings/Game/clip.mkv")
    assert job["error"] is None
    assert api.mic_level == 0.0
    assert sound_player.events == ["start", "finish"]


def test_empty_transcript_causes_clean_job_error(tmp_path: Path) -> None:
    api = BackendApi(
        load_config(tmp_path),
        audio_recorder=FakeAudioRecorder(),
        stt_engine=FakeSpeechToTextEngine("  "),
        media_renamer=NoopRenamer(),
    )

    created = api.create_job({"type": "recording", "original_path": "D:/Recordings/Game/video.mkv"})
    job = api.list_jobs()["jobs"][0]

    assert created["status"] == "error"
    assert job["error"] == "Speech recognition returned empty text."


def test_microphone_unavailable_maps_to_clean_error(tmp_path: Path) -> None:
    api = BackendApi(
        load_config(tmp_path),
        audio_recorder=FakeAudioRecorder(available=False),
        stt_engine=FakeSpeechToTextEngine("title"),
        media_renamer=NoopRenamer(),
    )

    api.create_job({"type": "moment", "original_path": "D:/Recordings/Game/clip.mkv"})
    job = api.list_jobs()["jobs"][0]

    assert job["status"] == "error"
    assert job["error"] == "Microphone unavailable. SayClip cannot listen."


def test_faster_whisper_missing_model_reports_system_check(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    config.data["stt"]["engine"] = "faster_whisper"
    config.data["stt"]["model_path"] = "missing-model"
    api = BackendApi(
        config,
        audio_recorder=FakeAudioRecorder(),
        stt_engine=FasterWhisperTinyCpuEngine(config),
        media_renamer=NoopRenamer(),
    )

    api.create_job({"type": "recording", "original_path": "D:/Recordings/Game/video.mkv"})
    job = api.list_jobs()["jobs"][0]
    checks = api.system_checks()

    assert checks["model"]["ok"] is False
    assert checks["model"]["message"] == "STT model not found. Set stt.model_path in config.toml."
    assert job["status"] == "error"
    assert job["error"] == "STT model not found. Set stt.model_path in config.toml."


@pytest.mark.parametrize("samples", [None, [0.0] * 160, [1e-9] * 160])
def test_silent_input_fails_naming_without_touching_video(tmp_path, monkeypatch, samples):
    recorder = _microphone_with_samples(tmp_path, monkeypatch, samples)
    monkeypatch.setattr(recorder, "readiness_error", lambda: None)
    original = tmp_path / "recording.mp4"
    original.write_bytes(b"original video")

    class UnexpectedStt:
        def readiness_error(self):
            return None

        def transcribe(self, *args, **kwargs):
            pytest.fail("Silent audio must not reach speech recognition")

    api = BackendApi(
        recorder.config, audio_recorder=recorder,
        stt_engine=UnexpectedStt(), media_renamer=NoopRenamer(),
    )
    created = api.create_job({"type": "recording", "original_path": str(original)})
    job = api.list_jobs()["jobs"][0]

    assert created["status"] == "error"
    assert "No audio signal from microphone" in job["error"]
    assert api.last_error == job["error"]
    assert original.read_bytes() == b"original video"
    assert job["final_path"] is None


def test_quiet_nonzero_microphone_signal_is_kept(tmp_path, monkeypatch):
    import io
    import soundfile as sf

    recorder = _microphone_with_samples(tmp_path, monkeypatch, [-0.0001, 0.0001] * 80)
    payload = recorder.record()
    samples, sample_rate = sf.read(io.BytesIO(payload.data))
    assert sample_rate == 16000
    assert len(samples) == 160
    assert abs(samples).max() > 0


def _microphone_with_samples(tmp_path, monkeypatch, samples):
    class InputStream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]

        def __enter__(self):
            if samples is not None:
                data = np.array(samples, dtype="float32").reshape(-1, 1)
                self.callback(data, len(data), None, None)
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(InputStream=InputStream))
    config = load_config(tmp_path)
    config.data["audio"]["device"] = "default"
    config.data["audio"]["max_record_seconds"] = 0
    return DefaultMicrophoneRecorder(config)
