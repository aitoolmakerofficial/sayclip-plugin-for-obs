from datetime import datetime
from pathlib import Path

from instant_easy_rename_server.naming import format_filename, next_available_path, sanitize_slug


def test_sanitizer_kebab_case_and_windows_forbidden_chars() -> None:
    assert sanitize_slug(' Clean: Overtake / Last* Corner? ') == "clean-overtake-last-corner"


def test_sanitizer_keeps_unicode() -> None:
    assert sanitize_slug("Чистый обгон") == "чистый-обгон"


def test_formatter_acceptance_example() -> None:
    filename = format_filename(
        game="Forza Horizon 6",
        job_type="moment",
        original_path="D:/Recordings/Forza Horizon 6/Replays/2026-05-27 22-10-44.mkv",
        title="clean overtake",
        when=datetime(2026, 5, 27, 23, 0, 0),
        filename_format="{source}__{job_type}__{datetime}__{title}",
    )

    assert filename == "forza-horizon-6__mom__2026-05-27_22-10-44__clean-overtake.mkv"


def test_formatter_uses_configurable_format() -> None:
    filename = format_filename(
        game="Forza Horizon 6",
        job_type="recording",
        original_path="D:/Recordings/clip.mkv",
        title="clean overtake",
        when=datetime(2026, 5, 27, 23, 0, 0),
        filename_format="{datetime}__{title}",
    )

    assert filename == "2026-05-27_23-00-00__clean-overtake.mkv"


def test_formatter_omits_unknown_source_token() -> None:
    filename = format_filename(
        game="unknown-game",
        job_type="moment",
        original_path="D:/Recordings/clip.mkv",
        title="clean overtake",
        when=datetime(2026, 5, 27, 23, 0, 0),
    )

    assert filename == "2026-05-27_23-00-00__clean-overtake.mkv"


def test_formatter_keeps_legacy_game_token() -> None:
    filename = format_filename(
        game="Forza Horizon 6",
        job_type="moment",
        original_path="D:/Recordings/clip.mkv",
        title="clean overtake",
        when=datetime(2026, 5, 27, 23, 0, 0),
        filename_format="{game}__{title}",
    )

    assert filename == "forza-horizon-6__clean-overtake.mkv"


def test_conflict_suffixing(tmp_path: Path) -> None:
    first = tmp_path / "clip.mkv"
    second = tmp_path / "clip(2).mkv"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")

    assert next_available_path(first).name == "clip(3).mkv"
