from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal
import secrets

from .config import AppConfig
from .naming import game_from_request


JobType = Literal["recording", "moment"]
JobStatus = Literal[
    "created",
    "waiting_for_voice",
    "listening",
    "transcribing",
    "renaming",
    "done",
    "error",
]

VALID_JOB_TYPES = {"recording", "moment"}
VALID_STATUSES = {
    "created",
    "waiting_for_voice",
    "listening",
    "transcribing",
    "renaming",
    "done",
    "error",
}


@dataclass
class JobCreateRequest:
    type: JobType
    original_path: str
    game_hint: str | None = None
    scene_name: str | None = None
    source_name: str | None = None
    source_title: str | None = None
    created_by: str = "obs_bridge"

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "JobCreateRequest":
        job_type = payload.get("type")
        original_path = payload.get("original_path")
        if job_type not in VALID_JOB_TYPES:
            raise ValueError("type must be one of: recording, moment")
        if not isinstance(original_path, str) or not original_path.strip():
            raise ValueError("original_path is required")
        return cls(
            type=job_type,
            original_path=original_path,
            game_hint=_optional_str(payload.get("game_hint")),
            scene_name=_optional_str(payload.get("scene_name")),
            source_name=_optional_str(payload.get("source_name")),
            source_title=_optional_str(payload.get("source_title")),
            created_by=str(payload.get("created_by") or "obs_bridge"),
        )


@dataclass
class Job:
    id: str
    type: JobType
    status: JobStatus
    game: str
    original_path: str
    transcript: str | None
    final_path: str | None
    error: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobStore:
    def __init__(self, config: AppConfig):
        self.config = config
        self.jobs: list[Job] = []

    def create(self, request: JobCreateRequest, now: datetime | None = None) -> Job:
        current = now or datetime.now(timezone.utc).astimezone()
        stamp = current.strftime("%Y%m%d-%H%M%S")
        job = Job(
            id=f"{stamp}-{secrets.token_hex(3)}",
            type=request.type,
            status="created",
            game=game_from_request(
                request.original_path,
                request.source_title,
                request.game_hint,
                self.config.naming["unknown_game_token"],
            ),
            original_path=request.original_path,
            transcript=None,
            final_path=None,
            error=None,
            created_at=current.isoformat(),
            updated_at=current.isoformat(),
        )
        self.jobs.insert(0, job)
        self.jobs = self.jobs[: self.config.max_jobs]
        return job

    def update_status(self, job_id: str, status: JobStatus) -> Job:
        if status not in VALID_STATUSES:
            raise ValueError(f"Unknown status: {status}")
        job = self._find(job_id)
        job.status = status
        job.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
        return job

    def update_transcript(self, job_id: str, transcript: str, status: JobStatus = "renaming") -> Job:
        if status not in VALID_STATUSES:
            raise ValueError(f"Unknown status: {status}")
        job = self._find(job_id)
        job.transcript = transcript
        job.status = status
        job.error = None
        job.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
        return job

    def complete(self, job_id: str, final_path: str) -> Job:
        job = self._find(job_id)
        job.status = "done"
        job.final_path = final_path
        job.error = None
        job.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
        return job

    def fail(self, job_id: str, error: str) -> Job:
        job = self._find(job_id)
        job.status = "error"
        job.error = error
        job.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
        return job

    def _find(self, job_id: str) -> Job:
        for job in self.jobs:
            if job.id == job_id:
                return job
        raise KeyError(job_id)

    def list(self) -> list[Job]:
        return list(self.jobs)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
