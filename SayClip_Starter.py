from __future__ import annotations

from pathlib import Path
import importlib.util


YOUTUBE_GUIDE_URL = "https://www.youtube.com/@WorkingAiTools"
OBS_DOCK_URL = "http://127.0.0.1:17891/dock"


def _load_bridge():
    path = Path(__file__).resolve().parent / "src" / "obs" / "instant_bridge.py"
    spec = importlib.util.spec_from_file_location("sayclip_bridge", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("Could not load SayClip Bridge.")
    spec.loader.exec_module(module)
    return module


_bridge = _load_bridge()


def script_description():
    return (
        "<h4>SayClip app</h4>"
        f"YouTube guide: <a href='{YOUTUBE_GUIDE_URL}'>open guide</a>.<br>"
        f"OBS dock: <a href='{OBS_DOCK_URL}'>open dock</a>."
    )


def script_load(settings):
    return _bridge.script_load(settings)


def script_unload():
    return _bridge.script_unload()


def script_update(settings):
    return _bridge.script_update(settings)


def script_save(settings):
    return _bridge.script_save(settings)


def script_properties():
    return _bridge.script_properties()


def script_defaults(settings):
    return _bridge.script_defaults(settings)
