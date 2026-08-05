from __future__ import annotations

from enum import Enum
from typing import Any


BACKEND_BASE_URL = "http://127.0.0.1:17891"
HEALTH_PATH = "/health"
STATUS_PATH = "/api/status"
SAVE_MOMENT_PATH = "/api/save/moment"
SAVE_RECORDING_PATH = "/api/save/recording"
DISCARD_RECORDING_PATH = "/api/discard/recording"
EXTENDED_CLIP_START_PATH = "/api/extended-clip/start"
EXTENDED_CLIP_FINISH_PATH = "/api/extended-clip/finish"
EXTENDED_CLIP_CANCEL_PATH = "/api/extended-clip/cancel"


class StreamDeckTitle(str, Enum):
    IDLE = "IDLE"
    SPEAK = "SPEAK"
    STT = "STT"
    BUSY = "BUSY"
    DONE = "DONE"
    ERROR = "ERROR"
    OFFLINE = "OFFLINE"
    SENT = "SENT"
    RECORDING = "RECORDING"
    PROCESSING = "PROCESSING"


def title_for_status_snapshot(snapshot: dict[str, Any] | None, *, reachable: bool = True) -> StreamDeckTitle:
    if not reachable or not snapshot:
        return StreamDeckTitle.OFFLINE

    phase = str(snapshot.get("ui_state") or snapshot.get("phase") or "idle")
    if phase == "recording":
        return StreamDeckTitle.RECORDING
    if phase == "processing":
        return StreamDeckTitle.PROCESSING
    if phase == "idle":
        return StreamDeckTitle.BUSY if snapshot.get("busy") else StreamDeckTitle.IDLE
    if phase in {"listening", "recording_voice_title"}:
        return StreamDeckTitle.SPEAK
    if phase == "transcribing":
        return StreamDeckTitle.STT
    if phase == "done":
        return StreamDeckTitle.DONE
    if phase == "error":
        return StreamDeckTitle.ERROR
    return StreamDeckTitle.BUSY


def title_for_save_response(response: dict[str, Any] | None, *, reachable: bool = True) -> StreamDeckTitle:
    if not reachable or not response:
        return StreamDeckTitle.OFFLINE
    if response.get("accepted") is True:
        return StreamDeckTitle.SENT
    if response.get("accepted") is False and response.get("reason") == "busy":
        return StreamDeckTitle.BUSY
    if response.get("ok") is False:
        return StreamDeckTitle.OFFLINE
    return StreamDeckTitle.ERROR
