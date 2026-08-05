# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 AI Toolmaker (AI Toolmaker Official)

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
import logging
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading

from .audio import AudioRecorder, AudioRecorderError, build_audio_recorder
from .audio_feedback import ListeningSoundPlayer, build_listening_sound_player
from .config import AppConfig
from .jobs import JobCreateRequest, JobStore
from .renamer import MediaRenamer, RenameError, build_media_renamer
from .stt import SpeechToTextEngine, SpeechToTextError, build_stt_engine
from .use_cases.discard_recording import (
    DEFAULT_DISCARD_FOLDER_NAME,
    DISCARD_MODE_DELETE_PERMANENTLY,
    DISCARD_MODE_MOVE,
    DiscardRecordingError,
    DiscardRecordingService,
)
from .use_cases.extended_clip import (
    ExtendedClipMergeError,
    ExtendedClipMerger,
    ExtendedClipPhase,
    ExtendedClipService,
)


logger = logging.getLogger(__name__)
BRIDGE_HEARTBEAT_SECONDS = 3.0
OBS_STATE_HEARTBEAT_SECONDS = 3.0
DONE_STATUS_SECONDS = 2.0
ERROR_STATUS_SECONDS = 8.0
DISCARD_CONFIRMATION_SECONDS = 2.0
DISCARD_PUBLIC_ERROR = "Recording was not discarded."


class BridgeCommandAction(str, Enum):
    SAVE_MOMENT = "save_moment"
    SAVE_RECORDING = "save_recording"
    DISCARD_RECORDING = "discard_recording"
    EXTENDED_CLIP_START = "extended_clip_start"
    EXTENDED_CLIP_FINISH = "extended_clip_finish"
    EXTENDED_CLIP_CANCEL = "extended_clip_cancel"


class OperationPhase(str, Enum):
    IDLE = "idle"
    COMMAND_SENT = "command_sent"
    WAITING_FOR_OBS = "waiting_for_obs"
    WAITING_FOR_FILE = "waiting_for_file"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    RENAMING = "renaming"
    DONE = "done"
    ERROR = "error"


class BridgeCommandStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


@dataclass
class BridgeCommand:
    id: str
    action: BridgeCommandAction
    status: BridgeCommandStatus
    created_at: str
    updated_at: str | None = None
    result: dict[str, Any] | None = None
    job_id: str | None = None
    policy: dict[str, Any] | None = None
    backend_processing: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["action"] = self.action.value
        payload["status"] = self.status.value
        return payload


class BackendApi:
    def __init__(
        self,
        config: AppConfig,
        store: JobStore | None = None,
        *,
        audio_recorder: AudioRecorder | None = None,
        stt_engine: SpeechToTextEngine | None = None,
        media_renamer: MediaRenamer | None = None,
        sound_player: ListeningSoundPlayer | None = None,
        extended_clip_service: ExtendedClipService | None = None,
        discard_recording_service: DiscardRecordingService | None = None,
    ):
        self.config = config
        self.store = store or JobStore(config)
        self.audio_recorder = audio_recorder or build_audio_recorder(config)
        self.stt_engine = stt_engine or build_stt_engine(config)
        self.media_renamer = media_renamer or build_media_renamer(config)
        self.sound_player = sound_player or build_listening_sound_player(config)
        self.discard_recording_service = discard_recording_service or DiscardRecordingService()
        extended_config = config.extended_clip
        self.extended_clip = extended_clip_service or ExtendedClipService(
            ExtendedClipMerger(
                config.root,
                ffmpeg=str(extended_config.get("ffmpeg") or "ffmpeg"),
                ffprobe=str(extended_config.get("ffprobe") or "ffprobe"),
                min_video_packets=int(extended_config.get("min_video_packets", 16)),
                audio_packets=int(extended_config.get("audio_packets", 8)),
                seam_decode_seconds=float(extended_config.get("seam_decode_seconds", 2.0)),
                match_window_seconds=float(extended_config.get("match_window_seconds", 3.0)),
            ),
            config.resolve_path(str(extended_config.get("runtime_path") or ".local/extended-clip/session.json")),
        )
        self.errors: list[dict[str, Any]] = []
        self.mic_level = 0.0
        self.listening_started_at: datetime | None = None
        self.bridge_commands: list[BridgeCommand] = []
        self.bridge_last_seen_at: datetime | None = None
        self.obs_state: dict[str, Any] = {}
        self.obs_state_seen_at: datetime | None = None
        self.active_command_id: str | None = None
        self.active_job_id: str | None = None
        self.last_result: str | None = None
        self.last_result_expires_at: datetime | None = None
        self.last_error: str | None = None
        self.discard_confirmation_expires_at: datetime | None = None
        self.shutdown_requested = threading.Event()
        self._lock = threading.RLock()

    def health(self) -> dict[str, str]:
        return {
            "app": self.config.app_name,
            "version": self.config.app_version,
            "status": "ok",
        }

    def create_job(self, payload: dict[str, Any]) -> dict[str, str]:
        logger.debug("Create job requested: %s", payload)
        request = JobCreateRequest.from_payload(payload)
        with self._lock:
            job = self.store.create(request)
        self._process_voice(job.id)
        current = self.list_jobs()["jobs"][0]
        if current["id"] == job.id:
            return {"job_id": current["id"], "status": current["status"]}
        return {"job_id": job.id, "status": job.status}

    def create_job_async(self, payload: dict[str, Any]) -> dict[str, str]:
        logger.debug("Create async job requested: %s", payload)
        request = JobCreateRequest.from_payload(payload)
        with self._lock:
            job = self.store.create(request)
            self._mark_active_job_locked(job.id)
        thread = threading.Thread(target=self._process_voice, args=(job.id,), daemon=True)
        thread.start()
        logger.debug("Async job accepted: job_id=%s", job.id)
        return {"job_id": job.id, "status": "created"}

    def list_jobs(self) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            return {"jobs": [job.to_dict() for job in self.store.list()]}

    def record_error(self, payload: dict[str, Any]) -> dict[str, str]:
        with self._lock:
            self.errors.insert(0, payload)
        return {"status": "accepted"}

    def list_errors(self) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            return {"errors": list(self.errors)}

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._expire_terminal_result_locked()
            if self.extended_clip.active_session is not None and (
                not self._bridge_is_connected() or not self._obs_state_is_fresh()
            ):
                self.extended_clip.fail("Extended Clip stopped because the OBS bridge state was lost.")
                self.last_result = OperationPhase.ERROR.value
                self.last_error = "Extended Clip stopped because the OBS bridge state was lost. Source files were kept."
                self.last_result_expires_at = self._terminal_expiry(ERROR_STATUS_SECONDS)
            jobs = self.store.list()
            active_command = self._active_command()
            active_job = self._active_job(active_command)
            active_job_status = active_job.status if active_job else None
            mic_error = self.audio_recorder.readiness_error()
            busy = active_command is not None or active_job is not None
            operation_phase = self._operation_phase(active_command, active_job_status)
            return {
                "backend": "ok",
                "bridge": self._bridge_status(),
                "busy": busy,
                "phase": operation_phase.value,
                "ui_state": self._ui_state(operation_phase, active_job_status),
                "active_action": active_command.action.value if active_command else None,
                "active_job_id": active_job.id if active_job else None,
                "last_result": self.last_result,
                "last_error": self.last_error,
                "obs": self._obs_status_payload(),
                "extended_clip": self.extended_clip.public_payload(),
                "actions": self._action_availability_payload(busy=busy),
                "mic": {
                    "available": mic_error is None,
                    "device": str(self.config.audio.get("device", "default")),
                    "active": active_job_status == "listening",
                    "level": round(self.mic_level, 4),
                    "elapsed_seconds": round(self._listening_elapsed_seconds(), 3),
                    "max_record_seconds": float(self.config.audio.get("max_record_seconds", 8)),
                    "remaining_seconds": round(self._listening_remaining_seconds(), 3),
                },
            }

    def open_latest_output_folder(self) -> dict[str, Any]:
        with self._lock:
            jobs = self.store.list()
            last_job = jobs[0].to_dict() if jobs else None
        if not last_job:
            return {"ok": False, "error": "No output folder available"}

        final_path = _path_or_none(last_job.get("final_path"))
        folder = _path_or_none(last_job.get("folder")) or _folder_for_job(last_job)
        if final_path and final_path.exists():
            _open_in_explorer(final_path, select=True)
            return {"ok": True}
        if folder and folder.exists():
            _open_in_explorer(folder, select=False)
            return {"ok": True}
        return {"ok": False, "error": "No output folder available"}

    def save_moment(self) -> dict[str, Any]:
        return self._enqueue_save_action(BridgeCommandAction.SAVE_MOMENT)

    def save_recording(self) -> dict[str, Any]:
        return self._enqueue_save_action(BridgeCommandAction.SAVE_RECORDING)

    def discard_recording(self) -> dict[str, Any]:
        with self._lock:
            active_command = self._active_command()
            busy = active_command is not None or self._active_job(active_command) is not None
            availability = self._discard_action_availability(busy=busy)
            if not availability["enabled"]:
                self.discard_confirmation_expires_at = None
                return {"ok": True, "accepted": False, "reason": availability["reason"]}

            now = datetime.now(timezone.utc).astimezone()
            if not self._discard_confirmation_is_armed_locked(now):
                self.discard_confirmation_expires_at = now + timedelta(seconds=DISCARD_CONFIRMATION_SECONDS)
                return {
                    "ok": True,
                    "accepted": False,
                    "confirmation_armed": True,
                    "confirmation_expires_in_ms": int(DISCARD_CONFIRMATION_SECONDS * 1000),
                }

            self.discard_confirmation_expires_at = None
            configured_mode = str(self.config.discard.get("mode") or DISCARD_MODE_MOVE).strip()
            if configured_mode not in {DISCARD_MODE_MOVE, DISCARD_MODE_DELETE_PERMANENTLY}:
                logger.warning("Unknown discard mode %r; using safe move mode", configured_mode)
                configured_mode = DISCARD_MODE_MOVE
            policy = {
                "mode": configured_mode,
                "folder_name": str(self.config.discard.get("folder_name") or DEFAULT_DISCARD_FOLDER_NAME).strip()
                or DEFAULT_DISCARD_FOLDER_NAME,
            }
            return self._enqueue_bridge_command_locked(BridgeCommandAction.DISCARD_RECORDING, policy=policy)

    def start_extended_clip(self) -> dict[str, Any]:
        with self._lock:
            availability = self._extended_action_availability("extended_clip_start")
            if not availability["enabled"]:
                return {"ok": True, "accepted": False, "reason": availability["reason"]}
            self.extended_clip.start()
            return self._enqueue_bridge_command_locked(BridgeCommandAction.EXTENDED_CLIP_START)

    def finish_extended_clip(self) -> dict[str, Any]:
        with self._lock:
            availability = self._extended_action_availability("extended_clip_finish")
            if not availability["enabled"]:
                return {"ok": True, "accepted": False, "reason": availability["reason"]}
            self.extended_clip.begin_finish()
            return self._enqueue_bridge_command_locked(BridgeCommandAction.EXTENDED_CLIP_FINISH)

    def cancel_extended_clip(self) -> dict[str, Any]:
        with self._lock:
            availability = self._extended_action_availability("extended_clip_cancel")
            if not availability["enabled"]:
                return {"ok": True, "accepted": False, "reason": availability["reason"]}
            self.extended_clip.begin_cancel()
            return self._enqueue_bridge_command_locked(BridgeCommandAction.EXTENDED_CLIP_CANCEL, replace_active=True)

    def poll_bridge_command(self) -> dict[str, Any]:
        with self._lock:
            self.bridge_last_seen_at = datetime.now(timezone.utc).astimezone()
            for command in self.bridge_commands:
                if command.status != BridgeCommandStatus.PENDING:
                    continue
                command.status = BridgeCommandStatus.PROCESSING
                command.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
                return {"command": self._bridge_command_payload(command)}
            return {"command": None}

    def record_bridge_command_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        command_id = str(payload.get("id") or "").strip()
        status_value = str(payload.get("status") or "").strip()
        if not command_id:
            return {"ok": False, "error": "Command id is required"}
        try:
            status = BridgeCommandStatus(status_value)
        except ValueError:
            return {"ok": False, "error": "Unknown command status"}
        if status not in {BridgeCommandStatus.PROCESSING, BridgeCommandStatus.DONE, BridgeCommandStatus.ERROR}:
            return {"ok": False, "error": "Unsupported command status"}

        with self._lock:
            command = self._find_bridge_command(command_id)
            if command is None:
                return {"ok": False, "error": "Command not found"}
            if command.status in {BridgeCommandStatus.DONE, BridgeCommandStatus.ERROR}:
                return {"ok": True, "duplicate": True}
            if command.action == BridgeCommandAction.DISCARD_RECORDING:
                return self._record_discard_result_locked(command, status, payload)
            if command.action in {
                BridgeCommandAction.EXTENDED_CLIP_START,
                BridgeCommandAction.EXTENDED_CLIP_FINISH,
                BridgeCommandAction.EXTENDED_CLIP_CANCEL,
            }:
                return self._record_extended_clip_result_locked(command, status, payload)
            command.status = status
            command.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
            command.result = dict(payload)
            if status == BridgeCommandStatus.PROCESSING:
                return {"ok": True}
            if status == BridgeCommandStatus.ERROR:
                self.last_result = OperationPhase.ERROR.value
                self.last_result_expires_at = self._terminal_expiry(ERROR_STATUS_SECONDS)
                self.last_error = str(payload.get("error") or "OBS bridge command failed.")
                self._finish_operation_locked(command)
                return {"ok": True}
            job_payload = self._job_payload_from_bridge_result(command, payload)
            request = JobCreateRequest.from_payload(job_payload)
            job = self.store.create(request)
            command.job_id = job.id
            self._mark_active_job_locked(job.id)
            self.last_error = None

        thread = threading.Thread(target=self._process_voice_for_operation, args=(job.id, command.id), daemon=True)
        thread.start()
        logger.debug("Bridge command result created async job: command_id=%s job_id=%s", command.id, job.id)
        return {"ok": True, "job_id": job.id, "status": "created"}

    def record_bridge_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = {
            "recording_active": bool(payload.get("recording_active")),
            "recording_paused": bool(payload.get("recording_paused")),
            "replay_buffer_active": bool(payload.get("replay_buffer_active")),
            "recording_output_path": _optional_path_text(payload.get("recording_output_path")),
            "replay_output_path": _optional_path_text(payload.get("replay_output_path")),
        }
        with self._lock:
            was_recording = bool(self.obs_state.get("recording_active")) if self._obs_state_is_fresh() else False
            self.bridge_last_seen_at = datetime.now(timezone.utc).astimezone()
            self.obs_state = state
            self.obs_state_seen_at = self.bridge_last_seen_at
            if not state["recording_active"]:
                self.discard_confirmation_expires_at = None
            session = self.extended_clip.active_session
            if (
                session is not None
                and session.phase == ExtendedClipPhase.CAPTURING
                and was_recording
                and not state["recording_active"]
            ):
                self.extended_clip.manual_recording_stop(state.get("recording_output_path"))
                self.last_result = OperationPhase.DONE.value
                self.last_result_expires_at = datetime.now(timezone.utc).astimezone() + timedelta(seconds=DONE_STATUS_SECONDS)
        return {"ok": True}

    def record_extended_clip_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = str(payload.get("event") or "")
        with self._lock:
            if event == "recording_stopped":
                self.extended_clip.manual_recording_stop(_optional_path_text(payload.get("recording_path")))
                return {"ok": True}
            return {"ok": False, "error": "Unknown Extended Clip bridge event"}

    def manual_voice_test_original_path(self, filename: str) -> Path:
        with self._lock:
            folder = self._obs_output_folder_locked()
            if folder is None:
                folder = self._latest_output_folder_locked()
        return folder / filename if folder else self.config.root / "manual-voice-test" / filename

    def _enqueue_save_action(self, action: BridgeCommandAction) -> dict[str, Any]:
        with self._lock:
            if self._active_command() is not None:
                return {"ok": True, "accepted": False, "reason": "busy"}
            if not self._bridge_is_connected():
                return {"ok": False, "error": "Bridge is not connected"}
            available = self._save_action_availability(action, busy=False)
            if not available["enabled"]:
                return {"ok": True, "accepted": False, "reason": available["reason"]}
            return self._enqueue_bridge_command_locked(action)

    def _enqueue_bridge_command_locked(
        self,
        action: BridgeCommandAction,
        *,
        replace_active: bool = False,
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = datetime.now(timezone.utc).astimezone()
        command = BridgeCommand(
            id=f"{current.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}",
            action=action,
            status=BridgeCommandStatus.PENDING,
            created_at=current.isoformat(),
            policy=dict(policy) if policy else None,
        )
        self.bridge_commands.insert(0, command)
        self.bridge_commands = self.bridge_commands[:25]
        if replace_active or self.active_command_id is None:
            self.active_command_id = command.id
        self.last_result = None
        self.last_result_expires_at = None
        self.last_error = None
        self.discard_confirmation_expires_at = None
        return {"ok": True, "accepted": True, "command_id": command.id}

    def request_shutdown(self) -> dict[str, Any]:
        logger.debug("Backend shutdown requested")
        with self._lock:
            self.mic_level = 0.0
            self.shutdown_requested.set()
        return {"ok": True}

    def apply_runtime_config(self) -> None:
        logger.debug(
            "Applying runtime config: audio.device=%s stt.engine=%s stt.model_path=%s",
            self.config.audio.get("device"),
            self.config.stt.get("engine"),
            self.config.stt.get("model_path"),
        )
        self.audio_recorder = build_audio_recorder(self.config)
        self.stt_engine = build_stt_engine(self.config)
        self.media_renamer = build_media_renamer(self.config)
        self.sound_player = build_listening_sound_player(self.config)
        self.mic_level = 0.0

    def system_checks(self) -> dict[str, dict[str, str | bool]]:
        model_error = self.stt_engine.readiness_error()
        microphone_error = self.audio_recorder.readiness_error()
        logger.debug("System checks: model_error=%s microphone_error=%s", model_error, microphone_error)
        return {
            "config": {"ok": True, "message": "Config loaded"},
            "model": {
                "ok": model_error is None,
                "message": model_error or "Model found",
            },
            "microphone": {
                "ok": microphone_error is None,
                "message": microphone_error or "Microphone available",
            },
        }

    def _process_voice(self, job_id: str) -> None:
        try:
            logger.debug("Voice pipeline started: job_id=%s", job_id)
            readiness_error = self.stt_engine.readiness_error()
            if readiness_error:
                logger.warning("Voice pipeline blocked by STT readiness: job_id=%s error=%s", job_id, readiness_error)
                with self._lock:
                    self.store.fail(job_id, readiness_error)
                    self._finish_active_job_locked(job_id, OperationPhase.ERROR.value, readiness_error)
                return
            microphone_error = self.audio_recorder.readiness_error()
            if microphone_error:
                logger.warning("Voice pipeline blocked by microphone readiness: job_id=%s error=%s", job_id, microphone_error)
                with self._lock:
                    self.store.fail(job_id, microphone_error)
                    self._finish_active_job_locked(job_id, OperationPhase.ERROR.value, microphone_error)
                return
            with self._lock:
                self.store.update_status(job_id, "waiting_for_voice")
                self.store.update_status(job_id, "listening")
                self.listening_started_at = datetime.now(timezone.utc).astimezone()
            logger.debug("Listening started: job_id=%s", job_id)
            self.sound_player.listening_started()
            try:
                audio = self.audio_recorder.record(on_level=self._set_mic_level)
            finally:
                self.sound_player.listening_finished()
                self._set_mic_level(0.0)
                with self._lock:
                    self.listening_started_at = None
                logger.debug("Listening finished: job_id=%s", job_id)
            logger.debug("Voice pipeline recorded audio: job_id=%s bytes=%s", job_id, len(audio.data or b""))
            with self._lock:
                self.store.update_status(job_id, "transcribing")
            result = self.stt_engine.transcribe(audio, language=str(self.config.stt.get("language") or "") or None)
            transcript = result.text.strip()
            logger.debug("Voice pipeline transcription completed: job_id=%s transcript=%r", job_id, transcript)
            if not transcript:
                with self._lock:
                    self.store.fail(job_id, "Speech recognition returned empty text.")
                    self._finish_active_job_locked(job_id, OperationPhase.ERROR.value, "Speech recognition returned empty text.")
                return
            with self._lock:
                job = self.store.update_transcript(job_id, transcript)
            final_path = self.media_renamer.rename(job, transcript)
            with self._lock:
                self.store.complete(job_id, str(final_path))
                self._finish_active_job_locked(job_id, OperationPhase.DONE.value, None)
            logger.debug("Voice pipeline completed: job_id=%s final_path=%s", job_id, final_path)
        except (AudioRecorderError, SpeechToTextError, RenameError) as error:
            logger.exception("Voice pipeline failed: job_id=%s", job_id)
            with self._lock:
                self.store.fail(job_id, str(error))
                self._finish_active_job_locked(job_id, OperationPhase.ERROR.value, str(error))

    def _process_voice_for_operation(self, job_id: str, command_id: str) -> None:
        self._process_voice(job_id)
        with self._lock:
            job = self._job_by_id(job_id)
            command = self._find_bridge_command(command_id)
            if command is None:
                return
            if job and job.status == "done":
                command.status = BridgeCommandStatus.DONE
            else:
                self._finish_active_job_locked(
                    job_id,
                    OperationPhase.ERROR.value,
                    job.error if job else "Job disappeared before completion.",
                )
                command.status = BridgeCommandStatus.ERROR
            command.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
            self._finish_operation_locked(command)

    def _record_extended_clip_result_locked(
        self,
        command: BridgeCommand,
        status: BridgeCommandStatus,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        command.status = status
        command.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
        command.result = dict(payload)
        if status == BridgeCommandStatus.PROCESSING:
            event = str(payload.get("event") or "")
            if command.action == BridgeCommandAction.EXTENDED_CLIP_START:
                if event == "recording_started":
                    self.extended_clip.mark_recording_started()
                elif event == "saving_replay":
                    self.extended_clip.mark_saving_replay()
            return {"ok": True}
        if status == BridgeCommandStatus.ERROR:
            error = str(payload.get("error") or "OBS bridge command failed.")
            self.extended_clip.fail(error)
            self.last_result = OperationPhase.ERROR.value
            self.last_error = error
            self.last_result_expires_at = self._terminal_expiry(ERROR_STATUS_SECONDS)
            self._finish_operation_locked(command)
            return {"ok": True}
        if command.action == BridgeCommandAction.EXTENDED_CLIP_START:
            replay_path = str(payload.get("replay_path") or payload.get("original_path") or "").strip()
            if not replay_path:
                self.extended_clip.fail("OBS did not provide an Extended Clip replay path.")
                command.status = BridgeCommandStatus.ERROR
                self._finish_operation_locked(command)
                return {"ok": False, "error": "Replay path is required"}
            self.extended_clip.mark_capturing(replay_path, payload)
            self._finish_operation_locked(command)
            return {"ok": True}
        if command.action == BridgeCommandAction.EXTENDED_CLIP_CANCEL:
            self.extended_clip.cancel(_optional_path_text(payload.get("recording_path")))
            self.last_result = OperationPhase.DONE.value
            self.last_result_expires_at = datetime.now(timezone.utc).astimezone() + timedelta(seconds=DONE_STATUS_SECONDS)
            self._finish_operation_locked(command)
            return {"ok": True}
        recording_path = str(payload.get("recording_path") or payload.get("original_path") or "").strip()
        if not recording_path:
            self.extended_clip.fail("OBS did not provide an Extended Clip recording path.")
            command.status = BridgeCommandStatus.ERROR
            self._finish_operation_locked(command)
            return {"ok": False, "error": "Recording path is required"}
        command.status = BridgeCommandStatus.PROCESSING
        thread = threading.Thread(
            target=self._process_extended_clip,
            args=(command.id, recording_path, dict(payload)),
            daemon=True,
        )
        thread.start()
        return {"ok": True, "status": "processing"}

    def _record_discard_result_locked(
        self,
        command: BridgeCommand,
        status: BridgeCommandStatus,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        command.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
        if status == BridgeCommandStatus.PROCESSING:
            if not command.backend_processing:
                command.status = BridgeCommandStatus.PROCESSING
                command.result = dict(payload)
            return {"ok": True}
        if command.backend_processing:
            return {"ok": True, "duplicate": True}
        if status == BridgeCommandStatus.ERROR:
            technical_error = str(payload.get("error") or "OBS bridge discard command failed.")
            logger.error("Discard bridge command failed: command_id=%s error=%s", command.id, technical_error)
            command.status = BridgeCommandStatus.ERROR
            command.result = dict(payload)
            self.last_result = OperationPhase.ERROR.value
            self.last_result_expires_at = self._terminal_expiry(ERROR_STATUS_SECONDS)
            self.last_error = DISCARD_PUBLIC_ERROR
            self._finish_operation_locked(command)
            return {"ok": True}
        command.status = BridgeCommandStatus.PROCESSING
        command.result = dict(payload)
        command.backend_processing = True
        self.obs_state["recording_active"] = False
        thread = threading.Thread(
            target=self._process_discard_recording,
            args=(command.id, dict(payload)),
            daemon=True,
        )
        thread.start()
        return {"ok": True, "status": "processing"}

    def _process_discard_recording(self, command_id: str, payload: dict[str, Any]) -> None:
        try:
            with self._lock:
                command = self._find_bridge_command(command_id)
                if command is None:
                    return
                policy = dict(command.policy or {})
            result = self.discard_recording_service.discard(
                str(payload.get("recording_path") or ""),
                str(payload.get("recording_output_root") or ""),
                mode=str(policy.get("mode") or DISCARD_MODE_MOVE),
                folder_name=str(policy.get("folder_name") or DEFAULT_DISCARD_FOLDER_NAME),
            )
            logger.info(
                "Discard completed: command_id=%s mode=%s source=%s destination=%s",
                command_id,
                result.mode,
                result.source_path,
                result.destination_path,
            )
            with self._lock:
                command = self._find_bridge_command(command_id)
                if command is None:
                    return
                command.status = BridgeCommandStatus.DONE
                command.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
                command.result = {
                    **payload,
                    "discard_mode": result.mode,
                    "discard_destination": str(result.destination_path) if result.destination_path else None,
                }
                self.last_result = OperationPhase.DONE.value
                self.last_result_expires_at = self._terminal_expiry(DONE_STATUS_SECONDS)
                self.last_error = None
                self._finish_operation_locked(command)
        except (DiscardRecordingError, OSError) as error:
            logger.exception("Discard processing failed: command_id=%s", command_id)
            with self._lock:
                command = self._find_bridge_command(command_id)
                if command is None:
                    return
                command.status = BridgeCommandStatus.ERROR
                command.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
                command.result = {**payload, "error": str(error)}
                self.last_result = OperationPhase.ERROR.value
                self.last_result_expires_at = self._terminal_expiry(ERROR_STATUS_SECONDS)
                self.last_error = DISCARD_PUBLIC_ERROR
                self._finish_operation_locked(command)

    def _process_extended_clip(self, command_id: str, recording_path: str, metadata: dict[str, Any]) -> None:
        try:
            result = self.extended_clip.merge(recording_path)
            with self._lock:
                session = self.extended_clip.active_session
                request = JobCreateRequest.from_payload(
                    {
                        "type": "extended_clip",
                        "original_path": str(result.output_path),
                        "game_hint": metadata.get("game_hint") or (session.game_hint if session else None),
                        "source_title": metadata.get("source_title") or (session.source_title if session else None),
                        "created_by": "extended_clip",
                    }
                )
                job = self.store.create(request)
                command = self._find_bridge_command(command_id)
                if command:
                    command.job_id = job.id
                self._mark_active_job_locked(job.id)
                self.extended_clip.mark_naming()
            self._process_voice(job.id)
            with self._lock:
                completed_job = self._job_by_id(job.id)
                command = self._find_bridge_command(command_id)
                if completed_job and completed_job.status == "done" and completed_job.final_path:
                    self.extended_clip.complete(completed_job.final_path)
                    if command:
                        command.status = BridgeCommandStatus.DONE
                else:
                    error = completed_job.error if completed_job else "Extended Clip naming job disappeared."
                    self.extended_clip.fail(error or "Extended Clip naming failed.")
                    if command:
                        command.status = BridgeCommandStatus.ERROR
                if command:
                    command.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
                    self._finish_operation_locked(command)
        except (ExtendedClipMergeError, OSError, ValueError) as error:
            logger.exception("Extended Clip processing failed: command_id=%s", command_id)
            with self._lock:
                self.extended_clip.fail(str(error))
                self.last_result = OperationPhase.ERROR.value
                self.last_error = str(error)
                self.last_result_expires_at = self._terminal_expiry(ERROR_STATUS_SECONDS)
                command = self._find_bridge_command(command_id)
                if command:
                    command.status = BridgeCommandStatus.ERROR
                    command.updated_at = datetime.now(timezone.utc).astimezone().isoformat()
                    self._finish_operation_locked(command)

    def _set_mic_level(self, value: float) -> None:
        self.mic_level = max(0.0, min(1.0, value))
        logger.debug("Mic level updated: %s", self.mic_level)

    def _listening_elapsed_seconds(self) -> float:
        if self.listening_started_at is None:
            return 0.0
        elapsed = datetime.now(timezone.utc).astimezone() - self.listening_started_at
        return max(0.0, elapsed.total_seconds())

    def _listening_remaining_seconds(self) -> float:
        max_seconds = float(self.config.audio.get("max_record_seconds", 8))
        return max(0.0, max_seconds - self._listening_elapsed_seconds())

    def job_for_ui(self, job: dict[str, Any]) -> dict[str, Any]:
        original_path = str(job.get("original_path") or "")
        final_path = str(job.get("final_path") or "")
        selected_path = final_path or original_path
        folder = str(Path(selected_path).parent) if selected_path else ""
        output_filename = Path(final_path).name if final_path else ""
        final = _path_or_none(final_path)
        output_folder = _path_or_none(folder)
        return {
            "id": str(job.get("id") or ""),
            "type": self._job_type_label(str(job.get("type") or "")),
            "status": str(job.get("status") or ""),
            "game": str(job.get("game") or ""),
            "transcript": job.get("transcript"),
            "original_path": original_path,
            "final_path": final_path or None,
            "output_filename": output_filename,
            "folder": folder or None,
            "error": job.get("error"),
            "updated_at": str(job.get("updated_at") or ""),
            "can_open_folder": bool((final and final.exists()) or (output_folder and output_folder.exists())),
        }

    def _job_type_label(self, job_type: str) -> str:
        tokens = dict(self.config.naming.get("job_type_tokens", {}))
        return str(tokens.get(job_type) or job_type)

    def _bridge_status(self) -> str:
        if self._bridge_is_connected():
            return "connected"
        return "waiting"

    def _bridge_is_connected(self) -> bool:
        if self.bridge_last_seen_at is None:
            return False
        elapsed = datetime.now(timezone.utc).astimezone() - self.bridge_last_seen_at
        return elapsed.total_seconds() <= BRIDGE_HEARTBEAT_SECONDS

    def _obs_state_is_fresh(self) -> bool:
        if self.obs_state_seen_at is None:
            return False
        elapsed = datetime.now(timezone.utc).astimezone() - self.obs_state_seen_at
        return elapsed.total_seconds() <= OBS_STATE_HEARTBEAT_SECONDS

    def _obs_status_payload(self) -> dict[str, Any]:
        fresh = self._obs_state_is_fresh()
        return {
            "recording_active": bool(self.obs_state.get("recording_active")) if fresh else None,
            "recording_paused": bool(self.obs_state.get("recording_paused")) if fresh else None,
            "replay_buffer_active": bool(self.obs_state.get("replay_buffer_active")) if fresh else None,
            "recording_output_path": self.obs_state.get("recording_output_path") if fresh else None,
            "replay_output_path": self.obs_state.get("replay_output_path") if fresh else None,
            "fresh": fresh,
        }

    def _obs_output_folder_locked(self) -> Path | None:
        if not self._obs_state_is_fresh():
            return None
        for key in ("replay_output_path", "recording_output_path"):
            folder = _folder_from_path_text(self.obs_state.get(key))
            if folder:
                return folder
        return None

    def _latest_output_folder_locked(self) -> Path | None:
        jobs = self.store.list()
        if not jobs:
            return None
        job = jobs[0].to_dict()
        final_path = _path_or_none(job.get("final_path"))
        if final_path:
            return final_path.parent
        original_path = _path_or_none(job.get("original_path"))
        if original_path:
            return original_path.parent
        return None

    def _action_availability_payload(self, *, busy: bool) -> dict[str, dict[str, Any]]:
        discard = self._discard_action_availability(busy=busy)
        confirmation_armed = discard["enabled"] and self._discard_confirmation_is_armed_locked()
        if not discard["enabled"]:
            self.discard_confirmation_expires_at = None
        discard = {
            **discard,
            "confirmation_armed": confirmation_armed,
            "confirmation_expires_in_ms": self._discard_confirmation_remaining_ms_locked()
            if confirmation_armed
            else 0,
        }
        return {
            "save_moment": self._save_action_availability(BridgeCommandAction.SAVE_MOMENT, busy=busy),
            "save_recording": self._save_action_availability(BridgeCommandAction.SAVE_RECORDING, busy=busy),
            "discard_recording": discard,
            "extended_clip_start": self._extended_action_availability("extended_clip_start"),
            "extended_clip_finish": self._extended_action_availability("extended_clip_finish"),
            "extended_clip_cancel": self._extended_action_availability("extended_clip_cancel"),
        }

    def _save_action_availability(self, action: BridgeCommandAction, *, busy: bool) -> dict[str, Any]:
        session = self.extended_clip.active_session
        if action == BridgeCommandAction.SAVE_RECORDING and session is not None:
            return {"enabled": False, "reason": "extended_clip_active"}
        if action == BridgeCommandAction.SAVE_MOMENT and session is not None:
            if session.phase != ExtendedClipPhase.CAPTURING:
                return {"enabled": False, "reason": "extended_clip_active"}
        if busy:
            return {"enabled": False, "reason": "busy"}
        if not self._bridge_is_connected():
            return {"enabled": False, "reason": "bridge_disconnected"}
        if not self._obs_state_is_fresh():
            return {"enabled": True, "reason": None}
        if action == BridgeCommandAction.SAVE_MOMENT and not self.obs_state.get("replay_buffer_active"):
            return {"enabled": False, "reason": "replay_buffer_inactive"}
        if action == BridgeCommandAction.SAVE_RECORDING and not self.obs_state.get("recording_active"):
            return {"enabled": False, "reason": "recording_inactive"}
        return {"enabled": True, "reason": None}

    def _discard_action_availability(self, *, busy: bool) -> dict[str, Any]:
        if not self._bridge_is_connected():
            return {"enabled": False, "reason": "bridge_disconnected"}
        if not self._obs_state_is_fresh():
            return {"enabled": False, "reason": "obs_state_stale"}
        if self.extended_clip.active_session is not None:
            return {"enabled": False, "reason": "extended_clip_active"}
        if busy:
            return {"enabled": False, "reason": "busy"}
        if not self.obs_state.get("recording_active"):
            return {"enabled": False, "reason": "recording_inactive"}
        return {"enabled": True, "reason": None}

    def _extended_action_availability(self, name: str) -> dict[str, Any]:
        if not bool(self.config.extended_clip.get("enabled", True)):
            return {"enabled": False, "reason": "feature_disabled"}
        if not self._bridge_is_connected():
            return {"enabled": False, "reason": "bridge_disconnected"}
        if not self._obs_state_is_fresh():
            return {"enabled": False, "reason": "obs_state_stale"}
        session = self.extended_clip.active_session
        active_command = self._active_command()
        active_job = self._active_job(active_command)
        ordinary_busy = active_command is not None or active_job is not None
        if name == "extended_clip_start":
            if session is not None:
                return {"enabled": False, "reason": "extended_clip_active"}
            if ordinary_busy:
                return {"enabled": False, "reason": "operation_busy"}
            if self.obs_state.get("recording_active"):
                return {"enabled": False, "reason": "recording_already_active"}
            if not self.obs_state.get("replay_buffer_active"):
                return {"enabled": False, "reason": "replay_buffer_inactive"}
            return {"enabled": True, "reason": None}
        if session is None:
            return {"enabled": False, "reason": "extended_clip_inactive"}
        if name == "extended_clip_finish":
            if session.phase != ExtendedClipPhase.CAPTURING:
                reason = "processing_committed" if session.stage == "processing" else "operation_busy"
                return {"enabled": False, "reason": reason}
            if ordinary_busy:
                return {"enabled": False, "reason": "operation_busy"}
            return {"enabled": True, "reason": None}
        if name == "extended_clip_cancel":
            if session.phase not in {
                ExtendedClipPhase.STARTING_RECORDING,
                ExtendedClipPhase.WAITING_OVERLAP,
                ExtendedClipPhase.SAVING_REPLAY,
                ExtendedClipPhase.CAPTURING,
            }:
                return {"enabled": False, "reason": "processing_committed"}
            return {"enabled": True, "reason": None}
        return {"enabled": False, "reason": "unknown_action"}

    def _active_command(self) -> BridgeCommand | None:
        if not self.active_command_id:
            return None
        command = self._find_bridge_command(self.active_command_id)
        if command is None or command.status in {BridgeCommandStatus.DONE, BridgeCommandStatus.ERROR}:
            return None
        return command

    def _find_bridge_command(self, command_id: str) -> BridgeCommand | None:
        for command in self.bridge_commands:
            if command.id == command_id:
                return command
        return None

    def _bridge_command_payload(self, command: BridgeCommand) -> dict[str, Any]:
        return {
            "id": command.id,
            "action": command.action.value,
            "created_at": command.created_at,
        }

    def _job_payload_from_bridge_result(self, command: BridgeCommand, payload: dict[str, Any]) -> dict[str, Any]:
        job_type = "moment" if command.action == BridgeCommandAction.SAVE_MOMENT else "recording"
        result = {
            "type": job_type,
            "original_path": payload.get("original_path"),
            "game_hint": payload.get("game_hint"),
            "scene_name": payload.get("scene_name"),
            "source_name": payload.get("source_name"),
            "source_title": payload.get("source_title"),
            "created_by": "obs_bridge",
        }
        return {key: value for key, value in result.items() if value is not None}

    def _operation_phase(
        self,
        command: BridgeCommand | None,
        active_job_status: str | None,
    ) -> OperationPhase:
        if active_job_status == "listening" or active_job_status == "waiting_for_voice":
            return OperationPhase.LISTENING
        if active_job_status == "transcribing":
            return OperationPhase.TRANSCRIBING
        if active_job_status == "renaming":
            return OperationPhase.RENAMING
        if active_job_status == "done":
            return OperationPhase.DONE
        if active_job_status == "error":
            return OperationPhase.ERROR
        if command is None:
            if self.last_result == OperationPhase.DONE.value and self._last_result_is_visible():
                return OperationPhase.DONE
            if self.last_result == OperationPhase.ERROR.value and self._last_result_is_visible():
                return OperationPhase.ERROR
            return OperationPhase.IDLE
        if command.job_id:
            return OperationPhase.WAITING_FOR_FILE
        if command.status == BridgeCommandStatus.PENDING:
            return OperationPhase.COMMAND_SENT
        if command.status == BridgeCommandStatus.PROCESSING:
            return OperationPhase.WAITING_FOR_OBS
        if command.status == BridgeCommandStatus.ERROR:
            return OperationPhase.ERROR
        if command.status == BridgeCommandStatus.DONE:
            return OperationPhase.DONE
        return OperationPhase.IDLE

    def _ui_state(self, operation_phase: OperationPhase, active_job_status: str | None) -> str:
        if not self._bridge_is_connected():
            return "offline"
        session = self.extended_clip.active_session
        if operation_phase == OperationPhase.ERROR or (self.extended_clip.session and self.extended_clip.session.phase == ExtendedClipPhase.ERROR):
            return "error"
        if active_job_status in {"listening", "waiting_for_voice"}:
            return "listening"
        if session is not None and session.stage == "processing":
            return "processing"
        if session is not None and session.stage == "recording":
            return "recording"
        if operation_phase in {
            OperationPhase.COMMAND_SENT,
            OperationPhase.WAITING_FOR_OBS,
            OperationPhase.WAITING_FOR_FILE,
            OperationPhase.TRANSCRIBING,
            OperationPhase.RENAMING,
        }:
            return "processing"
        if operation_phase == OperationPhase.DONE:
            return "done"
        return "ready"

    def _job_for_command(self, command: BridgeCommand | None):
        if not command or not command.job_id:
            return None
        return self._job_by_id(command.job_id)

    def _active_job(self, command: BridgeCommand | None):
        command_job = self._job_for_command(command)
        if command_job:
            return command_job
        if not self.active_job_id:
            return None
        job = self._job_by_id(self.active_job_id)
        if job is None or job.status in {"done", "error"}:
            return None
        return job

    def _job_by_id(self, job_id: str):
        for job in self.store.list():
            if job.id == job_id:
                return job
        return None

    def _mark_active_job_locked(self, job_id: str) -> None:
        self.active_job_id = job_id
        self.last_result = None
        self.last_result_expires_at = None
        self.last_error = None

    def _finish_active_job_locked(self, job_id: str, result: str, error: str | None) -> None:
        if self.active_job_id == job_id:
            self.active_job_id = None
        self.last_result = result
        self.last_error = error
        duration = DONE_STATUS_SECONDS if result == OperationPhase.DONE.value else ERROR_STATUS_SECONDS
        self.last_result_expires_at = self._terminal_expiry(duration)

    def _last_result_is_visible(self) -> bool:
        if self.last_result_expires_at is None:
            return False
        return datetime.now(timezone.utc).astimezone() <= self.last_result_expires_at

    def _expire_terminal_result_locked(self) -> None:
        if self.last_result is None or self._last_result_is_visible():
            return
        self.last_result = None
        self.last_result_expires_at = None
        self.last_error = None

    def _terminal_expiry(self, seconds: float) -> datetime:
        return datetime.now(timezone.utc).astimezone() + timedelta(seconds=seconds)

    def _discard_confirmation_is_armed_locked(self, now: datetime | None = None) -> bool:
        if self.discard_confirmation_expires_at is None:
            return False
        current = now or datetime.now(timezone.utc).astimezone()
        if current >= self.discard_confirmation_expires_at:
            self.discard_confirmation_expires_at = None
            return False
        return True

    def _discard_confirmation_remaining_ms_locked(self) -> int:
        if not self._discard_confirmation_is_armed_locked():
            return 0
        assert self.discard_confirmation_expires_at is not None
        remaining = self.discard_confirmation_expires_at - datetime.now(timezone.utc).astimezone()
        return max(0, int(remaining.total_seconds() * 1000))

    def _finish_operation_locked(self, command: BridgeCommand) -> None:
        if self.active_command_id == command.id:
            self.active_command_id = None


def _path_or_none(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text) if text else None


def _optional_path_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _folder_from_path_text(value: Any) -> Path | None:
    path = _path_or_none(value)
    if not path:
        return None
    return path.parent


def _folder_for_job(job: dict[str, Any]) -> Path | None:
    selected = _path_or_none(job.get("final_path")) or _path_or_none(job.get("original_path"))
    if not selected:
        return None
    return selected.parent


def _open_in_explorer(path: Path, *, select: bool) -> None:
    if sys.platform == "win32":
        if select:
            subprocess.Popen(["explorer", f"/select,{path}"])  # noqa: S603,S607
            return
        os.startfile(path)  # type: ignore[attr-defined]
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(path)])  # noqa: S603,S607
