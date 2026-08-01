from pathlib import Path

from instant_easy_rename_server.ui import (
    _empty_jobs_row,
    _folder_for_paths,
    _move_rename_part,
    _presentation_row,
    _rename_format_parts_from_template,
    _rename_format_template_from_parts,
)


def test_folder_for_paths_prefers_final_path() -> None:
    folder = _folder_for_paths("D:/Recordings/Game/final.mkv", "D:/Recordings/Game/original.mkv")

    assert folder == Path("D:/Recordings/Game")


def test_folder_for_paths_falls_back_to_original_path() -> None:
    folder = _folder_for_paths("", "D:/Recordings/Game/original.mkv")

    assert folder == Path("D:/Recordings/Game")


def test_empty_jobs_row_keeps_table_shape() -> None:
    assert _presentation_row(_empty_jobs_row()) == [
        "-",
        "idle",
        "-",
        "No jobs yet",
        "",
        "Current session is empty",
    ]


def test_rename_format_builder_parses_known_subset() -> None:
    parts, custom = _rename_format_parts_from_template("{datetime}__{title}")

    assert custom is None
    assert parts == [
        ("datetime", True, False),
        ("source", False, False),
        ("short_source", False, False),
        ("job_type", False, False),
        ("title", True, False),
    ]


def test_rename_format_builder_keeps_unsupported_custom_format() -> None:
    parts, custom = _rename_format_parts_from_template("{source}-{title}")

    assert custom == "{source}-{title}"
    assert parts[-1] == ("title", True, False)


def test_rename_format_builder_builds_enabled_parts_and_keeps_title() -> None:
    template = _rename_format_template_from_parts(
        [
            ("source", False, False),
            ("job_type", True, False),
            ("datetime", True, False),
            ("title", True, False),
        ]
    )

    assert template == "{job_type}__{datetime}__{title}"


def test_rename_format_builder_parses_folder_boundaries() -> None:
    parts, custom = _rename_format_parts_from_template("{source}/{job_type}/{datetime}__{title}")

    assert custom is None
    assert parts == [
        ("source", True, True),
        ("job_type", True, True),
        ("datetime", True, False),
        ("short_source", False, False),
        ("title", True, False),
    ]


def test_rename_format_builder_builds_folder_boundaries() -> None:
    template = _rename_format_template_from_parts(
        [
            ("source", True, True),
            ("job_type", True, True),
            ("datetime", False, False),
            ("title", True, False),
        ]
    )

    assert template == "{source}/{job_type}/{title}"


def test_rename_format_builder_supports_short_source() -> None:
    parts, custom = _rename_format_parts_from_template("{source}/{short_source}__{job_type}__{title}")

    assert custom is None
    assert parts == [
        ("source", True, True),
        ("short_source", True, False),
        ("job_type", True, False),
        ("datetime", False, False),
        ("title", True, False),
    ]


def test_rename_format_builder_keeps_voice_title_out_of_folders() -> None:
    parts, custom = _rename_format_parts_from_template("{title}__{source}/{job_type}")

    assert custom == "{title}__{source}/{job_type}"
    assert parts[-1] == ("title", True, False)

    template = _rename_format_template_from_parts(
        [
            ("title", True, False),
            ("source", True, True),
            ("job_type", False, False),
            ("datetime", False, False),
        ]
    )
    assert template == "{title}__{source}"


def test_move_rename_part_inserts_selected_part_at_target_index() -> None:
    order = ["source", "job_type", "datetime", "title"]

    assert _move_rename_part(order, "title", 1) == ["source", "title", "job_type", "datetime"]
