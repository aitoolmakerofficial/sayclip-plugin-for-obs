from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat


DEFAULT_DISCARD_FOLDER_NAME = "SayClip Discarded"
DISCARD_MODE_MOVE = "move"
DISCARD_MODE_DELETE_PERMANENTLY = "delete_permanently"
_WINDOWS_INVALID_NAME_CHARS = set('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class DiscardRecordingError(RuntimeError):
    """Raised when a recording cannot be discarded safely."""


@dataclass(frozen=True)
class DiscardRecordingResult:
    mode: str
    source_path: Path
    destination_path: Path | None


class DiscardRecordingService:
    def discard(
        self,
        recording_path: str | Path,
        recording_output_root: str | Path,
        *,
        mode: str,
        folder_name: str = DEFAULT_DISCARD_FOLDER_NAME,
    ) -> DiscardRecordingResult:
        source = _validated_regular_file(recording_path)
        normalized_mode = str(mode or "").strip()
        if normalized_mode == DISCARD_MODE_DELETE_PERMANENTLY:
            try:
                source.unlink()
            except OSError as error:
                raise DiscardRecordingError("The recording file could not be deleted.") from error
            return DiscardRecordingResult(normalized_mode, source, None)
        if normalized_mode != DISCARD_MODE_MOVE:
            raise DiscardRecordingError("The configured discard mode is invalid.")

        output_root = _validated_output_root(recording_output_root)
        safe_folder_name = validate_discard_folder_name(folder_name)
        if not _paths_are_on_same_volume(source, output_root):
            raise DiscardRecordingError("Moving discarded recordings between disks is not supported.")

        destination_dir = output_root / safe_folder_name
        try:
            destination_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise DiscardRecordingError("The discarded recordings folder could not be created.") from error

        destination = _reserve_destination(destination_dir, source.name)
        try:
            os.replace(source, destination)
        except OSError as error:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
            raise DiscardRecordingError("The recording file could not be moved.") from error
        return DiscardRecordingResult(normalized_mode, source, destination)


def validate_discard_folder_name(value: str) -> str:
    name = str(value or "").strip() or DEFAULT_DISCARD_FOLDER_NAME
    if name in {".", ".."} or any(character in _WINDOWS_INVALID_NAME_CHARS for character in name):
        raise DiscardRecordingError("The discarded recordings folder name is invalid.")
    if any(ord(character) < 32 for character in name) or name.endswith((" ", ".")):
        raise DiscardRecordingError("The discarded recordings folder name is invalid.")
    if name.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        raise DiscardRecordingError("The discarded recordings folder name is invalid.")
    return name


def _validated_regular_file(value: str | Path) -> Path:
    text = str(value or "").strip()
    if not text:
        raise DiscardRecordingError("OBS did not provide a recording path.")
    source = Path(text)
    try:
        source_stat = source.lstat()
    except OSError as error:
        raise DiscardRecordingError("The recording file is missing or unavailable.") from error
    if not stat.S_ISREG(source_stat.st_mode):
        raise DiscardRecordingError("The recording path is not a regular file.")
    return source


def _validated_output_root(value: str | Path) -> Path:
    text = str(value or "").strip()
    if not text:
        raise DiscardRecordingError("OBS did not provide its recording output directory.")
    root = Path(text)
    if not root.is_dir():
        raise DiscardRecordingError("The OBS recording output directory is unavailable.")
    return root


def _paths_are_on_same_volume(source: Path, output_root: Path) -> bool:
    if source.drive or output_root.drive:
        return source.drive.casefold() == output_root.drive.casefold()
    try:
        return source.stat().st_dev == output_root.stat().st_dev
    except OSError:
        return False


def _reserve_destination(directory: Path, original_name: str) -> Path:
    suffix = "".join(Path(original_name).suffixes)
    stem = original_name[: -len(suffix)] if suffix else original_name
    index = 0
    while True:
        candidate_name = original_name if index == 0 else f"{stem} ({index}){suffix}"
        candidate = directory / candidate_name
        try:
            descriptor = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            index += 1
            continue
        except OSError as error:
            raise DiscardRecordingError("A destination filename could not be reserved.") from error
        os.close(descriptor)
        return candidate
