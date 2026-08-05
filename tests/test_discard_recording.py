from pathlib import Path

import pytest

from instant_easy_rename_server.use_cases import discard_recording as discard_module
from instant_easy_rename_server.use_cases.discard_recording import (
    DISCARD_MODE_DELETE_PERMANENTLY,
    DISCARD_MODE_MOVE,
    DiscardRecordingError,
    DiscardRecordingService,
    validate_discard_folder_name,
)


def test_move_uses_obs_root_folder_and_preserves_original_name(tmp_path: Path) -> None:
    source = tmp_path / "nested" / "recording.mkv"
    source.parent.mkdir()
    source.write_bytes(b"video")

    result = DiscardRecordingService().discard(
        source,
        tmp_path,
        mode=DISCARD_MODE_MOVE,
        folder_name="SayClip Discarded",
    )

    assert result.destination_path == tmp_path / "SayClip Discarded" / "recording.mkv"
    assert result.destination_path.read_bytes() == b"video"
    assert not source.exists()


def test_move_resolves_conflicts_with_parenthesized_numbers(tmp_path: Path) -> None:
    destination = tmp_path / "SayClip Discarded"
    destination.mkdir()
    (destination / "recording.mkv").write_bytes(b"old")
    (destination / "recording (1).mkv").write_bytes(b"older")
    source = tmp_path / "recording.mkv"
    source.write_bytes(b"new")

    result = DiscardRecordingService().discard(source, tmp_path, mode=DISCARD_MODE_MOVE)

    assert result.destination_path == destination / "recording (2).mkv"
    assert result.destination_path.read_bytes() == b"new"
    assert (destination / "recording.mkv").read_bytes() == b"old"


def test_delete_permanently_removes_source_without_creating_folder(tmp_path: Path) -> None:
    source = tmp_path / "recording.mkv"
    source.write_bytes(b"video")

    result = DiscardRecordingService().discard(
        source,
        tmp_path,
        mode=DISCARD_MODE_DELETE_PERMANENTLY,
    )

    assert result.destination_path is None
    assert not source.exists()
    assert not (tmp_path / "SayClip Discarded").exists()


def test_move_rejects_cross_volume_without_touching_source(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "recording.mkv"
    source.write_bytes(b"video")
    monkeypatch.setattr(discard_module, "_paths_are_on_same_volume", lambda source, root: False)

    with pytest.raises(DiscardRecordingError, match="between disks"):
        DiscardRecordingService().discard(source, tmp_path, mode=DISCARD_MODE_MOVE)

    assert source.read_bytes() == b"video"
    assert not (tmp_path / "SayClip Discarded").exists()


@pytest.mark.parametrize("name", ["../Discarded", "folder/name", r"folder\name", "CON", "bad."])
def test_folder_name_rejects_paths_and_unsafe_names(name: str) -> None:
    with pytest.raises(DiscardRecordingError):
        validate_discard_folder_name(name)


def test_directory_source_is_rejected_without_creating_destination(tmp_path: Path) -> None:
    source = tmp_path / "recording.mkv"
    source.mkdir()

    with pytest.raises(DiscardRecordingError, match="regular file"):
        DiscardRecordingService().discard(source, tmp_path, mode=DISCARD_MODE_MOVE)

    assert not (tmp_path / "SayClip Discarded").exists()
