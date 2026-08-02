from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .overlap import OverlapMergeError, process_overlap


class ExtendedClipMergeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtendedClipMergeResult:
    output_path: Path
    diagnostics_path: Path
    diagnostics: dict[str, Any]


class ExtendedClipMerger:
    """Production facade for the in-package packet-overlap implementation."""

    def __init__(
        self,
        root: Path,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        min_video_packets: int = 16,
        audio_packets: int = 8,
        seam_decode_seconds: float = 2.0,
        match_window_seconds: float = 3.0,
    ) -> None:
        self.root = root.resolve()
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.min_video_packets = min_video_packets
        self.audio_packets = audio_packets
        self.seam_decode_seconds = seam_decode_seconds
        self.match_window_seconds = match_window_seconds

    def merge(self, replay_path: str | Path, recording_path: str | Path) -> ExtendedClipMergeResult:
        replay = Path(replay_path).resolve(strict=True)
        recording = Path(recording_path).resolve(strict=True)
        if replay == recording:
            raise ExtendedClipMergeError("Replay and recording must be different files.")
        if replay.suffix.lower() != recording.suffix.lower():
            raise ExtendedClipMergeError("Replay and recording have different file formats.")
        output = _unique_output(recording.with_name(recording.stem + ".extended-clip.mkv"))
        diagnostics_path = output.with_suffix(output.suffix + ".diagnostics.json")
        diagnostics: dict[str, Any] = {"sources_deleted": False}
        try:
            diagnostics = process_overlap(
                replay,
                recording,
                output_path=output,
                ffmpeg=self.ffmpeg,
                ffprobe=self.ffprobe,
                min_video_packets=self.min_video_packets,
                audio_packets=self.audio_packets,
                seam_decode_seconds=self.seam_decode_seconds,
                match_window_seconds=self.match_window_seconds,
            )
        except (OverlapMergeError, OSError) as error:
            diagnostics["error"] = str(error)
            _write_diagnostics(diagnostics_path, diagnostics)
            raise ExtendedClipMergeError(str(error)) from error
        _write_diagnostics(diagnostics_path, diagnostics)
        if not output.exists():
            raise ExtendedClipMergeError("Extended Clip merge did not create an output file.")
        return ExtendedClipMergeResult(output, diagnostics_path, diagnostics)


def _unique_output(candidate: Path) -> Path:
    if not candidate.exists():
        return candidate
    for index in range(2, 10_000):
        numbered = candidate.with_name(f"{candidate.stem}-{index}{candidate.suffix}")
        if not numbered.exists():
            return numbered
    raise ExtendedClipMergeError("Could not allocate a unique Extended Clip output path.")


def _write_diagnostics(path: Path, diagnostics: dict[str, Any]) -> None:
    path.write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False), encoding="utf-8")
