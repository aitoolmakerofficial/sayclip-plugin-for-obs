from datetime import datetime
from pathlib import Path

import pytest

from instant_easy_rename_server.naming import (
    format_filename,
    next_available_path,
    sanitize_slug,
    short_source_token,
)


def test_sanitizer_kebab_case_and_windows_forbidden_chars() -> None:
    assert sanitize_slug(' Clean: Overtake / Last* Corner? ') == "clean-overtake-last-corner"


def test_sanitizer_keeps_unicode() -> None:
    assert sanitize_slug("Чистый обгон") == "чистый-обгон"


def test_sanitizer_decodes_percent_encoded_title_chars() -> None:
    assert sanitize_slug("Honkai%3A Star Rail") == "honkai-star-rail"
    assert sanitize_slug("Honkai%3A%20Star%20Rail") == "honkai-star-rail"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("DemoTormentedSouls2__", "demotouls2"),
        ("METAL_GEAR_SOLID_Δ**SNAKE_EATER**", "mgsδse"),
        ("Banishers__Ghosts_of_New_Eden__", "bgone"),
        ("Dying_Light__The_Beast_(inactive)", "dltbi"),
        ("Portal", "portal"),
        ("HellIsUs", "hellisus"),
        ("RedDeadRedemption", "reddeption"),
    ],
)
def test_short_source_token(source: str, expected: str) -> None:
    assert short_source_token(source) == expected


def test_formatter_supports_short_source_token() -> None:
    filename = format_filename(
        game="Banishers Ghosts of New Eden",
        job_type="moment",
        original_path="D:/Recordings/clip.mkv",
        title="clean overtake",
        when=datetime(2026, 5, 27, 23, 0, 0),
        filename_format="{short_source}__{job_type}__{title}",
    )

    assert filename == "bgone__clip__clean-overtake.mkv"


def test_formatter_acceptance_example() -> None:
    filename = format_filename(
        game="Test Game",
        job_type="moment",
        original_path="D:/Recordings/Test Game/Replays/2026-05-27 22-10-44.mkv",
        title="clean overtake",
        when=datetime(2026, 5, 27, 23, 0, 0),
        filename_format="{source}__{job_type}__{datetime}__{title}",
    )

    assert filename == "test-game__clip__2026-05-27_22-10-44__clean-overtake.mkv"


def test_formatter_uses_configurable_format() -> None:
    filename = format_filename(
        game="Test Game",
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
        game="Test Game",
        job_type="moment",
        original_path="D:/Recordings/clip.mkv",
        title="clean overtake",
        when=datetime(2026, 5, 27, 23, 0, 0),
        filename_format="{game}__{title}",
    )

    assert filename == "test-game__clean-overtake.mkv"


def test_formatter_builds_relative_folders() -> None:
    filename = format_filename(
        game="Test Game",
        job_type="moment",
        original_path="D:/Recordings/moments/clip.mkv",
        title="clean overtake",
        when=datetime(2026, 5, 27, 23, 0, 0),
        filename_format="{source}/{job_type}/{datetime}__{title}",
        datetime_format="%Y-%m-%d",
    )

    assert filename == "test-game/clip/2026-05-27__clean-overtake.mkv"


@pytest.mark.parametrize("filename_format", ["../{title}", "/{title}", r"C:\{title}"])
def test_formatter_rejects_paths_outside_obs_folder(filename_format: str) -> None:
    with pytest.raises(ValueError):
        format_filename(
            game="Test Game",
            job_type="moment",
            original_path="D:/Recordings/clip.mkv",
            title="clean overtake",
            when=datetime(2026, 5, 27, 23, 0, 0),
            filename_format=filename_format,
        )


def test_conflict_suffixing(tmp_path: Path) -> None:
    first = tmp_path / "clip.mkv"
    second = tmp_path / "clip (2).mkv"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")

    assert next_available_path(first).name == "clip (3).mkv"
