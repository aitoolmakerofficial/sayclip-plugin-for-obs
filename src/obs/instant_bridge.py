# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 AI Toolmaker (AI Toolmaker Official)

from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen
import json
import os
import re
import subprocess
import sys
import threading
import time

try:
    import obspython as obs
except Exception:
    obs = None


APP_NAME = "SayClip"
APP_VERSION = "2.0.0"
YOUTUBE_GUIDE_URL = "https://www.youtube.com/watch?v=VeY80kJk3RM&list=PLOz1A1R4o9mg"
OBS_DOCK_URL = "http://127.0.0.1:17891/dock"
STREAMDECK_PLUGIN_REPOSITORY_URL = "https://github.com/aitoolmakerofficial/obs-sayclip-plugin-streamdeck"
DEFAULT_CONFIG = {
    "backend": {
        "host": "127.0.0.1",
        "port": 17891,
        "start_mode": "on_obs_start",
        "process": {
            "python_path": ".venv/Scripts/pythonw.exe",
            "module": "instant_easy_rename_server",
        },
    },
    "setup": {
        "completed": False,
        "dependencies_installed": False,
        "python_path": "",
        "venv_path": "",
        "completed_at": "",
    },
    "extended_clip": {
        "overlap_wait_seconds": 1.5,
    },
}

_state = {
    "backend_process": None,
    "backend_status": "Disconnected",
    "title_source_name": "",
    "pending_recording": None,
    "pending_replay": None,
    "extended_clip": None,
    "extended_timer_registered": False,
    "hotkeys": {},
    "background": {},
    "polling_registered": False,
    "last_poll_error_log_at": 0.0,
}
_state_lock = threading.RLock()


def script_description():
    return (
        "<h4>SayClip app</h4>"
        f"YouTube guide: <a href='{YOUTUBE_GUIDE_URL}'>open guide</a>.<br>"
        f"OBS dock: <a href='{OBS_DOCK_URL}'>open dock</a>.<br>"
        f"Stream Deck plugin: <a href='{STREAMDECK_PLUGIN_REPOSITORY_URL}'>open repository</a>."
    )


def script_load(settings):
    _log("Loading SayClip Bridge")
    _register_frontend_callback()
    _register_hotkeys(settings)
    _register_command_polling()
    config = load_bridge_config()
    if config["backend"].get("start_mode") == "on_obs_start":
        if is_setup_complete():
            request_start_backend()
        else:
            request_start_onboarding()


def script_unload():
    _log("Unloading SayClip Bridge")
    _cancel_owned_extended_recording("bridge_unload")
    if obs:
        try:
            obs.obs_frontend_remove_event_callback(_on_frontend_event)
        except Exception as error:
            _log("Could not remove frontend callback: %s" % error, visible=True)
        try:
            obs.timer_remove(_poll_bridge_commands)
            _state["polling_registered"] = False
        except Exception as error:
            _log("Could not remove command polling timer: %s" % error)
        if _state.get("extended_timer_registered"):
            try:
                obs.timer_remove(_extended_clip_save_replay)
            except Exception:
                pass
            _state["extended_timer_registered"] = False
    _unregister_hotkeys()
    stop_backend()


def script_update(settings):
    config = load_bridge_config()
    selected = _settings_get_string(settings, "backend_start_mode")
    if selected in ("on_obs_start", "manual"):
        config["backend"]["start_mode"] = selected
    _state["title_source_name"] = _settings_get_string(settings, "title_source_name").strip()
    if obs:
        obs.obs_data_set_string(settings, "backend_status", _state["backend_status"])


def script_save(settings):
    if not obs:
        return
    for name, hotkey_id in _state["hotkeys"].items():
        saved = obs.obs_hotkey_save(hotkey_id)
        obs.obs_data_set_array(settings, name, saved)
        obs.obs_data_array_release(saved)


def script_properties():
    if not obs:
        return None
    props = obs.obs_properties_create()
    obs.obs_properties_add_text(props, "backend_section", "Backend", obs.OBS_TEXT_INFO)
    start_mode = obs.obs_properties_add_list(
        props,
        "backend_start_mode",
        "Backend start mode",
        obs.OBS_COMBO_TYPE_LIST,
        obs.OBS_COMBO_FORMAT_STRING,
    )
    obs.obs_property_list_add_string(start_mode, "Start with OBS", "on_obs_start")
    obs.obs_property_list_add_string(start_mode, "Manual", "manual")
    obs.obs_properties_add_text(props, "backend_status", "Backend status", obs.OBS_TEXT_INFO)
    obs.obs_properties_add_button(props, "stop_backend", "Stop Backend", _props_stop_backend)
    obs.obs_properties_add_button(props, "hard_reset_backend", "Force Restart Backend", _props_hard_reset_backend)
    obs.obs_properties_add_button(props, "open_backend_ui", "Open Backend UI", _props_open_backend_ui)
    obs.obs_properties_add_text(props, "title_section", "Title setup", obs.OBS_TEXT_INFO)
    obs.obs_properties_add_text(
        props,
        "title_source_name",
        "Title source name",
        getattr(obs, "OBS_TEXT_DEFAULT", obs.OBS_TEXT_INFO),
    )
    return props


def script_defaults(settings):
    if obs:
        obs.obs_data_set_default_string(settings, "backend_start_mode", "on_obs_start")
        obs.obs_data_set_default_string(settings, "backend_status", _state["backend_status"])
        obs.obs_data_set_default_string(settings, "title_source_name", "")


def start_backend(*, show_ui=False):
    if not is_setup_complete():
        _log("Setup is incomplete; launching SayClip Onboarding instead of backend", visible=True)
        return start_onboarding()
    config = load_bridge_config()
    _set_backend_status("Starting")
    health = check_backend_health(config)
    if health["connected"]:
        _set_backend_status("Connected")
        _log("Backend already connected")
        return True
    if health["reachable"]:
        _set_backend_status("Error")
        _log("Port is occupied by a non SayClip service: %s" % health.get("error", "unknown"), visible=True)
        return False

    process_config = config["backend"]["process"]
    project_root = find_project_root()
    python_path = _resolve_project_path(project_root, process_config.get("python_path", "python"))
    if not python_path.exists() and python_path.name.lower() == "pythonw.exe":
        fallback = python_path.with_name("python.exe")
        if fallback.exists():
            _log("pythonw.exe was not found, falling back to: %s" % fallback)
            python_path = fallback
    module = str(process_config.get("module") or "instant_easy_rename_server")
    ui_mode_arg = "--ui" if show_ui else "--headless"
    command = [str(python_path), "-m", module, ui_mode_arg, "--obs-pid", str(os.getpid())]
    log_path = _bridge_process_log_path(project_root)
    _log("Starting backend: cwd=%s command=%s log=%s" % (project_root, command, log_path))
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        process_log = log_path.open("a", encoding="utf-8")
        _state["backend_process"] = subprocess.Popen(
            command,
            cwd=str(project_root),
            stdout=process_log,
            stderr=process_log,
            env=_build_backend_env(project_root),
            creationflags=_creation_flags(),
        )
    except OSError as error:
        _set_backend_status("Error")
        _log("Could not start backend: %s" % error, visible=True)
        return False

    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if check_backend_health(config)["connected"]:
            _set_backend_status("Connected")
            _log("Backend started")
            return True
        time.sleep(0.25)
    _set_backend_status("Error")
    _log("Backend process started but health check did not pass", visible=True)
    return False


def request_start_backend():
    return _run_background("start_backend", start_backend)


def start_onboarding():
    project_root = find_project_root()
    installer = project_root / "install.bat"
    if not installer.exists():
        _set_backend_status("Setup Required")
        _log("Setup is required, but install.bat was not found: %s" % installer, visible=True)
        return False
    _set_backend_status("Setup Required")
    _log("Launching SayClip Onboarding: %s" % installer, visible=True)
    try:
        process = subprocess.Popen(
            _installer_command(installer),
            cwd=str(project_root),
            creationflags=0,
        )
        _state["backend_process"] = process
        return True
    except OSError as error:
        _set_backend_status("Error")
        _log("Could not launch installer: %s" % error, visible=True)
        return False


def request_start_onboarding():
    return _run_background("start_onboarding", start_onboarding)


def stop_backend():
    config = load_bridge_config()
    graceful_requested = False
    graceful = False
    try:
        _post_json(config, "/api/system/shutdown", {})
        graceful_requested = True
    except Exception as error:
        _log("Backend graceful shutdown request did not complete: %s" % error)
    process = _state.get("backend_process")
    if process and process.poll() is None:
        try:
            process.wait(timeout=3)
            graceful = True
        except subprocess.TimeoutExpired:
            _log("Backend process did not exit after graceful shutdown")
    elif graceful_requested:
        graceful = True
    if not graceful:
        _terminate_known_backend_process(process)
        _kill_verified_backend_on_port(config)
    _state["backend_process"] = None
    _set_backend_status("Disconnected")
    return True


def request_stop_backend():
    return _run_background("stop_backend", stop_backend)


def hard_reset_backend():
    stop_backend()
    return start_backend()


def request_hard_reset_backend():
    return _run_background("hard_reset_backend", hard_reset_backend)


def test_backend():
    health = check_backend_health(load_bridge_config())
    _set_backend_status("Connected" if health["connected"] else "Disconnected")
    _log("Backend test: %s" % health)
    return health["connected"]


def request_test_backend():
    return _run_background("test_backend", test_backend)


def open_backend_ui():
    return _run_background("open_backend_ui", _open_backend_ui)


def stop_recording_and_voice_rename(command_id=None):
    if not _obs_call_bool("obs_frontend_recording_active"):
        message = "Recording is not active."
        _log(message, visible=True)
        _report_obs_error(command_id, message, {"operation": "stop_recording"})
        return False
    context = collect_obs_context()
    if command_id:
        context["command_id"] = command_id
    _state["pending_recording"] = context
    if not _obs_invoke("obs_frontend_recording_stop"):
        _state["pending_recording"] = None
        message = "OBS recording stop API is unavailable."
        _log(message, visible=True)
        _report_obs_error(command_id, message, {"operation": "stop_recording"})
        return False
    return True


def save_replay_buffer_and_voice_rename(command_id=None):
    if not _obs_call_bool("obs_frontend_replay_buffer_active"):
        message = "Replay buffer is not active."
        _log(message, visible=True)
        _report_obs_error(command_id, message, {"operation": "save_replay_buffer"})
        return False
    context = collect_obs_context()
    if command_id:
        context["command_id"] = command_id
    _state["pending_replay"] = context
    if not _obs_invoke("obs_frontend_replay_buffer_save"):
        _state["pending_replay"] = None
        message = "OBS replay-buffer save API is unavailable."
        _log(message, visible=True)
        _report_obs_error(command_id, message, {"operation": "save_replay_buffer"})
        return False
    return True


def start_extended_clip(command_id):
    if _state.get("extended_clip") is not None:
        _report_obs_error(command_id, "An Extended Clip is already active.")
        return False
    if _obs_call_bool("obs_frontend_recording_active"):
        _report_obs_error(command_id, "Recording is already active.")
        return False
    if not _obs_call_bool("obs_frontend_replay_buffer_active"):
        _report_obs_error(command_id, "Replay buffer is not active.")
        return False
    _state["extended_clip"] = {
        "mode": "starting",
        "command_id": command_id,
        "owned_recording": False,
        "context": collect_obs_context(),
    }
    if not _obs_invoke("obs_frontend_recording_start"):
        _state["extended_clip"] = None
        _report_obs_error(command_id, "OBS recording start API is unavailable.")
        return False
    return True


def finish_extended_clip(command_id):
    context = _state.get("extended_clip")
    if not isinstance(context, dict) or context.get("mode") != "capturing":
        _report_obs_error(command_id, "Extended Clip is not ready to finish.")
        return False
    if not context.get("owned_recording") or not _obs_call_bool("obs_frontend_recording_active"):
        _report_obs_error(command_id, "Extended Clip recording is not active.")
        return False
    context["mode"] = "finishing"
    context["command_id"] = command_id
    if not _obs_invoke("obs_frontend_recording_stop"):
        context["mode"] = "capturing"
        _report_obs_error(command_id, "OBS recording stop API is unavailable.")
        return False
    return True


def cancel_extended_clip(command_id):
    context = _state.get("extended_clip")
    if not isinstance(context, dict):
        _report_obs_error(command_id, "Extended Clip is not active.")
        return False
    context["mode"] = "cancelling"
    context["command_id"] = command_id
    if not context.get("owned_recording"):
        if _obs_call_bool("obs_frontend_recording_active"):
            context["owned_recording"] = True
        else:
            context["mode"] = "cancel_pending_start"
            return True
    if not _obs_call_bool("obs_frontend_recording_active"):
        _complete_extended_recording_event(None)
        return True
    if not _obs_invoke("obs_frontend_recording_stop"):
        _report_obs_error(command_id, "OBS recording stop API is unavailable.")
        return False
    return True


def _extended_clip_save_replay():
    if obs and _state.get("extended_timer_registered"):
        try:
            obs.timer_remove(_extended_clip_save_replay)
        except Exception:
            pass
    _state["extended_timer_registered"] = False
    context = _state.get("extended_clip")
    if not isinstance(context, dict) or context.get("mode") != "waiting_overlap":
        return
    command_id = context.get("command_id")
    if not _obs_call_bool("obs_frontend_replay_buffer_active"):
        _cancel_owned_extended_recording("replay_buffer_inactive")
        _report_obs_error(command_id, "Replay buffer stopped before the Extended Clip snapshot.")
        return
    context["mode"] = "saving_replay"
    _post_bridge_command_result({"id": command_id, "status": "processing", "event": "saving_replay"})
    if not _obs_invoke("obs_frontend_replay_buffer_save"):
        _cancel_owned_extended_recording("replay_save_failed")
        _report_obs_error(command_id, "OBS replay-buffer save API is unavailable.")


def _schedule_extended_replay_save():
    config = load_bridge_config()
    delay = float(config.get("extended_clip", {}).get("overlap_wait_seconds", 1.5))
    delay_ms = max(1, int(delay * 1000))
    if obs and hasattr(obs, "timer_add"):
        _state["extended_timer_registered"] = True
        obs.timer_add(_extended_clip_save_replay, delay_ms)
        return
    _extended_clip_save_replay()


def _complete_extended_replay_event(path):
    context = _state.get("extended_clip")
    if not isinstance(context, dict) or context.get("mode") != "saving_replay":
        return False
    command_id = context.get("command_id")
    if not path:
        _cancel_owned_extended_recording("missing_replay_path")
        _report_obs_error(command_id, "OBS did not provide an Extended Clip replay path.")
        return False
    payload = {
        "id": command_id,
        "status": "done",
        "replay_path": str(path),
        **dict(context.get("context") or {}),
    }
    _post_bridge_command_result(payload)
    context["mode"] = "capturing"
    context["command_id"] = None
    context["replay_path"] = str(path)
    return True


def _complete_extended_recording_event(path):
    context = _state.get("extended_clip")
    if not isinstance(context, dict):
        return False
    mode = context.get("mode")
    command_id = context.get("command_id")
    context["owned_recording"] = False
    if mode in {"finishing", "cancelling"} and command_id:
        payload = {
            "id": command_id,
            "status": "done",
            "recording_path": str(path) if path else None,
            **dict(context.get("context") or {}),
        }
        _post_bridge_command_result(payload)
    elif mode not in {"abandoning"}:
        try:
            _post_json(
                load_bridge_config(),
                "/api/bridge/extended-clip-event",
                {"event": "recording_stopped", "recording_path": str(path) if path else None},
            )
        except Exception as error:
            _log("Could not report manual Extended Clip recording stop: %s" % error)
    _state["extended_clip"] = None
    return True


def _cancel_owned_extended_recording(reason):
    context = _state.get("extended_clip")
    if not isinstance(context, dict):
        return False
    if context.get("owned_recording") and _obs_call_bool("obs_frontend_recording_active"):
        context["mode"] = "abandoning"
        _log("Stopping owned Extended Clip recording: %s" % reason)
        return _obs_invoke("obs_frontend_recording_stop")
    _state["extended_clip"] = None
    return True


def _on_frontend_event(event):
    if obs and event == getattr(obs, "OBS_FRONTEND_EVENT_RECORDING_STARTED", object()):
        extended = _state.get("extended_clip")
        if isinstance(extended, dict) and extended.get("mode") == "cancel_pending_start":
            extended["owned_recording"] = True
            extended["mode"] = "cancelling"
            if not _obs_invoke("obs_frontend_recording_stop"):
                _report_obs_error(extended.get("command_id"), "OBS recording stop API is unavailable.")
        elif isinstance(extended, dict) and extended.get("mode") == "starting":
            extended["owned_recording"] = True
            extended["mode"] = "waiting_overlap"
            _post_bridge_command_result(
                {"id": extended.get("command_id"), "status": "processing", "event": "recording_started"}
            )
            _schedule_extended_replay_save()
    if obs and event == getattr(obs, "OBS_FRONTEND_EVENT_RECORDING_STOPPED", object()):
        extended = _state.get("extended_clip")
        if isinstance(extended, dict):
            _complete_extended_recording_event(get_last_recording_path())
        context = _state.pop("pending_recording", None)
        if context is not None:
            path = get_last_recording_path()
            _send_job_after_obs_event("recording", path, context)
    if obs and event == getattr(obs, "OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED", object()):
        if _complete_extended_replay_event(get_last_replay_path()):
            return
        context = _state.pop("pending_replay", None)
        if context is not None:
            path = get_last_replay_path()
            _send_job_after_obs_event("moment", path, context)


def _send_job_after_obs_event(job_type, original_path, context):
    command_id = context.get("command_id") if isinstance(context, dict) else None
    if not original_path:
        message = "OBS did not provide an output path for %s." % job_type
        _log(message, visible=True)
        _report_obs_error(command_id, message, {"operation": job_type})
        return False
    payload = build_job_payload(job_type, original_path, context)
    if command_id:
        result = {"id": command_id, "status": "done", **payload}
        try:
            response = _post_json(load_bridge_config(), "/api/bridge/command-result", result)
            _log("Completed backend bridge command: %s" % response)
            return True
        except Exception as error:
            _log("Could not post backend bridge command result: %s" % error, visible=True)
            return False
    try:
        response = _post_json(load_bridge_config(), "/jobs", payload)
        _log("Created backend job: %s" % response)
        return True
    except Exception as error:
        _log("Could not post backend job: %s" % error, visible=True)
        return False


def find_project_root(script_path=None):
    current = Path(script_path or __file__).resolve()
    if current.is_file():
        current = current.parent
    candidates = [current, *current.parents]
    for candidate in candidates:
        has_config_anchor = (candidate / "config.toml").exists() or (candidate / "config.example.toml").exists()
        if has_config_anchor and (candidate / "src").exists():
            return candidate
    if current.name == "obs_bridge":
        return current.parent
    return current


def load_bridge_config(script_path=None):
    root = find_project_root(script_path)
    config = _deep_copy(DEFAULT_CONFIG)
    path = root / "config.toml"
    if path.exists():
        _deep_merge(config, _parse_minimal_toml(path.read_text(encoding="utf-8")))
    return config


def is_setup_complete(root=None):
    project_root = Path(root or find_project_root())
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    config_path = project_root / "config.toml"
    if not config_path.exists() or not venv_python.exists():
        return False
    config = load_bridge_config(project_root)
    setup = config.get("setup", {})
    if not setup.get("completed"):
        return False
    if not setup.get("dependencies_installed"):
        return False
    configured_venv = setup.get("venv_path")
    if configured_venv and not Path(str(configured_venv)).exists():
        return False
    return True


def check_backend_health(config=None):
    config = config or load_bridge_config()
    try:
        payload = _get_json(config, "/health")
    except HTTPError as error:
        return {"connected": False, "reachable": True, "error": "HTTP %s" % error.code}
    except (OSError, URLError, TimeoutError) as error:
        return {"connected": False, "reachable": False, "error": str(error)}
    expected = payload.get("app") == APP_NAME and payload.get("version") == APP_VERSION and payload.get("status") == "ok"
    return {"connected": bool(expected), "reachable": True, "payload": payload}


def build_job_payload(job_type, original_path, context=None):
    context = context or {}
    source_title = _clean_text(context.get("source_title"))
    payload = {
        "type": job_type,
        "original_path": str(original_path),
        "game_hint": source_title or _parent_folder_name(original_path),
        "scene_name": _clean_text(context.get("scene_name")),
        "source_name": _clean_text(context.get("source_name")),
        "source_title": source_title,
        "created_by": "obs_bridge",
    }
    return {key: value for key, value in payload.items() if value is not None}


def collect_obs_context():
    context = {"scene_name": None, "source_name": None, "source_title": None}
    if not obs:
        return context
    scene = _obs_call("obs_frontend_get_current_scene")
    if scene:
        try:
            context["scene_name"] = obs.obs_source_get_name(scene)
        finally:
            _obs_call("obs_source_release", scene)
    configured_source_name = _clean_text(_state.get("title_source_name"))
    if configured_source_name:
        source = _obs_call("obs_get_source_by_name", configured_source_name)
        if source:
            try:
                context["source_name"] = _safe_obs_source_name(source)
                context["source_title"] = _source_title_from_settings(source)
            finally:
                _obs_call("obs_source_release", source)
        return context
    source = _obs_call("obs_frontend_get_current_preview_scene") or scene
    if source:
        context["source_name"] = _safe_obs_source_name(source)
    return context


def get_last_recording_path():
    return _first_obs_string(
        "obs_frontend_get_last_recording",
        "obs_frontend_get_last_recording_path",
        "obs_frontend_get_current_record_output_path",
    )


def get_last_replay_path():
    return _first_obs_string(
        "obs_frontend_get_last_replay",
        "obs_frontend_get_last_replay_path",
        "obs_frontend_get_current_replay_output_path",
    )


def send_backend_error(message, details=None):
    payload = {"source": "obs_bridge", "message": message, "details": details or {}}
    try:
        return _post_json(load_bridge_config(), "/events/error", payload)
    except Exception as error:
        _log("Could not send backend error event: %s" % error, visible=True)
        return None


def _report_obs_error(command_id, message, details=None):
    if command_id:
        return _post_bridge_command_result({"id": command_id, "status": "error", "error": message})
    return send_backend_error(message, details)


def poll_bridge_commands():
    return _poll_bridge_commands()


def _register_frontend_callback():
    if obs:
        obs.obs_frontend_add_event_callback(_on_frontend_event)


def _register_command_polling():
    if obs and hasattr(obs, "timer_add") and not _state.get("polling_registered"):
        obs.timer_add(_poll_bridge_commands, 750)
        _state["polling_registered"] = True


def _register_hotkeys(settings):
    bindings = {
        "start_backend": ("SayClip Bridge: Start backend", request_start_backend),
        "stop_backend": ("SayClip Bridge: Stop backend", request_stop_backend),
        "hard_reset_backend": ("SayClip Bridge: Force Restart Backend", request_hard_reset_backend),
        "stop_recording_voice_rename": (
            "SayClip Bridge: Stop recording and voice rename",
            stop_recording_and_voice_rename,
        ),
        "save_replay_voice_rename": (
            "SayClip Bridge: Save replay buffer and voice rename",
            save_replay_buffer_and_voice_rename,
        ),
    }
    if not obs:
        return
    for name, (description, callback) in bindings.items():
        hotkey_id = obs.obs_hotkey_register_frontend(name, description, lambda pressed, cb=callback: pressed and cb())
        _state["hotkeys"][name] = hotkey_id
        saved = obs.obs_data_get_array(settings, name)
        obs.obs_hotkey_load(hotkey_id, saved)
        obs.obs_data_array_release(saved)


def _unregister_hotkeys():
    _state["hotkeys"] = {}


def _poll_bridge_commands():
    if not is_setup_complete():
        _set_backend_status("Setup Required")
        return False
    config = load_bridge_config()
    try:
        payload = _get_json(config, "/api/bridge/command")
    except Exception as error:
        _set_backend_status("Disconnected")
        _cancel_owned_extended_recording("backend_disconnected")
        _log_poll_error("Could not poll bridge commands: %s" % error)
        return False
    _set_backend_status("Connected")
    _post_bridge_state()
    command = payload.get("command")
    if command:
        _execute_bridge_command(command)
    return True


def _log_poll_error(message):
    now = time.monotonic()
    last = float(_state.get("last_poll_error_log_at") or 0.0)
    if now - last >= 10.0:
        _state["last_poll_error_log_at"] = now
        _log(message)


def _execute_bridge_command(command):
    command_id = str(command.get("id") or "")
    action = str(command.get("action") or "")
    ok = False
    error = None
    if command_id:
        _post_bridge_command_result({"id": command_id, "status": "processing"})
    try:
        if action == "save_moment":
            ok = bool(save_replay_buffer_and_voice_rename(command_id))
        elif action == "save_recording":
            ok = bool(stop_recording_and_voice_rename(command_id))
        elif action == "extended_clip_start":
            ok = bool(start_extended_clip(command_id))
        elif action == "extended_clip_finish":
            ok = bool(finish_extended_clip(command_id))
        elif action == "extended_clip_cancel":
            ok = bool(cancel_extended_clip(command_id))
        else:
            error = "Unknown command action: %s" % action
    except Exception as command_error:
        ok = False
        error = str(command_error)
        _log("Bridge command failed: %s" % error, visible=True)
    if command_id and error:
        _post_bridge_command_result({"id": command_id, "status": "error", "error": error})
    return ok


def _post_bridge_command_result(payload):
    try:
        return _post_json(load_bridge_config(), "/api/bridge/command-result", payload)
    except Exception as error:
        _log("Could not post bridge command result %s: %s" % (payload.get("id"), error))
        return None


def _post_bridge_state():
    payload = {
        "recording_active": _obs_call_bool("obs_frontend_recording_active"),
        "recording_paused": _obs_call_bool("obs_frontend_recording_paused"),
        "replay_buffer_active": _obs_call_bool("obs_frontend_replay_buffer_active"),
        "recording_output_path": _text_or_none(get_last_recording_path()),
        "replay_output_path": _text_or_none(get_last_replay_path()),
    }
    try:
        return _post_json(load_bridge_config(), "/api/bridge/state", payload)
    except Exception as error:
        _log_poll_error("Could not post bridge state: %s" % error)
        return None


def _terminate_known_backend_process(process):
    if not process or process.poll() is not None:
        return False
    try:
        process.terminate()
        process.wait(timeout=2)
        return True
    except Exception as error:
        _log("Could not terminate known backend process: %s" % error)
    try:
        process.kill()
        return True
    except Exception as error:
        _log("Could not kill known backend process: %s" % error)
        return False


def _kill_verified_backend_on_port(config):
    health = check_backend_health(config)
    if not health.get("connected"):
        if health.get("reachable"):
            _log("Configured backend port is occupied by a non SayClip service; not killing it", visible=True)
        return False
    pid = _pid_listening_on_port(int(config["backend"]["port"]))
    if not pid:
        _log("Could not find process bound to backend port")
        return False
    return _kill_pid(pid)


def _pid_listening_on_port(port):
    if sys.platform == "win32":
        try:
            output = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, errors="ignore")
        except Exception as error:
            _log("Could not inspect TCP ports with netstat: %s" % error)
            return None
        suffix = ":%s" % port
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            local_address, state, pid = parts[1], parts[3], parts[4]
            if state.upper() == "LISTENING" and local_address.endswith(suffix):
                try:
                    return int(pid)
                except ValueError:
                    return None
        return None
    try:
        output = subprocess.check_output(["lsof", "-ti", "tcp:%s" % port], text=True, errors="ignore")
    except Exception as error:
        _log("Could not inspect TCP ports with lsof: %s" % error)
        return None
    for line in output.splitlines():
        try:
            return int(line.strip())
        except ValueError:
            continue
    return None


def _kill_pid(pid):
    try:
        if sys.platform == "win32":
            subprocess.check_call(["taskkill", "/PID", str(pid), "/F"])
        else:
            os.kill(pid, 15)
        _log("Killed backend process on configured port: pid=%s" % pid)
        return True
    except Exception as error:
        _log("Could not kill process %s: %s" % (pid, error), visible=True)
        return False


def _props_start_backend(props, prop):
    return request_start_backend()


def _props_stop_backend(props, prop):
    return request_stop_backend()


def _props_hard_reset_backend(props, prop):
    return request_hard_reset_backend()


def _props_test_backend(props, prop):
    return request_test_backend()


def _props_open_backend_ui(props, prop):
    return open_backend_ui()


def _open_backend_ui():
    stop_backend()
    return start_backend(show_ui=True)


def _get_json(config, path):
    with urlopen(_url(config, path), timeout=0.5) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(config, path, payload):
    body = json.dumps(payload).encode("utf-8")
    request = Request(_url(config, path), data=body, method="POST", headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _url(config, path):
    backend = config["backend"]
    return "http://%s:%s%s" % (backend["host"], backend["port"], path)


def _settings_get_string(settings, key):
    if obs and settings:
        return obs.obs_data_get_string(settings, key)
    return ""


def _text_or_none(value):
    text = str(value or "").strip()
    return text or None


def _obs_call(name, *args):
    if not obs or not hasattr(obs, name):
        return None
    try:
        return getattr(obs, name)(*args)
    except Exception as error:
        _log("OBS API call failed: %s: %s" % (name, error), visible=True)
        return None


def _obs_invoke(name, *args):
    if not obs or not hasattr(obs, name):
        return False
    try:
        getattr(obs, name)(*args)
        return True
    except Exception as error:
        _log("OBS API call failed: %s: %s" % (name, error), visible=True)
        return False


def _obs_call_bool(name):
    return bool(_obs_call(name))


def _first_obs_string(*names):
    for name in names:
        value = _obs_call(name)
        if value:
            return str(value)
    return None


def _safe_obs_source_name(source):
    if obs and source and hasattr(obs, "obs_source_get_name"):
        try:
            return obs.obs_source_get_name(source)
        except Exception:
            return None
    return None


def _source_title_from_settings(source):
    if not obs or not source or not hasattr(obs, "obs_source_get_settings"):
        return None
    settings = None
    try:
        settings = obs.obs_source_get_settings(source)
        for key in ("title", "window_title", "window", "executable"):
            value = _obs_data_string(settings, key)
            title = _source_setting_to_title(value, key)
            if title:
                return title
    except Exception as error:
        _log("Could not read OBS source title settings: %s" % error)
    finally:
        if settings and hasattr(obs, "obs_data_release"):
            try:
                obs.obs_data_release(settings)
            except Exception:
                pass
    return None


def _obs_data_string(settings, key):
    if obs and settings and hasattr(obs, "obs_data_get_string"):
        try:
            return obs.obs_data_get_string(settings, key)
        except Exception:
            return None
    return None


def _source_setting_to_title(value, key):
    text = _clean_text(_decode_obs_setting_value(value))
    if not text:
        return None
    if key == "window":
        text = _window_setting_to_title(text)
    if key == "executable":
        text = Path(text).stem
    return _clean_text(text)


def _decode_obs_setting_value(value):
    if value is None:
        return None
    text = unquote(str(value))
    return re.sub(
        r"#(?:3a|22)",
        lambda match: ":" if match.group(0).lower() == "#3a" else "#",
        text,
        flags=re.IGNORECASE,
    )


def _window_setting_to_title(value):
    text = _clean_text(value)
    if not text:
        return None
    match = re.match(r"^\[[^\]]+\]:\s*(.+)$", text)
    if match:
        return _clean_text(match.group(1))
    if text.count(":") >= 2:
        return _clean_text(text.rsplit(":", 2)[0])
    return text


def _set_backend_status(value):
    with _state_lock:
        _state["backend_status"] = value


def _run_background(name, callback):
    with _state_lock:
        existing = _state["background"].get(name)
        if existing and existing.is_alive():
            _log("%s is already running" % name)
            return True
        thread = threading.Thread(target=_run_background_callback, args=(name, callback), daemon=True)
        _state["background"][name] = thread
        thread.start()
    return True


def _run_background_callback(name, callback):
    try:
        callback()
    except Exception as error:
        _set_backend_status("Error")
        _log("%s failed: %s" % (name, error), visible=True)


def _log(message, *, visible=False):
    if not visible and not _debug_logging_enabled():
        return
    text = "[SayClip Bridge] %s" % message
    _write_bridge_log(text)
    if visible and obs and hasattr(obs, "script_log"):
        try:
            obs.script_log(getattr(obs, "LOG_INFO", 300), text)
            return
        except Exception:
            pass
    if visible:
        print(text)


def _debug_logging_enabled():
    return str(os.environ.get("SAYCLIP_DEBUG", "")).strip().lower() in {"1", "true", "yes", "on"}


def _write_bridge_log(text):
    try:
        root = find_project_root()
        path = root / "logs" / "obs_bridge.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as handle:
            handle.write("%s %s\n" % (stamp, text))
    except Exception:
        return


def _creation_flags():
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _installer_command(installer):
    if os.name == "nt":
        return ["cmd.exe", "/c", str(installer)]
    return [str(installer)]


def _resolve_project_path(root, value):
    path = Path(str(value))
    if path.is_absolute():
        return path
    return (root / path).resolve()


def _build_backend_env(project_root):
    env = os.environ.copy()
    src_path = str((project_root / "src").resolve())
    current = env.get("PYTHONPATH", "")
    parts = [src_path]
    if current:
        parts.append(current)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _bridge_process_log_path(project_root):
    return project_root / "logs" / "obs_bridge_backend_process.log"


def _parent_folder_name(path):
    parent = Path(str(path)).parent.name.strip()
    return parent or None


def _clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _deep_copy(value):
    if isinstance(value, dict):
        return {key: _deep_copy(child) for key, child in value.items()}
    return value


def _deep_merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _parse_minimal_toml(text):
    data = {}
    current = data
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = data
            for part in line[1:-1].split("."):
                current = current.setdefault(part.strip(), {})
            continue
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        current[key.strip()] = _parse_toml_scalar(raw_value.strip())
    return data


def _parse_toml_scalar(value):
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    try:
        return int(value)
    except ValueError:
        return value


if __name__ == "__main__":
    if "--health" in sys.argv:
        print(json.dumps(check_backend_health(), ensure_ascii=False))
