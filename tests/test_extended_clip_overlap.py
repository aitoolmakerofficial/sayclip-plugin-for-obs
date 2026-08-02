import subprocess
from pathlib import Path

from instant_easy_rename_server.use_cases.extended_clip import overlap
from instant_easy_rename_server.use_cases.extended_clip.overlap import _run


def test_media_tools_are_started_without_windows_console(monkeypatch) -> None:
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    _run(["ffprobe", "input.mp4"], label="probe")

    assert captured["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


def test_video_window_uses_absolute_end_to_survive_keyframe_seek(monkeypatch, tmp_path: Path) -> None:
    replay = tmp_path / "replay.mp4"
    recording = tmp_path / "recording.mp4"
    replay.write_bytes(b"replay")
    recording.write_bytes(b"recording")
    intervals = []

    def fake_media_probe(ffprobe, path):
        del ffprobe, path
        return {
            "streams": [{"codec_type": "video", "codec_name": "av1"}],
            "format": {"duration": "17.621333", "start_time": "0"},
        }

    def fake_packets(ffprobe, path, selector, read_interval=None):
        del ffprobe
        intervals.append((selector, read_interval))
        timestamp = "16" if Path(path).name == "replay.mp4" else "0"
        return [{"data_hash": "SHA256:x", "flags": "K", "pts_time": timestamp, "dts_time": timestamp}]

    monkeypatch.setattr(overlap, "_executable", lambda value: value)
    monkeypatch.setattr(overlap, "_media_probe", fake_media_probe)
    monkeypatch.setattr(overlap, "_packets", fake_packets)
    monkeypatch.setattr(overlap, "_require_compatible", lambda left, right: [])
    monkeypatch.setattr(overlap, "_verify_audio_overlap", lambda *args, **kwargs: [])

    overlap.process_overlap(
        replay,
        recording,
        analyze_only=True,
        min_video_packets=1,
        match_window_seconds=3,
    )

    assert intervals == [
        ("v:0", "14.621333%17.621333"),
        ("v:0", "0%3.000000"),
    ]
