from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import tempfile
from typing import Any, Protocol

from .audio import AudioPayload
from .config import AppConfig


logger = logging.getLogger(__name__)


class SpeechToTextError(RuntimeError):
    pass


class SttModelMissingError(SpeechToTextError):
    pass


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str | None = None
    confidence: float | None = None
    raw: dict[str, Any] | None = None


class SpeechToTextEngine(Protocol):
    def transcribe(self, audio: AudioPayload, *, language: str | None = None) -> TranscriptionResult:
        ...

    def is_ready(self) -> bool:
        ...

    def readiness_error(self) -> str | None:
        ...


class FakeSpeechToTextEngine:
    def __init__(self, transcript: str = "test voice title"):
        self.transcript = transcript

    def transcribe(self, audio: AudioPayload, *, language: str | None = None) -> TranscriptionResult:
        logger.debug("Fake STT transcribe: language=%s transcript=%r", language, self.transcript)
        return TranscriptionResult(text=self.transcript, language=language)

    def is_ready(self) -> bool:
        return True

    def readiness_error(self) -> str | None:
        return None


class FasterWhisperTinyCpuEngine:
    def __init__(self, config: AppConfig):
        self.config = config
        self.model_path = config.resolve_path(str(config.stt.get("model_path", "")))
        self.device = str(config.stt.get("device", "cpu"))
        self.compute_type = str(config.stt.get("compute_type", "int8"))
        self._model: Any | None = None

    def transcribe(self, audio: AudioPayload, *, language: str | None = None) -> TranscriptionResult:
        logger.debug(
            "faster-whisper transcribe starting: model_path=%s device=%s compute_type=%s language=%s audio_path=%s audio_bytes=%s",
            self.model_path,
            self.device,
            self.compute_type,
            language,
            audio.path,
            len(audio.data or b""),
        )
        error = self.readiness_error()
        if error:
            raise SttModelMissingError(error)

        try:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            logger.exception("faster-whisper is not installed")
            raise SpeechToTextError("faster-whisper is not installed.") from exc

        model = self._model or WhisperModel(
            str(self.model_path),
            device=self.device,
            compute_type=self.compute_type,
            local_files_only=True,
        )
        self._model = model
        if audio.path:
            segments, info = model.transcribe(str(audio.path), language=language)
            result = _segments_to_result(segments, info)
            logger.debug("faster-whisper transcribe completed: text=%r language=%s confidence=%s", result.text, result.language, result.confidence)
            return result

        suffix = f".{audio.format.lstrip('.') or 'wav'}"
        temp_path = _write_temp_audio(audio.data or b"", suffix)
        logger.debug("Temporary audio written for STT: %s", temp_path)
        try:
            segments, info = model.transcribe(str(temp_path), language=language)
            result = _segments_to_result(segments, info)
            logger.debug("faster-whisper transcribe completed: text=%r language=%s confidence=%s", result.text, result.language, result.confidence)
            return result
        finally:
            if not self.config.audio.get("keep_temp_audio", False):
                temp_path.unlink(missing_ok=True)

    def is_ready(self) -> bool:
        return self.readiness_error() is None

    def readiness_error(self) -> str | None:
        if self.device != "cpu":
            return "Only CPU STT is supported in the MVP."
        if not str(self.config.stt.get("model_path", "")).strip() or not self.model_path.exists():
            return "STT model not found. Set stt.model_path in config.toml."
        logger.debug("STT model ready: %s", self.model_path)
        return None


def build_stt_engine(config: AppConfig) -> SpeechToTextEngine:
    engine = str(config.stt.get("engine", "fake"))
    if engine == "fake":
        return FakeSpeechToTextEngine(str(config.stt.get("fake_transcript", "test voice title")))
    if engine == "faster_whisper":
        return FasterWhisperTinyCpuEngine(config)
    raise SpeechToTextError(f"Unknown STT engine: {engine}")


def _segments_to_result(segments: Any, info: Any) -> TranscriptionResult:
    text = " ".join(segment.text.strip() for segment in segments).strip()
    detected_language = getattr(info, "language", None)
    probability = getattr(info, "language_probability", None)
    return TranscriptionResult(text=text, language=detected_language, confidence=probability)


def _write_temp_audio(data: bytes, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(data)
        return Path(handle.name)
