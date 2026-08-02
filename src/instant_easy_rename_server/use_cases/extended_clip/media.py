from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


class ExtendedClipMergeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtendedClipMergeResult:
    output_path: Path
    diagnostics_path: Path
    diagnostics: dict[str, Any]


class ExtendedClipMerger:
    """Production facade around the field-tested packet-overlap implementation.

    The current rollout always publishes a real Matroska output. Inputs are
    never changed or deleted. The standalone probe remains the single packet
    matching implementation until the MP4 remux experiment is complete.
    """

    def __init__(
        self,
        root: Path,
        *,
        python_executable: str | None = None,
        probe_script: Path | None = None,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        min_video_packets: int = 16,
        audio_packets: int = 8,
        seam_decode_seconds: float = 2.0,
        match_window_seconds: float = 3.0,
    ) -> None:
        self.root = root.resolve()
        self.python_executable = python_executable or sys.executable
        self.probe_script = probe_script or self.root / "replay_overlap_probe.py"
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
        if not self.probe_script.exists():
            raise ExtendedClipMergeError(f"Overlap merge tool was not found: {self.probe_script}")

        output = _unique_output(recording.with_name(recording.stem + ".extended-clip.mkv"))
        diagnostics_path = output.with_suffix(output.suffix + ".diagnostics.json")
        command = [
            self.python_executable,
            str(self.probe_script),
            str(replay),
            str(recording),
            "--output",
            str(output),
            "--min-video-packets",
            str(self.min_video_packets),
            "--audio-packets",
            str(self.audio_packets),
            "--seam-decode-seconds",
            str(self.seam_decode_seconds),
            "--match-window-seconds",
            str(self.match_window_seconds),
            "--ffmpeg",
            self.ffmpeg,
            "--ffprobe",
            self.ffprobe,
        ]
        completed = subprocess.run(
            command,
            cwd=str(self.root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        diagnostics = _read_diagnostics(diagnostics_path)
        if completed.returncode != 0 or not output.exists():
            message = str(diagnostics.get("error") or "Extended Clip merge failed.")
            stderr = completed.stderr.strip()
            if stderr and message == "Extended Clip merge failed.":
                message = stderr.splitlines()[-1]
            raise ExtendedClipMergeError(message)
        return ExtendedClipMergeResult(output, diagnostics_path, diagnostics)


def _unique_output(candidate: Path) -> Path:
    if not candidate.exists():
        return candidate
    for index in range(2, 10_000):
        numbered = candidate.with_name(f"{candidate.stem}-{index}{candidate.suffix}")
        if not numbered.exists():
            return numbered
    raise ExtendedClipMergeError("Could not allocate a unique Extended Clip output path.")


def _read_diagnostics(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
