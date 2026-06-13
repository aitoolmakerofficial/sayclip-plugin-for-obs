from datetime import datetime
from pathlib import Path

from instant_easy_rename_server.config import load_config
from instant_easy_rename_server.jobs import JobCreateRequest, JobStore


def test_create_job_is_session_only(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    store = JobStore(config)
    request = JobCreateRequest.from_payload(
        {
            "type": "recording",
            "original_path": "D:/Recordings/Forza Horizon 6/2026-05-27 21-31-12.mkv",
            "source_title": "Forza Horizon 6",
        }
    )

    job = store.create(request, now=datetime(2026, 5, 27, 21, 31, 12))
    reloaded = JobStore(config)

    assert job.status == "created"
    assert job.game == "forza-horizon-6"
    assert not (tmp_path / "jobs.json").exists()
    assert reloaded.list() == []


def test_status_transition_updates_job(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    store = JobStore(config)
    job = store.create(
        JobCreateRequest.from_payload(
            {
                "type": "moment",
                "original_path": "D:/Recordings/Forza Horizon 6/Replays/2026-05-27 22-10-44.mkv",
            }
        )
    )

    updated = store.update_status(job.id, "waiting_for_voice")

    assert updated.status == "waiting_for_voice"


def test_jobs_are_limited_to_latest_50(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    store = JobStore(config)

    for index in range(55):
        store.create(
            JobCreateRequest.from_payload(
                {
                    "type": "recording",
                    "original_path": f"D:/Recordings/Game/{index:02d}.mkv",
                }
            )
        )

    jobs = store.list()
    assert len(jobs) == 50
    assert jobs[0].original_path.endswith("54.mkv")
    assert jobs[-1].original_path.endswith("05.mkv")
