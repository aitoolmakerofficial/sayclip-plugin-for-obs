from instant_easy_rename_server.config import load_config
from instant_easy_rename_server.onboarding_config import update_config_from_environment


def test_onboarding_config_updates_config_from_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("IER_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("IER_MODEL_PATH", str(tmp_path / "models" / "fw"))
    monkeypatch.setenv("IER_AUDIO_DEVICE", "Mic One")
    monkeypatch.setenv("IER_LANGUAGE", "en")
    monkeypatch.setenv("IER_FILENAME_FORMAT", "{source}__{title}")
    monkeypatch.setenv("IER_SETUP_PYTHON_PATH", r"C:\Python313\python.exe")
    monkeypatch.setenv("IER_SETUP_VENV_PATH", str(tmp_path / ".venv"))
    monkeypatch.setenv("IER_SETUP_DEPENDENCIES_INSTALLED", "true")
    monkeypatch.setenv("IER_SETUP_COMPLETED", "true")
    monkeypatch.setenv("IER_SETUP_COMPLETED_AT", "2026-06-01T16:00:00Z")

    update_config_from_environment()

    config = load_config(tmp_path)
    assert config.data["setup"]["completed"] is True
    assert config.data["setup"]["dependencies_installed"] is True
    assert config.data["setup"]["python_path"] == r"C:\Python313\python.exe"
    assert config.data["setup"]["completed_at"] == "2026-06-01T16:00:00Z"
    assert config.data["stt"]["engine"] == "faster_whisper"
    assert config.data["stt"]["model_path"] == str(tmp_path / "models" / "fw")
    assert config.data["stt"]["language"] == "en"
    assert config.data["audio"]["device"] == "Mic One"
    assert config.data["naming"]["format"] == "{source}__{title}"
