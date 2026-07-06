from pathlib import Path

from instant_easy_rename_server.api import BackendApi
from instant_easy_rename_server.audio import FakeAudioRecorder
from instant_easy_rename_server.config import load_config
from instant_easy_rename_server.jobs import Job
from instant_easy_rename_server.renamer import RenameError
from instant_easy_rename_server.stt import FakeSpeechToTextEngine


class LockedRenamer:
    def rename(self, job: Job, transcript: str) -> Path:
        raise RenameError("File is locked or could not be renamed.")


def test_fake_voice_pipeline_renames_real_temp_video(tmp_path: Path) -> None:
    original = tmp_path / "Test Game" / "2026-05-27 22-10-44.mkv"
    original.parent.mkdir()
    original.write_bytes(b"video")
    api = BackendApi(
        load_config(tmp_path),
        audio_recorder=FakeAudioRecorder(),
        stt_engine=FakeSpeechToTextEngine("clean overtake"),
    )

    created = api.create_job({"type": "moment", "original_path": str(original)})
    job = api.list_jobs()["jobs"][0]
    final_path = Path(job["final_path"])

    assert created["status"] == "done"
    assert job["status"] == "done"
    assert final_path.name == "test-game__2026-05-27_22-10-44__clean-overtake.mkv"
    assert final_path.exists()
    assert not original.exists()


def test_rename_conflict_gets_numeric_suffix(tmp_path: Path) -> None:
    original = tmp_path / "Game" / "2026-05-27 21-31-12.mkv"
    original.parent.mkdir()
    original.write_bytes(b"video")
    existing = original.with_name("game__2026-05-27_21-31-12__test-voice-title.mkv")
    existing.write_bytes(b"existing")
    api = BackendApi(load_config(tmp_path))

    api.create_job({"type": "recording", "original_path": str(original)})
    job = api.list_jobs()["jobs"][0]

    assert Path(job["final_path"]).name == "game__2026-05-27_21-31-12__test-voice-title(2).mkv"
    assert Path(job["final_path"]).exists()
    assert existing.exists()


def test_completed_job_keeps_final_path_in_session(tmp_path: Path) -> None:
    original = tmp_path / "Game" / "2026-05-27 21-31-12.mkv"
    original.parent.mkdir()
    original.write_bytes(b"video")
    api = BackendApi(load_config(tmp_path))

    api.create_job({"type": "recording", "original_path": str(original)})
    job = api.list_jobs()["jobs"][0]

    assert job["final_path"]
    assert job["status"] == "done"
    assert not (tmp_path / "jobs.json").exists()


def test_locked_file_failure_becomes_clean_job_error(tmp_path: Path) -> None:
    original = tmp_path / "Game" / "2026-05-27 21-31-12.mkv"
    original.parent.mkdir()
    original.write_bytes(b"video")
    api = BackendApi(
        load_config(tmp_path),
        audio_recorder=FakeAudioRecorder(),
        stt_engine=FakeSpeechToTextEngine("locked clip"),
        media_renamer=LockedRenamer(),
    )

    api.create_job({"type": "recording", "original_path": str(original)})
    job = api.list_jobs()["jobs"][0]

    assert job["status"] == "error"
    assert job["error"] == "File is locked or could not be renamed."
