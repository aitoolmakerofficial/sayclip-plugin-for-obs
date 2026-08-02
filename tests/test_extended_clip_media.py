from pathlib import Path

import json

import pytest

from instant_easy_rename_server.use_cases.extended_clip.media import ExtendedClipMergeError, ExtendedClipMerger


def test_merger_rejects_different_source_extensions_without_running_probe(tmp_path: Path) -> None:
    replay = tmp_path / "replay.mp4"
    recording = tmp_path / "recording.mkv"
    replay.write_bytes(b"replay")
    recording.write_bytes(b"recording")
    merger = ExtendedClipMerger(tmp_path, probe_script=tmp_path / "missing.py")

    with pytest.raises(ExtendedClipMergeError, match="different file formats"):
        merger.merge(replay, recording)


def test_merger_publishes_real_mkv_and_reads_diagnostics(monkeypatch, tmp_path: Path) -> None:
    replay = tmp_path / "replay.mp4"
    recording = tmp_path / "recording.mp4"
    probe = tmp_path / "replay_overlap_probe.py"
    replay.write_bytes(b"replay")
    recording.write_bytes(b"recording")
    probe.write_text("# probe", encoding="utf-8")
    commands = []

    def fake_run(command, **kwargs):
        del kwargs
        commands.append(command)
        output = Path(command[command.index("--output") + 1])
        output.write_bytes(b"matroska")
        output.with_suffix(output.suffix + ".diagnostics.json").write_text(
            json.dumps({"status": "ok", "sources_deleted": False}), encoding="utf-8"
        )

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    monkeypatch.setattr("instant_easy_rename_server.use_cases.extended_clip.media.subprocess.run", fake_run)
    result = ExtendedClipMerger(tmp_path, probe_script=probe).merge(replay, recording)

    assert result.output_path.suffix == ".mkv"
    assert result.output_path.name == "recording.extended-clip.mkv"
    assert result.diagnostics["sources_deleted"] is False
    assert "--force" not in commands[0]
    assert replay.exists() and recording.exists()


def test_merger_does_not_overwrite_existing_output(monkeypatch, tmp_path: Path) -> None:
    replay = tmp_path / "replay.mkv"
    recording = tmp_path / "recording.mkv"
    probe = tmp_path / "replay_overlap_probe.py"
    replay.write_bytes(b"replay")
    recording.write_bytes(b"recording")
    probe.write_text("# probe", encoding="utf-8")
    (tmp_path / "recording.extended-clip.mkv").write_bytes(b"existing")

    def fake_run(command, **kwargs):
        del kwargs
        output = Path(command[command.index("--output") + 1])
        output.write_bytes(b"new")
        output.with_suffix(output.suffix + ".diagnostics.json").write_text('{"status":"ok"}', encoding="utf-8")

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    monkeypatch.setattr("instant_easy_rename_server.use_cases.extended_clip.media.subprocess.run", fake_run)
    result = ExtendedClipMerger(tmp_path, probe_script=probe).merge(replay, recording)

    assert result.output_path.name == "recording.extended-clip-2.mkv"
    assert (tmp_path / "recording.extended-clip.mkv").read_bytes() == b"existing"

