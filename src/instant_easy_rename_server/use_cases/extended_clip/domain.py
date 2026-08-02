from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ExtendedClipPhase(str, Enum):
    STARTING_RECORDING = "starting_recording"
    WAITING_OVERLAP = "waiting_overlap"
    SAVING_REPLAY = "saving_replay"
    CAPTURING = "capturing"
    STOPPING_RECORDING = "stopping_recording"
    MATCHING = "matching"
    MERGING = "merging"
    VALIDATING = "validating"
    NAMING = "naming"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    DONE = "done"
    ERROR = "error"


RECORDING_PHASES = {
    ExtendedClipPhase.STARTING_RECORDING,
    ExtendedClipPhase.WAITING_OVERLAP,
    ExtendedClipPhase.SAVING_REPLAY,
    ExtendedClipPhase.CAPTURING,
}
PROCESSING_PHASES = {
    ExtendedClipPhase.STOPPING_RECORDING,
    ExtendedClipPhase.MATCHING,
    ExtendedClipPhase.MERGING,
    ExtendedClipPhase.VALIDATING,
    ExtendedClipPhase.NAMING,
    ExtendedClipPhase.CANCELLING,
}
TERMINAL_PHASES = {
    ExtendedClipPhase.CANCELLED,
    ExtendedClipPhase.DONE,
    ExtendedClipPhase.ERROR,
}


@dataclass
class ExtendedClipSession:
    id: str
    phase: ExtendedClipPhase
    created_at: str
    updated_at: str
    recording_owned: bool = False
    replay_path: str | None = None
    recording_path: str | None = None
    output_path: str | None = None
    error: str | None = None
    source_title: str | None = None
    game_hint: str | None = None

    def transition(self, phase: ExtendedClipPhase) -> None:
        self.phase = phase
        self.updated_at = _now()

    @property
    def active(self) -> bool:
        return self.phase not in TERMINAL_PHASES

    @property
    def stage(self) -> str:
        if self.phase in RECORDING_PHASES:
            return "recording"
        if self.phase in PROCESSING_PHASES:
            return "processing"
        return "idle"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["phase"] = self.phase.value
        return payload


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()

