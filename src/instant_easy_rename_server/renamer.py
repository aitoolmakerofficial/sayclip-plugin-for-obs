# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 AI Toolmaker (AI Toolmaker Official)

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
import time

from .config import AppConfig
from .jobs import Job
from .naming import format_relative_media_path, next_available_path, sanitize_slug


class RenameError(RuntimeError):
    pass


class MediaRenamer(Protocol):
    def rename(self, job: Job, transcript: str) -> Path:
        ...


@dataclass
class FileSystemMediaRenamer:
    config: AppConfig
    retry_seconds: float = 10.0
    retry_interval_seconds: float = 0.5

    def rename(self, job: Job, transcript: str) -> Path:
        source = Path(job.original_path)
        if not source.exists():
            raise RenameError(f"Original file does not exist: {source}")

        title = sanitize_slug(transcript, fallback="")
        if not title:
            raise RenameError("Recognized title became empty after sanitization.")

        try:
            relative_path = format_relative_media_path(
                game=job.game,
                job_type=job.type,
                original_path=source,
                title=title,
                when=datetime.now(timezone.utc).astimezone(),
                filename_format=str(self.config.naming["format"]),
                datetime_format=str(self.config.naming["datetime_format"]),
                job_type_tokens=dict(self.config.naming["job_type_tokens"]),
                unknown_source_token=str(self.config.naming["unknown_game_token"]),
            )
        except (KeyError, ValueError) as error:
            raise RenameError(f"Invalid rename format: {error}") from error

        target = next_available_path(source.parent / relative_path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise RenameError(f"Could not create output folder: {target.parent}") from error
        self._replace_with_retry(source, target)
        return target

    def _replace_with_retry(self, source: Path, target: Path) -> None:
        deadline = time.monotonic() + self.retry_seconds
        last_error: OSError | None = None
        while True:
            try:
                source.rename(target)
                return
            except OSError as error:
                last_error = error
                if time.monotonic() >= deadline:
                    break
                time.sleep(self.retry_interval_seconds)
        raise RenameError("File is locked or could not be renamed.") from last_error


def build_media_renamer(config: AppConfig) -> MediaRenamer:
    return FileSystemMediaRenamer(config)
