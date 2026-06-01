from pathlib import Path
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
from instant_easy_rename_server.stt import FakeSpeechToTextEngine


class NoopRenamer:
    def rename(self, job: Job, transcript: str) -> Path:
        del transcript
        return Path(job.original_path)


def test_health_contract(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))

    assert api.health() == {
        "app": "SayClip",
        "version": "0.1.0",
        "status": "ok",
    }


def test_valid_recording_and_moment_jobs(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    recording_path = tmp_path / "Forza Horizon 6" / "2026-05-27 21-31-12.mkv"
    moment_path = tmp_path / "Forza Horizon 6" / "Replays" / "2026-05-27 22-10-44.mkv"
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
    original_path = tmp_path / "Forza Horizon 6" / "2026-05-27 21-31-12.mkv"
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
        "fresh": False,
    }
    assert state["actions"]["save_moment"]["reason"] == "bridge_disconnected"
    assert state["actions"]["save_recording"]["reason"] == "bridge_disconnected"
    assert "mic" in state
    assert "last_job" not in state


def test_job_for_ui_returns_latest_job_shape(tmp_path: Path) -> None:
    api = BackendApi(load_config(tmp_path))
    original_path = tmp_path / "Forza Horizon 6" / "clip.mkv"
    original_path.parent.mkdir()
    original_path.write_bytes(b"recording")

    api.create_job({"type": "moment", "original_path": str(original_path), "source_title": "Forza Horizon 6"})
    job = api.job_for_ui(api.list_jobs()["jobs"][0])

    assert job["type"] == "mom"
    assert job["game"] == "forza-horizon-6"
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
    assert BridgeCommandStatus.PROCESSING.value == "processing"
    assert OperationPhase.LISTENING.value == "listening"


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
