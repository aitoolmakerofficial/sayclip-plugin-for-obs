from pathlib import Path

from instant_easy_rename_server.ui import _empty_jobs_row, _folder_for_paths, _presentation_row


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
