# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 AI Toolmaker (AI Toolmaker Official)

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tomllib

from . import APP_VERSION
from .use_cases.discard_recording import (
    DEFAULT_DISCARD_FOLDER_NAME,
    DISCARD_MODE_DELETE_PERMANENTLY,
    DISCARD_MODE_MOVE,
    DiscardRecordingError,
    validate_discard_folder_name,
)


DEFAULT_CONFIG: dict[str, Any] = {
    "app": {"name": "SayClip", "version": APP_VERSION},
    "backend": {
        "host": "127.0.0.1",
        "port": 17891,
        "start_mode": "on_obs_start",
        "process": {
            "python_path": ".venv/Scripts/pythonw.exe",
            "module": "instant_easy_rename_server",
        },
    },
    "obs": {"prefer_source_title": True, "fallback_to_parent_folder": True},
    "setup": {
        "completed": False,
        "dependencies_installed": False,
        "python_path": "",
        "venv_path": "",
        "completed_at": "",
    },
    "naming": {
        "format": "{source}__{datetime}__{title}",
        "datetime_format": "%Y-%m-%d_%H-%M-%S",
        "include_job_type": True,
        "unknown_game_token": "unknown-game",
        "title_language_mode": "keep",
        "keep_extension": True,
        "on_conflict": "increment",
        "job_type_tokens": {"recording": "rec", "moment": "clip", "extended_clip": "extended-clip"},
    },
    "jobs": {
        "max_jobs_in_ui": 50,
    },
    "discard": {
        "mode": "move",
        "folder_name": "SayClip Discarded",
    },
    "extended_clip": {
        "enabled": True,
        "overlap_wait_seconds": 1.5,
        "min_video_packets": 16,
        "audio_packets": 8,
        "seam_decode_seconds": 2.0,
        "match_window_seconds": 3.0,
        "ffmpeg": "ffmpeg",
        "ffprobe": "ffprobe",
        "runtime_path": ".local/extended-clip/session.json",
        "output_container": "mkv",
        "delete_sources_after_success": False,
    },
    "microphone_guard": {
        "enabled": True,
        "source_name": "Mic/Aux",
        "silence_seconds": 30,
        "threshold_db": -60,
    },
    "audio": {
        "device": "fake",
        "max_record_seconds": 8,
        "silence_stop_enabled": True,
        "silence_seconds": 5,
        "beep_start": True,
        "beep_end": True,
        "show_level_meter": True,
        "keep_temp_audio": False,
    },
    "stt": {
        "engine": "fake",
        "model_path": "",
        "device": "cpu",
        "compute_type": "int8",
        "language": "ru",
        "offline_only": True,
        "fake_transcript": "test voice title",
    },
    "logging": {"log_path": "logs/instant_easy_rename_server.log", "level": "INFO"},
    "ui": {
        "theme": "dark",
        "show_mic_meter": True,
        "show_jobs_table": True,
        "show_additional_setup": True,
    },
}


@dataclass(frozen=True)
class AppConfig:
    root: Path
    data: dict[str, Any]

    @property
    def app_name(self) -> str:
        return str(self.data["app"]["name"])

    @property
    def app_version(self) -> str:
        return APP_VERSION

    @property
    def backend_host(self) -> str:
        return str(self.data["backend"]["host"])

    @property
    def backend_port(self) -> int:
        return int(self.data["backend"]["port"])

    @property
    def max_jobs(self) -> int:
        return int(self.data["jobs"]["max_jobs_in_ui"])

    @property
    def naming(self) -> dict[str, Any]:
        return self.data["naming"]

    @property
    def audio(self) -> dict[str, Any]:
        return self.data["audio"]

    @property
    def stt(self) -> dict[str, Any]:
        return self.data["stt"]

    @property
    def extended_clip(self) -> dict[str, Any]:
        return self.data["extended_clip"]

    @property
    def discard(self) -> dict[str, Any]:
        return self.data["discard"]

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (self.root / path).resolve()


def load_config(root: Path | str | None = None, filename: str = "config.toml") -> AppConfig:
    project_root = Path(root or Path.cwd()).resolve()
    path = project_root / filename
    data = _deep_copy(DEFAULT_CONFIG)
    if path.exists():
        with path.open("rb") as handle:
            data = _deep_merge(data, tomllib.load(handle))
    _migrate_legacy_branding(data)
    _normalize_discard_config(data)
    data["app"]["version"] = APP_VERSION
    _drop_legacy_job_persistence(data)
    return AppConfig(root=project_root, data=data)


def save_config(config: AppConfig, filename: str = "config.toml") -> None:
    path = config.root / filename
    path.write_text(_to_toml(config.data), encoding="utf-8")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_copy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_deep_copy(child) for child in value]
    return value


def _drop_legacy_job_persistence(data: dict[str, Any]) -> None:
    jobs = data.get("jobs")
    if not isinstance(jobs, dict):
        return
    jobs.pop("persist_to_json", None)
    jobs.pop("json_path", None)


def _migrate_legacy_branding(data: dict[str, Any]) -> None:
    app = data.get("app")
    if isinstance(app, dict) and app.get("name") == "Instant Easy Rename":
        app["name"] = "SayClip"


def _normalize_discard_config(data: dict[str, Any]) -> None:
    discard = data.setdefault("discard", {})
    mode = str(discard.get("mode") or DISCARD_MODE_MOVE).strip()
    if mode not in {DISCARD_MODE_MOVE, DISCARD_MODE_DELETE_PERMANENTLY}:
        mode = DISCARD_MODE_MOVE
    try:
        folder_name = validate_discard_folder_name(str(discard.get("folder_name") or ""))
    except DiscardRecordingError:
        folder_name = DEFAULT_DISCARD_FOLDER_NAME
    discard["mode"] = mode
    discard["folder_name"] = folder_name


def _to_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for section, value in data.items():
        if isinstance(value, dict):
            _write_table(lines, [section], value)
        else:
            lines.append(f"{section} = {_format_toml_value(value)}")
    return "\n".join(lines).rstrip() + "\n"


def _write_table(lines: list[str], path: list[str], data: dict[str, Any]) -> None:
    if lines:
        lines.append("")
    lines.append(f"[{'.'.join(path)}]")
    nested: list[tuple[str, dict[str, Any]]] = []
    for key, value in data.items():
        if isinstance(value, dict):
            nested.append((key, value))
        else:
            lines.append(f"{key} = {_format_toml_value(value)}")
    for key, value in nested:
        _write_table(lines, [*path, key], value)


def _format_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'
