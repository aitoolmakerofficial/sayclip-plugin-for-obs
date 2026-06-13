from __future__ import annotations

from pathlib import Path
import os

from instant_easy_rename_server.config import load_config, save_config


def update_config_from_environment(project_root: str | Path | None = None) -> None:
    root = Path(project_root or os.environ["IER_PROJECT_ROOT"])
    config = load_config(root)

    config.data.setdefault("setup", {})
    config.data["setup"]["completed"] = _env_bool("IER_SETUP_COMPLETED")
    config.data["setup"]["dependencies_installed"] = _env_bool("IER_SETUP_DEPENDENCIES_INSTALLED")
    config.data["setup"]["python_path"] = os.environ.get("IER_SETUP_PYTHON_PATH", "")
    config.data["setup"]["venv_path"] = os.environ.get("IER_SETUP_VENV_PATH", "")
    config.data["setup"]["completed_at"] = os.environ.get("IER_SETUP_COMPLETED_AT", "")

    config.data.setdefault("stt", {})
    config.data["stt"]["engine"] = "faster_whisper"
    config.data["stt"]["model_path"] = os.environ.get("IER_MODEL_PATH", "")
    config.data["stt"]["device"] = "cpu"
    config.data["stt"]["compute_type"] = "int8"
    config.data["stt"]["language"] = os.environ.get("IER_LANGUAGE", "ru")
    config.data["stt"]["offline_only"] = True

    config.data.setdefault("audio", {})
    config.data["audio"]["device"] = os.environ.get("IER_AUDIO_DEVICE", "") or "default"

    config.data.setdefault("naming", {})
    config.data["naming"]["format"] = os.environ.get("IER_FILENAME_FORMAT", "") or config.data["naming"].get(
        "format",
        "{source}__{datetime}__{title}",
    )

    save_config(config)


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "false").lower() == "true"


def main() -> int:
    update_config_from_environment()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
