from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from instant_easy_rename_server.use_cases.extended_clip.overlap import OverlapMergeError, process_overlap


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze or merge an OBS replay/recording overlap without re-encoding.")
    parser.add_argument("replay", type=Path)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--output", type=Path, default=Path("manual_sequence_merged.mkv"))
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument("--force", action="store_true", help="Retained for CLI compatibility; existing output is never overwritten.")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--min-video-packets", type=int, default=16)
    parser.add_argument("--audio-packets", type=int, default=8)
    parser.add_argument("--audio-tolerance-ms", type=int, default=250)
    parser.add_argument("--seam-decode-seconds", type=float, default=2.0)
    parser.add_argument("--match-window-seconds", type=float, default=3.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output.resolve()
    diagnostics_path = output.with_suffix(output.suffix + ".diagnostics.json")
    diagnostics: dict[str, object] = {"sources_deleted": False}
    try:
        if output.exists() and not args.analyze_only:
            raise OverlapMergeError(f"Output already exists: {output}")
        diagnostics = process_overlap(
            args.replay,
            args.recording,
            output_path=output,
            ffmpeg=args.ffmpeg,
            ffprobe=args.ffprobe,
            min_video_packets=args.min_video_packets,
            audio_packets=args.audio_packets,
            audio_tolerance_ms=args.audio_tolerance_ms,
            seam_decode_seconds=args.seam_decode_seconds,
            match_window_seconds=args.match_window_seconds,
            analyze_only=args.analyze_only,
            keep_temp=args.keep_temp,
        )
        print(f"Replay:    {Path(args.replay).resolve()}")
        print(f"Recording: {Path(args.recording).resolve()}")
        print(f"Video codec: {diagnostics.get('video_codec')}")
        for warning in diagnostics.get("compatibility_warnings", []):
            print(f"Compatibility note: {warning}")
        overlap = diagnostics.get("video_overlap", {})
        print(
            f"Video overlap: {overlap.get('matched_packets')} packets, "
            f"replay DTS {overlap.get('replay_dts_sec')} s, "
            f"prefix duration {diagnostics.get('cut_duration_sec')} s"
        )
        print(f"Audio overlap: verified {len(diagnostics.get('audio_overlap', []))} track(s)")
        if not args.analyze_only:
            print(f"Merged output: {output}")
        print("Input files were not modified or deleted.")
        return_code = 0
    except (OverlapMergeError, FileNotFoundError, OSError) as error:
        diagnostics["error"] = str(error)
        print(f"ERROR: {error}", file=sys.stderr)
        return_code = 1
    finally:
        try:
            diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
            diagnostics_path.write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Diagnostics: {diagnostics_path}")
        except OSError as error:
            print(f"Could not write diagnostics: {error}", file=sys.stderr)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
