from pathlib import Path

import pytest

from instant_easy_rename_server.use_cases.extended_clip import (
    ExtendedClipMergeResult,
    ExtendedClipPhase,
    ExtendedClipService,
)


class FakeMerger:
    def __init__(self, output: Path) -> None:
        self.output = output
        self.calls: list[tuple[str, str]] = []

    def merge(self, replay_path: str, recording_path: str) -> ExtendedClipMergeResult:
        self.calls.append((replay_path, recording_path))
        return ExtendedClipMergeResult(self.output, self.output.with_suffix(".diagnostics.json"), {"status": "ok"})


def test_extended_clip_happy_path_owns_recording_and_merges(tmp_path: Path) -> None:
    merger = FakeMerger(tmp_path / "merged.mkv")
    service = ExtendedClipService(merger, tmp_path / "state" / "session.json")

    service.start()
    service.mark_recording_started()
    service.mark_saving_replay()
    service.mark_capturing(str(tmp_path / "replay.mp4"), {"source_title": "Game"})
    service.begin_finish()
    result = service.merge(str(tmp_path / "recording.mp4"))
    service.mark_naming()
    service.complete(str(result.output_path))

    assert merger.calls == [(str((tmp_path / "replay.mp4").resolve()), str((tmp_path / "recording.mp4").resolve()))]
    assert service.session is not None
    assert service.session.phase == ExtendedClipPhase.DONE
    assert service.session.recording_owned is False
    assert service.public_payload() == {"active": False, "stage": "idle"}
    assert (tmp_path / "state" / "session.json").exists()


def test_extended_clip_rejects_second_start_and_finish_before_capturing(tmp_path: Path) -> None:
    service = ExtendedClipService(FakeMerger(tmp_path / "merged.mkv"), tmp_path / "session.json")
    service.start()

    with pytest.raises(ValueError, match="extended_clip_active"):
        service.start()
    with pytest.raises(ValueError, match="operation_busy"):
        service.begin_finish()


def test_cancel_keeps_known_paths_and_never_merges(tmp_path: Path) -> None:
    merger = FakeMerger(tmp_path / "merged.mkv")
    service = ExtendedClipService(merger, tmp_path / "session.json")
    service.start()
    service.mark_recording_started()
    service.mark_saving_replay()
    service.mark_capturing(str(tmp_path / "replay.mp4"))

    service.begin_cancel()
    service.cancel(str(tmp_path / "recording.mp4"))

    assert merger.calls == []
    assert service.session is not None
    assert service.session.phase == ExtendedClipPhase.CANCELLED
    assert service.session.replay_path == str((tmp_path / "replay.mp4").resolve())
    assert service.session.recording_path == str((tmp_path / "recording.mp4").resolve())


def test_cancel_is_rejected_after_finish_commit(tmp_path: Path) -> None:
    service = ExtendedClipService(FakeMerger(tmp_path / "merged.mkv"), tmp_path / "session.json")
    service.start()
    service.mark_capturing(str(tmp_path / "replay.mp4"))
    service.begin_finish()

    with pytest.raises(ValueError, match="processing_committed"):
        service.begin_cancel()


def test_stale_journal_is_preserved_but_not_resumed(tmp_path: Path) -> None:
    journal = tmp_path / "session.json"
    journal.write_text('{"phase": "capturing"}', encoding="utf-8")

    service = ExtendedClipService(FakeMerger(tmp_path / "merged.mkv"), journal)

    assert service.session is None
    assert not journal.exists()
    assert journal.with_suffix(".json.stale").exists()

