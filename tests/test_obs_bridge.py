from pathlib import Path
import importlib.util
import time


BRIDGE_PATH = Path(__file__).resolve().parents[1] / "src" / "obs" / "instant_bridge.py"
PRODUCT_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "SayClip_Starter.py"


def load_bridge():
    spec = importlib.util.spec_from_file_location("sayclip_bridge_under_test", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_product_script():
    spec = importlib.util.spec_from_file_location("sayclip_obs_script_under_test", PRODUCT_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_product_named_obs_script_delegates_to_bridge() -> None:
    script = load_product_script()

    assert script.script_description() == script._bridge.script_description()


def test_bridge_locates_project_root_from_script_path() -> None:
    bridge = load_bridge()

    assert bridge.find_project_root(BRIDGE_PATH) == BRIDGE_PATH.parents[2]


def test_bridge_locates_project_root_with_example_config_only(tmp_path: Path) -> None:
    bridge = load_bridge()
    script = tmp_path / "SayClip_Starter.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "config.example.toml").write_text("", encoding="utf-8")

    assert bridge.find_project_root(script) == tmp_path


def test_bridge_loads_backend_config_without_backend_imports() -> None:
    bridge = load_bridge()

    config = bridge.load_bridge_config(BRIDGE_PATH)

    assert config["backend"]["host"] == "127.0.0.1"
    assert config["backend"]["port"] == 17891
    assert config["backend"]["process"]["module"] == "instant_easy_rename_server"


def test_bridge_payload_uses_source_title_before_parent_folder(tmp_path: Path) -> None:
    bridge = load_bridge()
    original = tmp_path / "Parent Game" / "recording.mkv"

    payload = bridge.build_job_payload(
        "recording",
        original,
        {"scene_name": "Main", "source_name": "Capture", "source_title": "Window Game"},
    )

    assert payload == {
        "type": "recording",
        "original_path": str(original),
        "game_hint": "Window Game",
        "scene_name": "Main",
        "source_name": "Capture",
        "source_title": "Window Game",
        "created_by": "obs_bridge",
    }


def test_bridge_payload_falls_back_to_parent_folder(tmp_path: Path) -> None:
    bridge = load_bridge()
    original = tmp_path / "Parent Game" / "recording.mkv"

    payload = bridge.build_job_payload("moment", original, {})

    assert payload["type"] == "moment"
    assert payload["game_hint"] == "Parent Game"
    assert "scene_name" not in payload
    assert "source_title" not in payload


def test_collect_obs_context_uses_configured_source_name(monkeypatch) -> None:
    bridge = load_bridge()

    class FakeSource:
        def __init__(self, name: str) -> None:
            self.name = name

    class FakeObs:
        def __init__(self) -> None:
            self.released = []

        def obs_frontend_get_current_scene(self):
            return FakeSource("Game Scene")

        def obs_get_source_by_name(self, name):
            return FakeSource(name) if name == "Save recording" else None

        def obs_source_get_name(self, source):
            return source.name

        def obs_source_release(self, source):
            self.released.append(source.name)

    fake_obs = FakeObs()
    monkeypatch.setattr(bridge, "obs", fake_obs)
    bridge._state["title_source_name"] = "Save recording"

    context = bridge.collect_obs_context()

    assert context == {
        "scene_name": "Game Scene",
        "source_name": "Save recording",
        "source_title": "Save recording",
    }
    assert fake_obs.released == ["Game Scene", "Save recording"]


def test_collect_obs_context_keeps_folder_fallback_when_title_source_empty(monkeypatch) -> None:
    bridge = load_bridge()

    class FakeObs:
        def obs_frontend_get_current_scene(self):
            return None

    monkeypatch.setattr(bridge, "obs", FakeObs())
    bridge._state["title_source_name"] = ""

    assert bridge.collect_obs_context()["source_title"] is None


def test_bridge_does_not_import_backend_package() -> None:
    source = BRIDGE_PATH.read_text(encoding="utf-8")

    assert "from instant_easy_rename_server" not in source
    assert "import instant_easy_rename_server" not in source
    assert "PySide6" not in source
    assert "faster_whisper" not in source


def test_bridge_backend_env_adds_src_pythonpath(monkeypatch) -> None:
    bridge = load_bridge()
    root = BRIDGE_PATH.parents[2]
    monkeypatch.setenv("PYTHONPATH", "existing-path")

    env = bridge._build_backend_env(root)

    assert env["PYTHONPATH"].split(bridge.os.pathsep)[0] == str(root / "src")
    assert "existing-path" in env["PYTHONPATH"].split(bridge.os.pathsep)


def test_bridge_background_requests_return_immediately() -> None:
    bridge = load_bridge()
    calls = []

    started = time.monotonic()
    result = bridge._run_background("slow-test", lambda: (time.sleep(0.2), calls.append("done")))
    elapsed = time.monotonic() - started

    assert result is True
    assert elapsed < 0.1
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline and not calls:
        time.sleep(0.01)
    assert calls == ["done"]


def test_bridge_setup_is_incomplete_without_config_state_or_venv(tmp_path: Path) -> None:
    bridge = load_bridge()

    assert bridge.is_setup_complete(tmp_path) is False


def test_bridge_setup_is_complete_with_config_state_and_venv(tmp_path: Path) -> None:
    bridge = load_bridge()
    (tmp_path / "config.toml").write_text(
        '[setup]\ncompleted = true\ndependencies_installed = true\nvenv_path = "%s"\n'
        % str(tmp_path / ".venv").replace("\\", "\\\\"),
        encoding="utf-8",
    )
    venv_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    assert bridge.is_setup_complete(tmp_path) is True


def test_bridge_setup_is_incomplete_without_dependency_marker(tmp_path: Path) -> None:
    bridge = load_bridge()
    (tmp_path / "config.toml").write_text(
        '[setup]\ncompleted = true\ndependencies_installed = false\nvenv_path = "%s"\n'
        % str(tmp_path / ".venv").replace("\\", "\\\\"),
        encoding="utf-8",
    )
    venv_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    assert bridge.is_setup_complete(tmp_path) is False


def test_bridge_start_backend_launches_onboarding_when_setup_is_incomplete(monkeypatch, tmp_path: Path) -> None:
    bridge = load_bridge()
    calls = []

    monkeypatch.setattr(bridge, "find_project_root", lambda: tmp_path)
    monkeypatch.setattr(bridge, "is_setup_complete", lambda: False)
    monkeypatch.setattr(bridge, "start_onboarding", lambda: calls.append("onboarding") or True)

    assert bridge.start_backend() is True
    assert calls == ["onboarding"]


def test_bridge_start_onboarding_launches_installer_without_persistent_lock(monkeypatch, tmp_path: Path) -> None:
    bridge = load_bridge()
    (tmp_path / "install.bat").write_text("", encoding="utf-8")
    commands = []

    class FakeProcess:
        pid = 54321

    monkeypatch.setattr(bridge, "find_project_root", lambda: tmp_path)
    monkeypatch.setattr(bridge, "_installer_command", lambda installer: [str(installer)])
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda command, **kwargs: commands.append(command) or FakeProcess())

    assert bridge.start_onboarding() is True

    assert commands == [[str(tmp_path / "install.bat")]]
    assert not (tmp_path / ".local").exists()


def test_recording_flow_waits_for_obs_stop_event(monkeypatch, tmp_path: Path) -> None:
    bridge = load_bridge()
    posted = []

    class FakeObs:
        OBS_FRONTEND_EVENT_RECORDING_STOPPED = 1

        def __init__(self) -> None:
            self.stopped = False

        def obs_frontend_recording_active(self):
            return True

        def obs_frontend_recording_stop(self):
            self.stopped = True

        def obs_frontend_get_last_recording(self):
            return str(tmp_path / "Game" / "clip.mkv")

    fake_obs = FakeObs()
    monkeypatch.setattr(bridge, "obs", fake_obs)
    monkeypatch.setattr(bridge, "collect_obs_context", lambda: {"source_title": "Game"})
    monkeypatch.setattr(bridge, "_post_json", lambda config, path, payload: posted.append((path, payload)) or {"status": "created"})
    monkeypatch.setattr(bridge, "load_bridge_config", lambda: {"backend": {"host": "127.0.0.1", "port": 1}})

    assert bridge.stop_recording_and_voice_rename() is True
    assert fake_obs.stopped is True
    assert posted == []

    bridge._on_frontend_event(fake_obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED)

    assert posted[0][0] == "/jobs"
    assert posted[0][1]["type"] == "recording"
    assert posted[0][1]["created_by"] == "obs_bridge"


def test_replay_flow_logs_missing_path_after_save_event(monkeypatch) -> None:
    bridge = load_bridge()
    errors = []

    class FakeObs:
        OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED = 2

        def obs_frontend_replay_buffer_active(self):
            return True

        def obs_frontend_replay_buffer_save(self):
            return None

    fake_obs = FakeObs()
    monkeypatch.setattr(bridge, "obs", fake_obs)
    monkeypatch.setattr(bridge, "collect_obs_context", lambda: {})
    monkeypatch.setattr(bridge, "get_last_replay_path", lambda: None)
    monkeypatch.setattr(bridge, "send_backend_error", lambda message, details=None: errors.append((message, details)))

    assert bridge.save_replay_buffer_and_voice_rename() is True
    bridge._on_frontend_event(fake_obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED)

    assert "output path" in errors[0][0]
    assert errors[0][1]["operation"] == "moment"


def test_bridge_polls_and_executes_dock_command(monkeypatch) -> None:
    bridge = load_bridge()
    results = []
    calls = []

    monkeypatch.setattr(
        bridge,
        "_get_json",
        lambda config, path: {"command": {"id": "cmd-1", "action": "save_moment"}},
    )
    monkeypatch.setattr(
        bridge,
        "_post_json",
        lambda config, path, payload: results.append((path, payload)) or {"ok": True},
    )
    monkeypatch.setattr(bridge, "is_setup_complete", lambda: True)
    monkeypatch.setattr(bridge, "save_replay_buffer_and_voice_rename", lambda command_id=None: calls.append(command_id) or True)
    monkeypatch.setattr(bridge, "load_bridge_config", lambda: {"backend": {"host": "127.0.0.1", "port": 1}})

    assert bridge.poll_bridge_commands() is True

    assert calls == ["cmd-1"]
    assert results == [
        (
            "/api/bridge/state",
            {"recording_active": False, "recording_paused": False, "replay_buffer_active": False},
        ),
        ("/api/bridge/command-result", {"id": "cmd-1", "status": "processing"})
    ]


def test_bridge_posts_obs_state_while_polling(monkeypatch) -> None:
    bridge = load_bridge()
    posted = []

    class FakeObs:
        def obs_frontend_recording_active(self):
            return True

        def obs_frontend_recording_paused(self):
            return False

        def obs_frontend_replay_buffer_active(self):
            return True

    monkeypatch.setattr(bridge, "obs", FakeObs())
    monkeypatch.setattr(bridge, "_get_json", lambda config, path: {"command": None})
    monkeypatch.setattr(bridge, "_post_json", lambda config, path, payload: posted.append((path, payload)) or {"ok": True})
    monkeypatch.setattr(bridge, "is_setup_complete", lambda: True)
    monkeypatch.setattr(bridge, "load_bridge_config", lambda: {"backend": {"host": "127.0.0.1", "port": 1}})

    assert bridge.poll_bridge_commands() is True

    assert posted == [
        (
            "/api/bridge/state",
            {"recording_active": True, "recording_paused": False, "replay_buffer_active": True},
        )
    ]


def test_bridge_action_specific_error_does_not_block_later_valid_command(monkeypatch, tmp_path: Path) -> None:
    bridge = load_bridge()
    results = []

    class FakeObs:
        OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED = 2

        def __init__(self) -> None:
            self.recording_active = False
            self.replay_active = True

        def obs_frontend_recording_active(self):
            return self.recording_active

        def obs_frontend_replay_buffer_active(self):
            return self.replay_active

        def obs_frontend_replay_buffer_save(self):
            return None

    fake_obs = FakeObs()
    commands = iter(
        [
            {"command": {"id": "cmd-recording", "action": "save_recording"}},
            {"command": {"id": "cmd-moment", "action": "save_moment"}},
        ]
    )

    monkeypatch.setattr(bridge, "obs", fake_obs)
    monkeypatch.setattr(bridge, "_get_json", lambda config, path: next(commands))
    monkeypatch.setattr(
        bridge,
        "_post_json",
        lambda config, path, payload: results.append((path, payload)) or {"ok": True},
    )
    monkeypatch.setattr(bridge, "is_setup_complete", lambda: True)
    monkeypatch.setattr(bridge, "collect_obs_context", lambda: {"source_title": "Game"})
    monkeypatch.setattr(bridge, "get_last_replay_path", lambda: tmp_path / "Game" / "clip.mkv")
    monkeypatch.setattr(bridge, "load_bridge_config", lambda: {"backend": {"host": "127.0.0.1", "port": 1}})

    assert bridge.poll_bridge_commands() is True
    assert bridge.poll_bridge_commands() is True
    bridge._on_frontend_event(fake_obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED)

    assert results == [
        (
            "/api/bridge/state",
            {"recording_active": False, "recording_paused": False, "replay_buffer_active": True},
        ),
        ("/api/bridge/command-result", {"id": "cmd-recording", "status": "processing"}),
        ("/api/bridge/command-result", {"id": "cmd-recording", "status": "error", "error": "Recording is not active."}),
        (
            "/api/bridge/state",
            {"recording_active": False, "recording_paused": False, "replay_buffer_active": True},
        ),
        ("/api/bridge/command-result", {"id": "cmd-moment", "status": "processing"}),
        (
            "/api/bridge/command-result",
            {
                "id": "cmd-moment",
                "status": "done",
                "type": "moment",
                "original_path": str(tmp_path / "Game" / "clip.mkv"),
                "game_hint": "Game",
                "source_title": "Game",
                "created_by": "obs_bridge",
            },
        ),
    ]


def test_bridge_command_result_posts_done_after_obs_event(monkeypatch, tmp_path: Path) -> None:
    bridge = load_bridge()
    posted = []

    class FakeObs:
        OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED = 2

        def obs_frontend_replay_buffer_active(self):
            return True

        def obs_frontend_replay_buffer_save(self):
            return None

    fake_obs = FakeObs()
    monkeypatch.setattr(bridge, "obs", fake_obs)
    monkeypatch.setattr(bridge, "collect_obs_context", lambda: {"source_title": "Game"})
    monkeypatch.setattr(bridge, "get_last_replay_path", lambda: tmp_path / "Game" / "clip.mkv")
    monkeypatch.setattr(bridge, "_post_json", lambda config, path, payload: posted.append((path, payload)) or {"ok": True})
    monkeypatch.setattr(bridge, "load_bridge_config", lambda: {"backend": {"host": "127.0.0.1", "port": 1}})

    assert bridge.save_replay_buffer_and_voice_rename("cmd-1") is True
    bridge._on_frontend_event(fake_obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED)

    assert posted[0][0] == "/api/bridge/command-result"
    assert posted[0][1]["id"] == "cmd-1"
    assert posted[0][1]["status"] == "done"
    assert posted[0][1]["type"] == "moment"
    assert posted[0][1]["source_title"] == "Game"


def test_bridge_starts_backend_with_obs_pid(monkeypatch, tmp_path: Path) -> None:
    bridge = load_bridge()
    commands = []

    class FakeProcess:
        def poll(self):
            return None

    monkeypatch.setattr(bridge, "find_project_root", lambda: tmp_path)
    monkeypatch.setattr(bridge, "is_setup_complete", lambda: True)
    monkeypatch.setattr(bridge, "check_backend_health", lambda config: {"connected": True, "reachable": True})
    monkeypatch.setattr(bridge, "load_bridge_config", lambda: {
        "backend": {
            "host": "127.0.0.1",
            "port": 17891,
            "process": {"python_path": "python.exe", "module": "instant_easy_rename_server"},
        }
    })
    monkeypatch.setattr(bridge, "_resolve_project_path", lambda root, value: tmp_path / value)
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    health_results = iter([
        {"connected": False, "reachable": False},
        {"connected": True, "reachable": True},
    ])
    monkeypatch.setattr(bridge, "check_backend_health", lambda config: next(health_results))
    monkeypatch.setattr(
        bridge.subprocess,
        "Popen",
        lambda command, **kwargs: commands.append(command) or FakeProcess(),
    )

    assert bridge.start_backend() is True

    assert "--headless" in commands[0]
    assert "--obs-pid" in commands[0]
    assert commands[0][commands[0].index("--obs-pid") + 1] == str(bridge.os.getpid())


def test_bridge_open_backend_ui_restarts_backend_in_pyside_mode(monkeypatch) -> None:
    bridge = load_bridge()
    calls = []

    monkeypatch.setattr(bridge, "stop_backend", lambda: calls.append("stop") or True)
    monkeypatch.setattr(bridge, "start_backend", lambda *, show_ui=False: calls.append(("start", show_ui)) or True)

    assert bridge._open_backend_ui() is True

    assert calls == ["stop", ("start", True)]


def test_bridge_properties_include_open_ui_and_stop_backend_buttons(monkeypatch) -> None:
    bridge = load_bridge()
    buttons = {}

    class FakeObs:
        OBS_COMBO_TYPE_LIST = 1
        OBS_COMBO_FORMAT_STRING = 2
        OBS_TEXT_INFO = 3

        def obs_properties_create(self):
            return {}

        def obs_properties_add_list(self, props, name, label, combo_type, combo_format):
            del props, label, combo_type, combo_format
            return {"name": name, "items": []}

        def obs_property_list_add_string(self, prop, label, value):
            prop["items"].append((label, value))

        def obs_properties_add_text(self, props, name, label, text_type):
            props[name] = (label, text_type)

        def obs_properties_add_button(self, props, name, label, callback):
            del props
            buttons[name] = {"label": label, "callback": callback}

    monkeypatch.setattr(bridge, "obs", FakeObs())
    monkeypatch.setattr(bridge, "request_stop_backend", lambda: "stop-requested")
    monkeypatch.setattr(bridge, "open_backend_ui", lambda: "ui-requested")

    bridge.script_properties()

    assert buttons["stop_backend"]["label"] == "Stop Backend"
    assert buttons["open_backend_ui"]["label"] == "Open Backend UI"
    assert buttons["stop_backend"]["callback"](None, None) == "stop-requested"
    assert buttons["open_backend_ui"]["callback"](None, None) == "ui-requested"


def test_bridge_starts_backend_in_ui_mode_when_requested(monkeypatch, tmp_path: Path) -> None:
    bridge = load_bridge()
    commands = []

    class FakeProcess:
        def poll(self):
            return None

    monkeypatch.setattr(bridge, "find_project_root", lambda: tmp_path)
    monkeypatch.setattr(bridge, "is_setup_complete", lambda: True)
    monkeypatch.setattr(bridge, "load_bridge_config", lambda: {
        "backend": {
            "host": "127.0.0.1",
            "port": 17891,
            "process": {"python_path": "python.exe", "module": "instant_easy_rename_server"},
        }
    })
    monkeypatch.setattr(bridge, "_resolve_project_path", lambda root, value: tmp_path / value)
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    health_results = iter([
        {"connected": False, "reachable": False},
        {"connected": True, "reachable": True},
    ])
    monkeypatch.setattr(bridge, "check_backend_health", lambda config: next(health_results))
    monkeypatch.setattr(
        bridge.subprocess,
        "Popen",
        lambda command, **kwargs: commands.append(command) or FakeProcess(),
    )

    assert bridge.start_backend(show_ui=True) is True

    assert "--ui" in commands[0]
    assert "--headless" not in commands[0]


def test_bridge_stop_backend_uses_graceful_shutdown(monkeypatch) -> None:
    bridge = load_bridge()
    posted = []

    monkeypatch.setattr(bridge, "load_bridge_config", lambda: {"backend": {"host": "127.0.0.1", "port": 1}})
    monkeypatch.setattr(bridge, "_post_json", lambda config, path, payload: posted.append(path) or {"ok": True})
    monkeypatch.setattr(bridge, "_kill_verified_backend_on_port", lambda config: (_ for _ in ()).throw(AssertionError("should not kill")))
    bridge._state["backend_process"] = None

    assert bridge.stop_backend() is True

    assert posted == ["/api/system/shutdown"]


def test_bridge_does_not_kill_non_easy_rename_service_on_port(monkeypatch) -> None:
    bridge = load_bridge()
    killed = []
    config = {"backend": {"host": "127.0.0.1", "port": 17891}}

    monkeypatch.setattr(
        bridge,
        "check_backend_health",
        lambda config: {"connected": False, "reachable": True, "payload": {"app": "Other"}},
    )
    monkeypatch.setattr(bridge, "_kill_pid", lambda pid: killed.append(pid) or True)

    assert bridge._kill_verified_backend_on_port(config) is False
    assert killed == []
