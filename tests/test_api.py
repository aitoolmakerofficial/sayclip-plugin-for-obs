from pathlib import Path
from datetime import timedelta
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import time

from instant_easy_rename_server.api import BackendApi, BridgeCommandAction, BridgeCommandStatus, OperationPhase
from instant_easy_rename_server.audio import AudioPayload, FakeAudioRecorder
from instant_easy_rename_server.config import load_config
from instant_easy_rename_server.jobs import Job
from instant_easy_rename_server.server import create_server
from instant_easy_rename_server.use_cases.extended_clip import ExtendedClipMergeResult, ExtendedClipService
from instant_easy_rename_server.stt import FakeSpeechToTextEngine


class NoopRenamer:
    def rename(self, job: Job, transcript: str) -> Path:
        del transcript
        return Path(job.original_path)


def test_health_contract(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))

    assert api.health() == {
        "app": "SayClip",
        "version": "2.0.0",
        "status": "ok",
    }


def test_valid_recording_and_moment_jobs(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    recording_path = tmp_path / "Test Game" / "2026-05-27 21-31-12.mkv"
    moment_path = tmp_path / "Test Game" / "Replays" / "2026-05-27 22-10-44.mkv"
    recording_path.parent.mkdir(parents=True)
    moment_path.parent.mkdir(parents=True)
    recording_path.write_bytes(b"recording")
    moment_path.write_bytes(b"moment")

    recording = api.create_job(
        {
            "type": "recording",
            "original_path": str(recording_path),
        }
    )
    moment = api.create_job(
        {
            "type": "moment",
            "original_path": str(moment_path),
        }
    )

    assert recording["status"] == "done"
    assert moment["status"] == "done"
    assert len(api.list_jobs()["jobs"]) == 2


def test_invalid_job_schema_rejected(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))

    for payload in [{"type": "clip", "original_path": "x.mkv"}, {"type": "moment"}]:
        try:
            api.create_job(payload)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid payload was accepted")


def test_http_health_and_create_job(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    config.data["backend"]["port"] = 0
    original_path = tmp_path / "Test Game" / "2026-05-27 21-31-12.mkv"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"recording")
    server = create_server(BackendApi(config))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        health = _get_json(f"http://{host}:{port}/health")
        created = _post_json(
            f"http://{host}:{port}/jobs",
                {
                    "type": "recording",
                    "original_path": str(original_path),
                    "created_by": "obs_bridge",
                },
            )
        listed = _get_json(f"http://{host}:{port}/jobs")
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert health["status"] == "ok"
    assert created["status"] == "created"
    assert listed["jobs"][0]["id"] == created["job_id"]


def test_http_create_job_returns_before_voice_pipeline_finishes(tmp_path: Path) -> None:
    class SlowRecorder(FakeAudioRecorder):
        def record(self, *, on_level=None):
            time.sleep(0.3)
            return AudioPayload(data=b"known-audio")

    config = load_config(tmp_path)
    config.data["backend"]["port"] = 0
    original_path = tmp_path / "Game" / "clip.mkv"
    original_path.parent.mkdir()
    original_path.write_bytes(b"recording")
    server = create_server(BackendApi(config, audio_recorder=SlowRecorder()))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        started = time.monotonic()
        created = _post_json(
            f"http://{host}:{port}/jobs",
            {"type": "recording", "original_path": str(original_path)},
        )
        elapsed = time.monotonic() - started
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            listed = _get_json(f"http://{host}:{port}/jobs")
            if listed["jobs"][0]["status"] in {"done", "error"}:
                break
            time.sleep(0.02)
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert created["status"] == "created"
    assert elapsed < 0.25


def test_http_invalid_type_returns_422(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    config.data["backend"]["port"] = 0
    server = create_server(BackendApi(config))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        try:
            _post_json(
                f"http://{host}:{port}/jobs",
                {"type": "clip", "original_path": "clip.mkv"},
            )
        except HTTPError as error:
            assert error.code == 422
        else:
            raise AssertionError("invalid request was accepted")
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_http_records_and_lists_errors(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    config.data["backend"]["port"] = 0
    server = create_server(BackendApi(config))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        accepted = _post_json(
            f"http://{host}:{port}/events/error",
            {"message": "rename failed", "path": "D:/Recordings/example.mkv"},
        )
        listed = _get_json(f"http://{host}:{port}/errors")
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert accepted["status"] == "accepted"
    assert listed["errors"][0]["message"] == "rename failed"


def test_status_returns_valid_json(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))

    state = api.status()

    assert state["backend"] == "ok"
    assert state["bridge"] == "waiting"
    assert state["busy"] is False
    assert state["phase"] == "idle"
    assert state["obs"] == {
        "recording_active": None,
        "recording_paused": None,
        "replay_buffer_active": None,
        "recording_output_path": None,
        "replay_output_path": None,
        "fresh": False,
    }
    assert state["actions"]["save_moment"]["reason"] == "bridge_disconnected"
    assert state["actions"]["save_recording"]["reason"] == "bridge_disconnected"
    assert "mic" in state
    assert "last_job" not in state


def test_job_for_ui_returns_latest_job_shape(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    original_path = tmp_path / "Test Game" / "clip.mkv"
    original_path.parent.mkdir()
    original_path.write_bytes(b"recording")

    api.create_job({"type": "moment", "original_path": str(original_path), "source_title": "Test Game"})
    job = api.job_for_ui(api.list_jobs()["jobs"][0])

    assert job["type"] == "clip"
    assert job["game"] == "test-game"
    assert job["status"] == "done"
    assert job["output_filename"].endswith(".mkv")
    assert job["can_open_folder"] is True


def test_dock_open_folder_returns_controlled_error_with_no_folder(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))

    result = api.open_latest_output_folder()

    assert result == {"ok": False, "error": "No output folder available"}


def test_save_action_requires_connected_bridge(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))

    result = api.save_moment()

    assert result == {"ok": False, "error": "Bridge is not connected"}


def test_bridge_state_controls_save_action_availability(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))

    accepted = api.record_bridge_state(
        {
            "recording_active": True,
            "recording_paused": False,
            "replay_buffer_active": False,
        }
    )
    state = api.status()
    moment = api.save_moment()
    recording = api.save_recording()

    assert accepted == {"ok": True}
    assert state["bridge"] == "connected"
    assert state["obs"]["recording_active"] is True
    assert state["obs"]["replay_buffer_active"] is False
    assert state["actions"]["save_moment"] == {"enabled": False, "reason": "replay_buffer_inactive"}
    assert state["actions"]["save_recording"] == {"enabled": True, "reason": None}
    assert moment == {"ok": True, "accepted": False, "reason": "replay_buffer_inactive"}
    assert recording["accepted"] is True


def test_manual_voice_test_uses_fresh_obs_output_folder(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    replay_path = tmp_path / "OBS Output" / "Replay.mkv"

    api.record_bridge_state(
        {
            "recording_active": True,
            "recording_paused": False,
            "replay_buffer_active": True,
            "recording_output_path": str(tmp_path / "OBS Output" / "Recording.mkv"),
            "replay_output_path": str(replay_path),
        }
    )

    assert api.manual_voice_test_original_path("test.mkv") == replay_path.with_name("test.mkv")


def test_bridge_command_flow_creates_job_from_done_result(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    original_path = tmp_path / "Game" / "clip.mkv"
    original_path.parent.mkdir()
    original_path.write_bytes(b"recording")

    assert api.poll_bridge_command() == {"command": None}
    created = api.save_recording()
    polled = api.poll_bridge_command()
    processing = api.record_bridge_command_result({"id": created["command_id"], "status": "processing"})
    done = api.record_bridge_command_result(
        {
            "id": created["command_id"],
            "status": "done",
            "original_path": str(original_path),
            "source_title": "Game",
        }
    )
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and api.status()["busy"]:
        time.sleep(0.02)
    polled_again = api.poll_bridge_command()

    assert created["ok"] is True
    assert created["accepted"] is True
    assert polled["command"]["action"] == "save_recording"
    assert processing == {"ok": True}
    assert done["ok"] is True
    assert api.list_jobs()["jobs"][0]["type"] == "recording"
    assert polled_again == {"command": None}


def test_status_tracks_active_job_and_expires_done_result(tmp_path: Path) -> None:
    class SlowRecorder(FakeAudioRecorder):
        def record(self, *, on_level=None):
            time.sleep(0.3)
            return AudioPayload(data=b"known-audio")

    api = BackendApi(
        load_config(tmp_path),
        audio_recorder=SlowRecorder(),
        stt_engine=FakeSpeechToTextEngine("stream deck title"),
        media_renamer=NoopRenamer(),
    )
    original_path = tmp_path / "Game" / "clip.mkv"
    original_path.parent.mkdir()
    original_path.write_bytes(b"recording")

    api.poll_bridge_command()
    created = api.save_recording()
    api.poll_bridge_command()
    result = api.record_bridge_command_result(
        {
            "id": created["command_id"],
            "status": "done",
            "original_path": str(original_path),
            "source_title": "Game",
        }
    )

    listening_state = _wait_for_phase(api, "listening")
    done_state = _wait_for_phase(api, "done")
    idle_state = _wait_for_phase(api, "idle", timeout=4)

    assert result["ok"] is True
    assert listening_state["busy"] is True
    assert listening_state["active_job_id"] == result["job_id"]
    assert done_state["last_result"] == "done"
    assert idle_state["busy"] is False
    assert idle_state["active_job_id"] is None


def test_save_action_returns_busy_while_operation_active(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    api.poll_bridge_command()

    first = api.save_moment()
    second = api.save_recording()

    assert first["accepted"] is True
    assert second == {"ok": True, "accepted": False, "reason": "busy"}


def test_bridge_command_result_error_updates_status(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    api.poll_bridge_command()
    created = api.save_moment()
    api.poll_bridge_command()

    result = api.record_bridge_command_result(
        {"id": created["command_id"], "status": "error", "error": "Replay buffer is not active."}
    )

    assert result == {"ok": True}
    assert api.status()["phase"] == "error"
    assert api.status()["last_error"] == "Replay buffer is not active."


def test_action_specific_bridge_error_does_not_mark_connected_bridge_offline_or_error(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    api.poll_bridge_command()

    api.record_error(
        {
            "source": "obs_bridge",
            "message": "Recording is not active.",
            "details": {"operation": "stop_recording"},
        }
    )

    state = api.status()
    assert state["bridge"] == "connected"
    assert state["busy"] is False


def test_valid_save_action_can_follow_action_specific_bridge_error(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    api.poll_bridge_command()
    api.record_error(
        {
            "source": "obs_bridge",
            "message": "Recording is not active.",
            "details": {"operation": "stop_recording"},
        }
    )

    created = api.save_moment()
    polled = api.poll_bridge_command()

    assert created["ok"] is True
    assert created["accepted"] is True
    assert polled["command"]["action"] == "save_moment"


def test_contract_enums_keep_expected_values() -> None:
    assert BridgeCommandAction.SAVE_MOMENT.value == "save_moment"
    assert BridgeCommandAction.SAVE_RECORDING.value == "save_recording"
    assert BridgeCommandAction.DISCARD_RECORDING.value == "discard_recording"
    assert BridgeCommandAction.EXTENDED_CLIP_START.value == "extended_clip_start"
    assert BridgeCommandAction.EXTENDED_CLIP_FINISH.value == "extended_clip_finish"
    assert BridgeCommandAction.EXTENDED_CLIP_CANCEL.value == "extended_clip_cancel"
    assert BridgeCommandStatus.PROCESSING.value == "processing"
    assert OperationPhase.LISTENING.value == "listening"


def test_discard_confirmation_is_shared_and_second_call_enqueues_command(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    api.record_bridge_state(
        {"recording_active": True, "recording_paused": False, "replay_buffer_active": False}
    )

    first = api.discard_recording()
    armed = api.status()["actions"]["discard_recording"]
    second = api.discard_recording()
    command = api.poll_bridge_command()["command"]

    assert first["accepted"] is False
    assert first["confirmation_armed"] is True
    assert armed["confirmation_armed"] is True
    assert 0 < armed["confirmation_expires_in_ms"] <= 2000
    assert second["accepted"] is True
    assert command["action"] == "discard_recording"


def test_discard_rejects_inactive_recording_without_arming(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    api.record_bridge_state(
        {"recording_active": False, "recording_paused": False, "replay_buffer_active": True}
    )

    result = api.discard_recording()
    action = api.status()["actions"]["discard_recording"]

    assert result == {"ok": True, "accepted": False, "reason": "recording_inactive"}
    assert action["confirmation_armed"] is False


def test_discard_confirmation_expires_without_enqueuing_command(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    api.record_bridge_state(
        {"recording_active": True, "recording_paused": False, "replay_buffer_active": False}
    )
    api.discard_recording()
    api.discard_confirmation_expires_at = api.discard_confirmation_expires_at - timedelta(seconds=3)

    state = api.status()
    next_press = api.discard_recording()

    assert state["actions"]["discard_recording"]["confirmation_armed"] is False
    assert api.poll_bridge_command() == {"command": None}
    assert next_press["confirmation_armed"] is True


def test_discard_done_moves_file_without_creating_voice_job(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    source = tmp_path / "nested" / "recording.mkv"
    source.parent.mkdir()
    source.write_bytes(b"video")
    api.record_bridge_state(
        {"recording_active": True, "recording_paused": True, "replay_buffer_active": True}
    )
    api.discard_recording()
    accepted = api.discard_recording()
    api.poll_bridge_command()
    result = api.record_bridge_command_result(
        {
            "id": accepted["command_id"],
            "status": "done",
            "recording_path": str(source),
            "recording_output_root": str(tmp_path),
        }
    )
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and api.status()["busy"]:
        time.sleep(0.01)

    assert result == {"ok": True, "status": "processing"}
    assert api.status()["ui_state"] == "done"
    assert api.list_jobs()["jobs"] == []
    assert (tmp_path / "SayClip Discarded" / "recording.mkv").read_bytes() == b"video"


def test_discard_invalid_bridge_path_finishes_with_safe_error(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    api.record_bridge_state(
        {"recording_active": True, "recording_paused": False, "replay_buffer_active": False}
    )
    api.discard_recording()
    accepted = api.discard_recording()
    api.poll_bridge_command()
    api.record_bridge_command_result(
        {
            "id": accepted["command_id"],
            "status": "done",
            "recording_path": str(tmp_path / "missing.mkv"),
            "recording_output_root": str(tmp_path),
        }
    )
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and api.status()["busy"]:
        time.sleep(0.01)

    state = api.status()
    assert state["ui_state"] == "error"
    assert state["last_error"] == "Recording was not discarded."
    assert api.list_jobs()["jobs"] == []


def test_http_dock_returns_html(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    config.data["backend"]["port"] = 0
    server = create_server(BackendApi(config))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        html = _get_text(f"http://{host}:{port}/dock")
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert "SayClip" in html
    assert 'id="extendedClip"' in html


def test_http_status_and_open_folder_no_job(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    config.data["backend"]["port"] = 0
    server = create_server(BackendApi(config))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        state = _get_json(f"http://{host}:{port}/api/status")
        try:
            _post_json(f"http://{host}:{port}/api/system/open-folder", {})
        except HTTPError as error:
            error_payload = json.loads(error.read().decode("utf-8"))
            assert error.code == 422
        else:
            raise AssertionError("open-folder should fail without an output folder")
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert state["phase"] == "idle"
    assert "last_job" not in state
    assert error_payload == {"ok": False, "error": "No output folder available"}


def test_http_save_action_and_bridge_command_result(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    config.data["backend"]["port"] = 0
    server = create_server(BackendApi(config))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    original_path = tmp_path / "Game" / "clip.mkv"
    original_path.parent.mkdir()
    original_path.write_bytes(b"recording")

    try:
        assert _get_json(f"http://{host}:{port}/api/bridge/command") == {"command": None}
        created = _post_json(f"http://{host}:{port}/api/save/moment", {})
        polled = _get_json(f"http://{host}:{port}/api/bridge/command")
        result = _post_json(
            f"http://{host}:{port}/api/bridge/command-result",
            {
                "id": created["command_id"],
                "status": "done",
                "original_path": str(original_path),
                "source_title": "Game",
            },
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            status = _get_json(f"http://{host}:{port}/api/status")
            if not status["busy"]:
                break
            time.sleep(0.02)
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert created["ok"] is True
    assert polled["command"]["action"] == "save_moment"
    assert result["ok"] is True


def test_http_discard_endpoint_arms_then_accepts_and_rejects_fields(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    config.data["backend"]["port"] = 0
    api = BackendApi(config)
    api.record_bridge_state(
        {"recording_active": True, "recording_paused": False, "replay_buffer_active": False}
    )
    server = create_server(api)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    url = f"http://{host}:{port}/api/discard/recording"

    try:
        first = _post_json(url, {})
        second = _post_json(url, {})
        try:
            _post_json(url, {"recording_path": "consumer-path.mkv"})
        except HTTPError as error:
            rejected = json.loads(error.read().decode("utf-8"))
            rejected_status = error.code
        else:
            raise AssertionError("discard fields should be rejected")
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert first["confirmation_armed"] is True
    assert second["accepted"] is True
    assert rejected_status == 422
    assert rejected == {"error": "Discard recording request body must be empty"}


def test_http_system_shutdown_sets_shutdown_flag_without_persisting_jobs(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    config.data["backend"]["port"] = 0
    api = BackendApi(config)
    server = create_server(api)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        response = _post_json(f"http://{host}:{port}/api/system/shutdown", {})
    finally:
        thread.join(timeout=2)
        server.server_close()

    assert response["ok"] is True
    assert response["status"] == "shutting_down"
    assert api.shutdown_requested.is_set()
    assert not (tmp_path / "jobs.json").exists()


class _ApiFakeExtendedMerger:
    def __init__(self, output: Path) -> None:
        self.output = output
        self.calls = []

    def merge(self, replay_path: str, recording_path: str) -> ExtendedClipMergeResult:
        self.calls.append((replay_path, recording_path))
        self.output.write_bytes(b"merged")
        return ExtendedClipMergeResult(self.output, self.output.with_suffix(".diagnostics.json"), {"status": "ok"})


def _extended_api(tmp_path: Path) -> tuple[BackendApi, _ApiFakeExtendedMerger]:
    config = load_config(tmp_path)
    merger = _ApiFakeExtendedMerger(tmp_path / "sequence.extended-clip.mkv")
    service = ExtendedClipService(merger, tmp_path / "extended-session.json")
    api = BackendApi(config, extended_clip_service=service)
    api.record_bridge_state(
        {"recording_active": False, "replay_buffer_active": True, "recording_paused": False}
    )
    return api, merger


def test_extended_clip_start_projects_recording_state_and_actions(tmp_path: Path) -> None:
    api, _ = _extended_api(tmp_path)

    created = api.start_extended_clip()
    command = api.poll_bridge_command()["command"]
    api.record_bridge_command_result({"id": command["id"], "status": "processing", "event": "recording_started"})
    api.record_bridge_command_result({"id": command["id"], "status": "processing", "event": "saving_replay"})
    api.record_bridge_command_result(
        {"id": command["id"], "status": "done", "replay_path": str(tmp_path / "replay.mp4")}
    )
    state = api.status()

    assert created["accepted"] is True
    assert state["ui_state"] == "recording"
    assert state["extended_clip"] == {"active": True, "stage": "recording"}
    assert state["actions"]["save_moment"]["enabled"] is True
    assert state["actions"]["save_recording"] == {"enabled": False, "reason": "extended_clip_active"}
    assert state["actions"]["extended_clip_finish"]["enabled"] is True
    assert state["actions"]["extended_clip_cancel"]["enabled"] is True


def test_extended_clip_finish_merges_then_creates_voice_job(tmp_path: Path) -> None:
    api, merger = _extended_api(tmp_path)
    start = api.start_extended_clip()
    start_command = api.poll_bridge_command()["command"]
    assert start_command["id"] == start["command_id"]
    api.record_bridge_command_result(
        {"id": start_command["id"], "status": "done", "replay_path": str(tmp_path / "replay.mp4")}
    )

    finish = api.finish_extended_clip()
    finish_command = api.poll_bridge_command()["command"]
    result = api.record_bridge_command_result(
        {"id": finish_command["id"], "status": "done", "recording_path": str(tmp_path / "recording.mp4")}
    )
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and api.extended_clip.active_session is not None:
        time.sleep(0.02)

    assert finish["accepted"] is True
    assert result["status"] == "processing"
    assert len(merger.calls) == 1
    assert api.extended_clip.session.phase.value == "done"
    assert api.list_jobs()["jobs"][0]["type"] == "extended_clip"
    assert (tmp_path / "replay.mp4").exists() is False  # Fake paths were never touched or created.


def test_extended_clip_cancel_does_not_merge_or_stop_replay_contract(tmp_path: Path) -> None:
    api, merger = _extended_api(tmp_path)
    api.start_extended_clip()
    start_command = api.poll_bridge_command()["command"]
    api.record_bridge_command_result(
        {"id": start_command["id"], "status": "done", "replay_path": str(tmp_path / "replay.mp4")}
    )

    cancelled = api.cancel_extended_clip()
    cancel_command = api.poll_bridge_command()["command"]
    api.record_bridge_command_result(
        {"id": cancel_command["id"], "status": "done", "recording_path": str(tmp_path / "recording.mp4")}
    )

    assert cancelled["accepted"] is True
    assert merger.calls == []
    assert api.extended_clip.session.phase.value == "cancelled"
    assert api.status()["extended_clip"] == {"active": False, "stage": "idle"}


def _get_json(url: str) -> dict:
    with urlopen(url, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_text(url: str) -> str:
    with urlopen(url, timeout=2) as response:
        return response.read().decode("utf-8")


def _post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_for_phase(api: BackendApi, phase: str, timeout: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    state = api.status()
    while time.monotonic() < deadline:
        state = api.status()
        if state["phase"] == phase:
            return state
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for phase {phase!r}; last state was {state!r}")
