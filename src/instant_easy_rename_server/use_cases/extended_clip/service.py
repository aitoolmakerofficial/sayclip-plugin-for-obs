from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
from typing import Any

from .domain import ExtendedClipPhase, ExtendedClipSession
from .media import ExtendedClipMergeResult, ExtendedClipMerger


class ExtendedClipService:
    def __init__(self, merger: ExtendedClipMerger, journal_path: Path) -> None:
        self.merger = merger
        self.journal_path = journal_path
        self.session: ExtendedClipSession | None = None
        self._mark_stale_journal()

    def start(self) -> ExtendedClipSession:
        if self.active_session is not None:
            raise ValueError("extended_clip_active")
        now = _now()
        self.session = ExtendedClipSession(
            id=f"extended-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}",
            phase=ExtendedClipPhase.STARTING_RECORDING,
            created_at=now,
            updated_at=now,
        )
        self.persist()
        return self.session

    @property
    def active_session(self) -> ExtendedClipSession | None:
        return self.session if self.session and self.session.active else None

    def mark_recording_started(self) -> None:
        session = self._require_active()
        session.recording_owned = True
        session.transition(ExtendedClipPhase.WAITING_OVERLAP)
        self.persist()

    def mark_saving_replay(self) -> None:
        session = self._require_active()
        session.transition(ExtendedClipPhase.SAVING_REPLAY)
        self.persist()

    def mark_capturing(self, replay_path: str, metadata: dict[str, Any] | None = None) -> None:
        session = self._require_active()
        session.replay_path = str(Path(replay_path).resolve())
        metadata = metadata or {}
        session.source_title = _optional_text(metadata.get("source_title"))
        session.game_hint = _optional_text(metadata.get("game_hint"))
        session.transition(ExtendedClipPhase.CAPTURING)
        self.persist()

    def begin_finish(self) -> ExtendedClipSession:
        session = self._require_phase(ExtendedClipPhase.CAPTURING)
        session.transition(ExtendedClipPhase.STOPPING_RECORDING)
        self.persist()
        return session

    def begin_cancel(self) -> ExtendedClipSession:
        session = self._require_active()
        if session.phase not in {
            ExtendedClipPhase.STARTING_RECORDING,
            ExtendedClipPhase.WAITING_OVERLAP,
            ExtendedClipPhase.SAVING_REPLAY,
            ExtendedClipPhase.CAPTURING,
        }:
            raise ValueError("processing_committed")
        session.transition(ExtendedClipPhase.CANCELLING)
        self.persist()
        return session

    def cancel(self, recording_path: str | None = None) -> None:
        session = self._require_active()
        if recording_path:
            session.recording_path = str(Path(recording_path).resolve())
        session.recording_owned = False
        session.transition(ExtendedClipPhase.CANCELLED)
        self.persist()

    def manual_recording_stop(self, recording_path: str | None = None) -> None:
        session = self.active_session
        if session is None or session.phase != ExtendedClipPhase.CAPTURING:
            return
        self.cancel(recording_path)

    def merge(self, recording_path: str) -> ExtendedClipMergeResult:
        session = self._require_phase(ExtendedClipPhase.STOPPING_RECORDING)
        if not session.replay_path:
            raise ValueError("Extended Clip replay path is missing.")
        session.recording_path = str(Path(recording_path).resolve())
        session.recording_owned = False
        session.transition(ExtendedClipPhase.MATCHING)
        self.persist()
        session.transition(ExtendedClipPhase.MERGING)
        self.persist()
        result = self.merger.merge(session.replay_path, session.recording_path)
        session.output_path = str(result.output_path)
        session.transition(ExtendedClipPhase.VALIDATING)
        self.persist()
        return result

    def mark_naming(self) -> None:
        session = self._require_active()
        session.transition(ExtendedClipPhase.NAMING)
        self.persist()

    def complete(self, final_path: str) -> None:
        session = self._require_active()
        session.output_path = final_path
        session.transition(ExtendedClipPhase.DONE)
        self.persist()

    def fail(self, error: str) -> None:
        session = self.active_session
        if session is None:
            return
        session.recording_owned = False
        session.error = error
        session.transition(ExtendedClipPhase.ERROR)
        self.persist()

    def public_payload(self) -> dict[str, Any]:
        session = self.active_session
        return {
            "active": session is not None,
            "stage": session.stage if session else "idle",
        }

    def persist(self) -> None:
        if self.session is None:
            return
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.journal_path.with_suffix(self.journal_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.session.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.journal_path)

    def _require_active(self) -> ExtendedClipSession:
        session = self.active_session
        if session is None:
            raise ValueError("extended_clip_inactive")
        return session

    def _require_phase(self, phase: ExtendedClipPhase) -> ExtendedClipSession:
        session = self._require_active()
        if session.phase != phase:
            raise ValueError("operation_busy")
        return session

    def _mark_stale_journal(self) -> None:
        if not self.journal_path.exists():
            return
        stale = self.journal_path.with_suffix(self.journal_path.suffix + ".stale")
        if stale.exists():
            stale = self.journal_path.with_name(self.journal_path.name + f".{secrets.token_hex(3)}.stale")
        try:
            os.replace(self.journal_path, stale)
        except OSError:
            return


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

