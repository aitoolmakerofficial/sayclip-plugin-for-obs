from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol
import logging
import queue
import time

from .audio_devices import list_audio_input_device_names, selected_audio_device_exists
from .config import AppConfig


logger = logging.getLogger(__name__)
LevelCallback = Callable[[float], None]


class AudioRecorderError(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioPayload:
    data: bytes | None = None
    path: Path | None = None
    sample_rate: int = 16000
    channels: int = 1
    format: str = "wav"

    def __post_init__(self) -> None:
        if self.data is None and self.path is None:
            raise ValueError("AudioPayload requires data or path")


class AudioRecorder(Protocol):
    def record(self, *, on_level: LevelCallback | None = None) -> AudioPayload:
        ...

    def is_available(self) -> bool:
        ...

    def readiness_error(self) -> str | None:
        ...


class FakeAudioRecorder:
    def __init__(self, payload: AudioPayload | None = None, *, available: bool = True, level: float = 0.42):
        self.payload = payload or AudioPayload(data=b"fake-wav-audio")
        self.available = available
        self.level = level

    def record(self, *, on_level: LevelCallback | None = None) -> AudioPayload:
        logger.debug("Fake audio recording started")
        if not self.available:
            raise AudioRecorderError("Microphone unavailable. SayClip cannot listen.")
        if on_level:
            on_level(self.level)
        logger.debug("Fake audio recording completed: level=%s bytes=%s", self.level, len(self.payload.data or b""))
        return self.payload

    def is_available(self) -> bool:
        return self.available

    def readiness_error(self) -> str | None:
        if self.available:
            return None
        return "Microphone unavailable. SayClip cannot listen."


class DefaultMicrophoneRecorder:
    def __init__(self, config: AppConfig):
        self.config = config
        self.device = str(config.audio.get("device", "default"))
        self.max_record_seconds = float(config.audio.get("max_record_seconds", 8))
        self.silence_stop_enabled = bool(config.audio.get("silence_stop_enabled", True))
        self.silence_seconds = float(config.audio.get("silence_seconds", 5))

    def record(self, *, on_level: LevelCallback | None = None) -> AudioPayload:
        logger.debug(
            "Microphone recording starting: device=%s max_seconds=%s silence_enabled=%s silence_seconds=%s",
            self.device,
            self.max_record_seconds,
            self.silence_stop_enabled,
            self.silence_seconds,
        )
        try:
            import sounddevice as sd  # type: ignore[import-not-found]
            import soundfile as sf  # type: ignore[import-not-found]
        except ModuleNotFoundError as error:
            logger.exception("Audio recording dependencies missing")
            raise AudioRecorderError("Audio recording dependencies are not installed. Run install.bat again.") from error

        import io

        sample_rate = 16000
        device = None if self.device == "default" else _resolve_sounddevice_device(sd, self.device)
        logger.debug("Resolved sounddevice device: configured=%s resolved=%s", self.device, device)
        if device is None and self.device != "default":
            raise AudioRecorderError(f"Selected microphone was not found: {self.device}")
        try:
            import numpy as np  # type: ignore[import-not-found]

            chunks: list[object] = []
            errors: queue.Queue[Exception] = queue.Queue()
            stop_at = time.monotonic() + self.max_record_seconds

            def callback(indata: object, frames: int, time_info: object, status: object) -> None:
                if status:
                    logger.debug("Microphone stream status: %s", status)
                try:
                    chunk = indata.copy()  # type: ignore[attr-defined]
                    chunks.append(chunk)
                    if on_level:
                        on_level(_peak_level(chunk))
                except Exception as error:
                    errors.put(error)

            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                device=device,
                callback=callback,
            ):
                while time.monotonic() < stop_at:
                    if not errors.empty():
                        raise errors.get()
                    time.sleep(0.05)
            recording = np.concatenate(chunks, axis=0) if chunks else np.zeros((0, 1), dtype="float32")
        except Exception as error:
            logger.exception("Microphone recording failed")
            raise AudioRecorderError(f"Microphone recording failed: {error}") from error
        peak = 0.0
        try:
            peak = _peak_level(recording)
        except ValueError:
            peak = 0.0
        buffer = io.BytesIO()
        sf.write(buffer, recording, sample_rate, format="WAV")
        data = buffer.getvalue()
        logger.debug("Microphone recording completed: peak=%s bytes=%s", peak, len(data))
        return AudioPayload(data=data, sample_rate=sample_rate, channels=1, format="wav")

    def is_available(self) -> bool:
        return self.readiness_error() is None

    def readiness_error(self) -> str | None:
        logger.debug("Checking microphone readiness: device=%s", self.device)
        try:
            import sounddevice as sd  # type: ignore[import-not-found]
            import soundfile  # noqa: F401  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            logger.debug("Audio dependencies missing during readiness check", exc_info=True)
            return "Audio recording dependencies are not installed. Run install.bat again."
        if self.device == "default":
            try:
                sd.query_devices(kind="input")
            except Exception:
                logger.debug("Default input microphone readiness check failed", exc_info=True)
                return "No default input microphone was found."
            return None
        if not selected_audio_device_exists(self.device):
            return f"Selected microphone was not found: {self.device}"
        if _resolve_sounddevice_device(sd, self.device) is None:
            return f"Selected microphone is visible to Windows but not available for recording: {self.device}"
        return None


def build_audio_recorder(config: AppConfig) -> AudioRecorder:
    if str(config.audio.get("device", "default")) == "fake":
        return FakeAudioRecorder()
    return DefaultMicrophoneRecorder(config)


def list_input_devices() -> list[str]:
    return list_audio_input_device_names()


def _resolve_sounddevice_device(sounddevice: object, name: str) -> int | str | None:
    try:
        devices = sounddevice.query_devices()  # type: ignore[attr-defined]
    except Exception:
        logger.debug("Failed to query sounddevice devices", exc_info=True)
        return None
    selected = name.casefold()
    for index, device in enumerate(devices):
        device_name = str(device.get("name", "")).strip()
        if int(device.get("max_input_channels", 0)) <= 0:
            continue
        candidate = device_name.casefold()
        if candidate == selected or candidate.startswith(selected) or selected.startswith(candidate):
            return index
    return None


def _peak_level(recording: object) -> float:
    try:
        return max(0.0, min(1.0, float(abs(recording).max())))  # type: ignore[attr-defined]
    except ValueError:
        return 0.0
