from pathlib import Path

from instant_easy_rename_server.config import load_config, save_config


def test_load_default_config_when_file_missing(tmp_path: Path) -> None:
    config = load_config(tmp_path)

    assert config.app_name == "SayClip"
    assert config.app_version == "2.0.0"
    assert config.backend_host == "127.0.0.1"
    assert config.audio["max_record_seconds"] == 8
    assert config.extended_clip["output_container"] == "mkv"
    assert config.extended_clip["match_window_seconds"] == 3.0
    assert config.extended_clip["delete_sources_after_success"] is False


def test_load_config_migrates_legacy_app_name(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text('[app]\nname = "Instant Easy Rename"\n', encoding="utf-8")

    config = load_config(tmp_path)

    assert config.app_name == "SayClip"
    assert config.audio["beep_start"] is True
    assert config.audio["beep_end"] is True


def test_runtime_version_cannot_be_downgraded_by_local_config(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text('[app]\nversion = "1.0.0"\n', encoding="utf-8")

    config = load_config(tmp_path)

    assert config.app_version == "2.0.0"
    assert config.data["app"]["version"] == "2.0.0"


def test_default_jobs_limit_is_latest_50(tmp_path: Path) -> None:
    config = load_config(tmp_path)

    assert config.max_jobs == 50


def test_legacy_jobs_json_settings_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        '[jobs]\npersist_to_json = true\njson_path = "jobs.json"\nmax_jobs_in_ui = 75\n',
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.max_jobs == 75
    assert "persist_to_json" not in config.data["jobs"]
    assert "json_path" not in config.data["jobs"]


def test_save_config_round_trips_audio_and_stt_settings(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    config.data["stt"]["engine"] = "faster_whisper"
    config.data["stt"]["model_path"] = "./models/faster-whisper-tiny"
    config.data["stt"]["language"] = "en"
    config.data["audio"]["device"] = "default"

    save_config(config)
    reloaded = load_config(tmp_path)

    assert reloaded.stt["engine"] == "faster_whisper"
    assert reloaded.stt["model_path"] == "./models/faster-whisper-tiny"
    assert reloaded.stt["language"] == "en"
    assert reloaded.audio["device"] == "default"
