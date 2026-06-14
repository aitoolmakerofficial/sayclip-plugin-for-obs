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
        ("datetime", True),
        ("title", True),
        ("source", False),
        ("job_type", False),
    ]


def test_rename_format_builder_keeps_unsupported_custom_format() -> None:
    parts, custom = _rename_format_parts_from_template("{source}-{title}")

    assert custom == "{source}-{title}"
    assert parts[-1] == ("title", True)


def test_rename_format_builder_builds_enabled_parts_and_keeps_title() -> None:
    template = _rename_format_template_from_parts(
        [("source", False), ("job_type", True), ("datetime", True), ("title", True)]
    )

    assert template == "{job_type}__{datetime}__{title}"


def test_move_rename_part_inserts_selected_part_at_target_index() -> None:
    order = ["source", "job_type", "datetime", "title"]

    assert _move_rename_part(order, "title", 1) == ["source", "title", "job_type", "datetime"]
