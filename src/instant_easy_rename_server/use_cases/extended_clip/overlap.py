from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Sequence


class OverlapMergeError(RuntimeError):
    pass


def _executable(value: str) -> str:
    resolved = shutil.which(value)
    if resolved:
        return resolved
    candidate = Path(value)
    if candidate.is_file():
        return str(candidate.resolve())
    raise OverlapMergeError(f"Executable was not found: {value}")


def _run(command: Sequence[str], *, label: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        raise OverlapMergeError(f"{label} failed: {detail}")
    return completed


def _probe_json(ffprobe: str, path: Path, *extra: str) -> dict[str, Any]:
    completed = _run(
        [ffprobe, "-v", "error", "-print_format", "json", *extra, str(path)],
        label=f"ffprobe {path.name}",
    )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise OverlapMergeError(f"ffprobe returned invalid JSON for {path}") from error
    if not isinstance(value, dict):
        raise OverlapMergeError(f"ffprobe returned an invalid result for {path}")
    return value


def _media_probe(ffprobe: str, path: Path) -> dict[str, Any]:
    return _probe_json(
        ffprobe,
        path,
        "-show_streams",
        "-show_format",
        "-show_data_hash",
        "sha256",
    )


def _packets(
    ffprobe: str, path: Path, selector: str, read_interval: str | None = None
) -> list[dict[str, Any]]:
    interval = ["-read_intervals", read_interval] if read_interval else []
    probe = _probe_json(
        ffprobe,
        path,
        *interval,
        "-select_streams",
        selector,
        "-show_packets",
        "-show_entries",
        "packet=pts_time,dts_time,duration_time,flags,data_hash",
        "-show_data_hash",
        "sha256",
    )
    packets = probe.get("packets", [])
    if not isinstance(packets, list):
        return []
    return [packet for packet in packets if isinstance(packet, dict) and packet.get("data_hash")]


def _decimal(packet: dict[str, Any], *keys: str) -> Decimal:
    for key in keys:
        value = packet.get(key)
        if value not in (None, "N/A"):
            try:
                return Decimal(str(value))
            except InvalidOperation:
                pass
    raise OverlapMergeError(f"Packet has no usable timestamp: {packet}")


def _format_decimal(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _is_keyframe(packet: dict[str, Any]) -> bool:
    return "K" in str(packet.get("flags", ""))


def _matching_run(
    left: list[dict[str, Any]], left_index: int, right: list[dict[str, Any]], right_index: int
) -> int:
    count = 0
    while left_index + count < len(left) and right_index + count < len(right):
        if left[left_index + count].get("data_hash") != right[right_index + count].get("data_hash"):
            break
        count += 1
    return count


def _find_video_overlap(
    replay_packets: list[dict[str, Any]], recording_packets: list[dict[str, Any]], minimum_packets: int
) -> dict[str, Any]:
    try:
        recording_index = next(index for index, packet in enumerate(recording_packets) if _is_keyframe(packet))
    except StopIteration as error:
        raise OverlapMergeError("Recording contains no video keyframe") from error
    first_hash = recording_packets[recording_index]["data_hash"]
    candidates: list[tuple[int, int]] = []
    for replay_index, packet in enumerate(replay_packets):
        if packet.get("data_hash") != first_hash or not _is_keyframe(packet):
            continue
        run = _matching_run(replay_packets, replay_index, recording_packets, recording_index)
        if run >= minimum_packets:
            candidates.append((run, replay_index))
    if not candidates:
        raise OverlapMergeError(
            f"The first recording GOP was not found in replay (required {minimum_packets} packet hashes)"
        )
    run, replay_index = max(candidates, key=lambda item: (item[0], item[1]))
    replay_packet = replay_packets[replay_index]
    recording_packet = recording_packets[recording_index]
    return {
        "replay_index": replay_index,
        "recording_index": recording_index,
        "matched_packets": run,
        "replay_pts_sec": _decimal(replay_packet, "pts_time", "dts_time"),
        "replay_dts_sec": _decimal(replay_packet, "dts_time", "pts_time"),
        "recording_pts_sec": _decimal(recording_packet, "pts_time", "dts_time"),
        "recording_dts_sec": _decimal(recording_packet, "dts_time", "pts_time"),
        "first_hash": first_hash,
    }


def _stream_signature(stream: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "codec_type", "codec_name", "profile", "width", "height", "pix_fmt",
        "sample_rate", "channels", "channel_layout", "time_base", "extradata_hash",
    )
    return {key: stream.get(key) for key in keys if stream.get(key) is not None}


def _av_signatures(probe: dict[str, Any]) -> list[dict[str, Any]]:
    streams = probe.get("streams", [])
    return [
        _stream_signature(stream)
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") in {"video", "audio"}
    ]


def _require_compatible(replay_probe: dict[str, Any], recording_probe: dict[str, Any]) -> list[str]:
    replay = _av_signatures(replay_probe)
    recording = _av_signatures(recording_probe)
    if len(replay) != len(recording):
        raise OverlapMergeError(
            "Replay and recording stream layouts differ:\n"
            + json.dumps({"replay": replay, "recording": recording}, indent=2, ensure_ascii=False)
        )
    warnings: list[str] = []
    for index, (left, right) in enumerate(zip(replay, recording, strict=True)):
        fields = ["codec_type", "codec_name", "extradata_hash"]
        if left.get("codec_type") == "video":
            fields.extend(["width", "height", "pix_fmt"])
        elif left.get("codec_type") == "audio":
            fields.extend(["sample_rate", "channels", "channel_layout"])
        differences = {field: (left.get(field), right.get(field)) for field in fields if left.get(field) != right.get(field)}
        if differences:
            raise OverlapMergeError(
                f"Replay and recording stream {index} codec parameters differ:\n"
                + json.dumps(differences, indent=2, ensure_ascii=False)
            )
        left_profile, right_profile = left.get("profile"), right.get("profile")
        if left_profile and right_profile and left_profile != right_profile:
            raise OverlapMergeError(
                f"Replay and recording stream {index} profiles differ: {left_profile!r} != {right_profile!r}"
            )
        if left.get("time_base") != right.get("time_base"):
            warnings.append(
                f"stream {index} container time base differs ({left.get('time_base')} vs {right.get('time_base')}); "
                "the merge path will normalize containers with stream copy"
            )
        if bool(left_profile) != bool(right_profile):
            warnings.append(
                f"stream {index} profile is reported only by one container; matching codec extradata is used instead"
            )
    return warnings


def _audio_stream_count(probe: dict[str, Any]) -> int:
    return sum(
        1 for stream in probe.get("streams", [])
        if isinstance(stream, dict) and stream.get("codec_type") == "audio"
    )


def _verify_audio_overlap(
    ffprobe: str,
    replay: Path,
    recording: Path,
    replay_seam: Decimal,
    recording_seam: Decimal,
    stream_count: int,
    packet_count: int,
    tolerance_ms: int,
    window_seconds: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    lead = Decimal("0.5")
    length = Decimal(str(window_seconds))
    replay_start = max(Decimal(0), replay_seam - lead)
    recording_start = max(Decimal(0), recording_seam - lead)
    replay_end = replay_start + length
    recording_end = recording_start + length
    for index in range(stream_count):
        left = _packets(
            ffprobe,
            replay,
            f"a:{index}",
            f"{_format_decimal(replay_start)}%{_format_decimal(replay_end)}",
        )
        right = _packets(
            ffprobe,
            recording,
            f"a:{index}",
            f"{_format_decimal(recording_start)}%{_format_decimal(recording_end)}",
        )
        best: tuple[int, int, int] | None = None
        right_by_hash: dict[str, list[int]] = {}
        for right_index, packet in enumerate(right):
            right_by_hash.setdefault(str(packet["data_hash"]), []).append(right_index)
        for left_index, packet in enumerate(left):
            for right_index in right_by_hash.get(str(packet["data_hash"]), []):
                run = _matching_run(left, left_index, right, right_index)
                if best is None or run > best[0]:
                    best = (run, left_index, right_index)
        if best is None or best[0] < packet_count:
            raise OverlapMergeError(
                f"Audio stream {index} overlap was not verified (required {packet_count} packet hashes)"
            )
        run, left_index, right_index = best
        left_time = _decimal(left[left_index], "pts_time", "dts_time")
        right_time = _decimal(right[right_index], "pts_time", "dts_time")
        offset_ms = abs(((left_time - replay_seam) - (right_time - recording_seam)) * 1000)
        if offset_ms > tolerance_ms:
            raise OverlapMergeError(
                f"Audio stream {index} seam differs from video by {offset_ms} ms (limit {tolerance_ms} ms)"
            )
        results.append({"stream": index, "matched_packets": run, "offset_ms": str(offset_ms)})
    return results


def _ffconcat_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "'\\''").replace("\\", "/")


def _build_merge(
    ffmpeg: str,
    ffprobe: str,
    replay: Path,
    recording: Path,
    output: Path,
    cut_duration: Decimal,
    recording_signature: list[str],
    seam_decode_seconds: float,
    keep_temp: bool,
) -> dict[str, Any]:
    if output.suffix.lower() != ".mkv":
        raise OverlapMergeError("Extended Clip output must be a Matroska (.mkv) file")
    if output.exists():
        raise OverlapMergeError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="sayclip-overlap-", dir=output.parent))
    prefix = work / "replay-prefix.mkv"
    normalized = work / "recording.mkv"
    manifest = work / "sequence.ffconcat"
    partial = work / "output.partial.mkv"
    cut_text = _format_decimal(cut_duration)
    try:
        prefix_run = _run(
            [ffmpeg, "-hide_banner", "-v", "warning", "-y", "-i", str(replay), "-to", cut_text,
             "-map", "0:v:0", "-map", "0:a?", "-c", "copy", str(prefix)],
            label="replay prefix remux",
        )
        recording_run = _run(
            [ffmpeg, "-hide_banner", "-v", "warning", "-y", "-i", str(recording),
             "-map", "0:v:0", "-map", "0:a?", "-c", "copy", str(normalized)],
            label="recording remux",
        )
        _require_compatible(_media_probe(ffprobe, prefix), _media_probe(ffprobe, normalized))
        prefix_hashes = [packet["data_hash"] for packet in _packets(ffprobe, prefix, "v:0")]
        signature_first = recording_signature[0]
        if signature_first in prefix_hashes:
            raise OverlapMergeError("Replay prefix still contains the first recording GOP")
        manifest.write_text(
            "ffconcat version 1.0\n"
            f"file '{_ffconcat_path(prefix)}'\n"
            f"duration {cut_text}\n"
            f"file '{_ffconcat_path(normalized)}'\n",
            encoding="utf-8",
        )
        concat_run = _run(
            [ffmpeg, "-hide_banner", "-v", "warning", "-y", "-f", "concat", "-safe", "0",
             "-i", str(manifest), "-map", "0:v:0", "-map", "0:a?", "-c", "copy", str(partial)],
            label="stream-copy concat",
        )
        output_packets = _packets(ffprobe, partial, "v:0")
        output_hashes = [packet["data_hash"] for packet in output_packets]
        matches = []
        for index, value in enumerate(output_hashes):
            if value != signature_first:
                continue
            if output_hashes[index:index + len(recording_signature)] == recording_signature:
                matches.append(index)
        if len(matches) != 1:
            raise OverlapMergeError(f"Merged seam signature occurs {len(matches)} times; expected exactly once")
        decode_start = max(Decimal(0), cut_duration - Decimal(str(seam_decode_seconds)))
        _run(
            [ffmpeg, "-hide_banner", "-v", "error", "-ss", _format_decimal(decode_start), "-i", str(partial),
             "-t", str(seam_decode_seconds * 2), "-map", "0:v:0", "-map", "0:a?", "-f", "null", os.devnull],
            label="seam decode validation",
        )
        output_probe = _media_probe(ffprobe, partial)
        os.replace(partial, output)
        return {
            "output": str(output),
            "output_size": output.stat().st_size,
            "output_duration": output_probe.get("format", {}).get("duration"),
            "output_format_name": output_probe.get("format", {}).get("format_name"),
            "seam_packet_index": matches[0],
            "work_directory": str(work) if keep_temp else None,
            "ffmpeg_warnings": [text.strip() for text in (prefix_run.stderr, recording_run.stderr, concat_run.stderr) if text.strip()],
        }
    finally:
        if not keep_temp:
            shutil.rmtree(work, ignore_errors=True)


def process_overlap(
    replay_path: str | Path,
    recording_path: str | Path,
    *,
    output_path: str | Path | None = None,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    min_video_packets: int = 16,
    audio_packets: int = 8,
    audio_tolerance_ms: int = 250,
    seam_decode_seconds: float = 2.0,
    match_window_seconds: float = 3.0,
    analyze_only: bool = False,
    keep_temp: bool = False,
) -> dict[str, Any]:
    replay = Path(replay_path).resolve(strict=True)
    recording = Path(recording_path).resolve(strict=True)
    if replay == recording:
        raise OverlapMergeError("Replay and recording must be different files.")
    if replay.suffix.lower() != recording.suffix.lower():
        raise OverlapMergeError("Replay and recording have different file formats.")
    ffprobe_bin = _executable(ffprobe)
    ffmpeg_bin = _executable(ffmpeg) if not analyze_only else ffmpeg
    replay_probe = _media_probe(ffprobe_bin, replay)
    recording_probe = _media_probe(ffprobe_bin, recording)
    warnings = _require_compatible(replay_probe, recording_probe)
    codec = next(
        (stream.get("codec_name") for stream in replay_probe.get("streams", []) if stream.get("codec_type") == "video"),
        None,
    )
    replay_duration = Decimal(str(replay_probe.get("format", {}).get("duration", "0")))
    window = Decimal(str(match_window_seconds))
    replay_start = max(Decimal(0), replay_duration - window)
    replay_video = _packets(
        ffprobe_bin,
        replay,
        "v:0",
        f"{_format_decimal(replay_start)}%{_format_decimal(replay_duration)}",
    )
    recording_video = _packets(ffprobe_bin, recording, "v:0", f"0%{_format_decimal(window)}")
    overlap = _find_video_overlap(replay_video, recording_video, min_video_packets)
    audio_count = _audio_stream_count(replay_probe)
    audio = _verify_audio_overlap(
        ffprobe_bin, replay, recording, overlap["replay_dts_sec"], overlap["recording_dts_sec"],
        audio_count, audio_packets, audio_tolerance_ms, match_window_seconds,
    )
    start_time = Decimal(str(replay_probe.get("format", {}).get("start_time", "0")))
    cut_duration = overlap["replay_dts_sec"] - start_time
    if cut_duration <= 0:
        raise OverlapMergeError("Calculated replay prefix duration is not positive")
    diagnostics: dict[str, Any] = {
        "status": "analyzed" if analyze_only else "merged",
        "replay": str(replay),
        "recording": str(recording),
        "video_codec": codec,
        "stream_signatures": _av_signatures(replay_probe),
        "recording_stream_signatures": _av_signatures(recording_probe),
        "compatibility_warnings": warnings,
        "video_overlap": {key: str(value) if isinstance(value, Decimal) else value for key, value in overlap.items()},
        "audio_overlap": audio,
        "cut_duration_sec": str(cut_duration),
        "sources_deleted": False,
    }
    if not analyze_only:
        if output_path is None:
            raise OverlapMergeError("An output path is required for merge")
        recording_index = int(overlap["recording_index"])
        signature_length = min(int(overlap["matched_packets"]), max(min_video_packets, 32))
        signature = [packet["data_hash"] for packet in recording_video[recording_index:recording_index + signature_length]]
        diagnostics["merge"] = _build_merge(
            ffmpeg_bin, ffprobe_bin, replay, recording, Path(output_path).resolve(), cut_duration,
            signature, seam_decode_seconds, keep_temp,
        )
    return diagnostics
