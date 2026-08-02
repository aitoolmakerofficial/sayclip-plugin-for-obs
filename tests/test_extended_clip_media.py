from pathlib import Path

import pytest

from instant_easy_rename_server.use_cases.extended_clip.media import ExtendedClipMergeError, ExtendedClipMerger


def test_merger_rejects_different_source_extensions_without_running_probe(tmp_path: Path) -> None:
    replay = tmp_path / "replay.mp4"
    recording = tmp_path / "recording.mkv"
    replay.write_bytes(b"replay")
    recording.write_bytes(b"recording")
    merger = ExtendedClipMerger(tmp_path)

    with pytest.raises(ExtendedClipMergeError, match="different file formats"):
        merger.merge(replay, recording)


def test_merger_publishes_real_mkv_without_root_probe(monkeypatch, tmp_path: Path) -> None:
    replay = tmp_path / "replay.mp4"
    recording = tmp_path / "recording.mp4"
    replay.write_bytes(b"replay")
    recording.write_bytes(b"recording")

    def fake_process(replay_path, recording_path, *, output_path, **kwargs):
        del replay_path, recording_path, kwargs
        output = Path(output_path)
        output.write_bytes(b"matroska")
        return {"status": "ok", "sources_deleted": False}

    monkeypatch.setattr("instant_easy_rename_server.use_cases.extended_clip.media.process_overlap", fake_process)
    result = ExtendedClipMerger(tmp_path).merge(replay, recording)

    assert result.output_path.suffix == ".mkv"
    assert result.output_path.name == "recording.extended-clip.mkv"
    assert result.diagnostics["sources_deleted"] is False
    assert replay.exists() and recording.exists()
    assert result.diagnostics_path.exists()


def test_merger_does_not_overwrite_existing_output(monkeypatch, tmp_path: Path) -> None:
    replay = tmp_path / "replay.mkv"
    recording = tmp_path / "recording.mkv"
    replay.write_bytes(b"replay")
    recording.write_bytes(b"recording")
    (tmp_path / "recording.extended-clip.mkv").write_bytes(b"existing")

    def fake_process(replay_path, recording_path, *, output_path, **kwargs):
        del replay_path, recording_path, kwargs
        output = Path(output_path)
        output.write_bytes(b"new")
        return {"status": "ok", "sources_deleted": False}

    monkeypatch.setattr("instant_easy_rename_server.use_cases.extended_clip.media.process_overlap", fake_process)
    result = ExtendedClipMerger(tmp_path).merge(replay, recording)

    assert result.output_path.name == "recording.extended-clip-2.mkv"
    assert (tmp_path / "recording.extended-clip.mkv").read_bytes() == b"existing"
