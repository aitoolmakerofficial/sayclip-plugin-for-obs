from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


FORBIDDEN_WINDOWS_CHARS = '<>:"/\\|?*'
JOB_TYPE_TOKENS = {"recording": "rec", "moment": "mom"}


def sanitize_slug(value: str, fallback: str = "untitled") -> str:
    text = value.lower()
    text = "".join("-" if char in FORBIDDEN_WINDOWS_CHARS else char for char in text)
    text = "".join("" if ord(char) < 32 else char for char in text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^\w\-.]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-. ")
    return text or fallback


def game_from_request(
    original_path: str,
    source_title: str | None,
    game_hint: str | None,
    unknown_game_token: str = "unknown-game",
) -> str:
    if source_title:
        return sanitize_slug(source_title, fallback=unknown_game_token)
    if game_hint:
        return sanitize_slug(game_hint, fallback=unknown_game_token)
    parent = Path(original_path).parent.name
    return sanitize_slug(parent, fallback=unknown_game_token)


def format_filename(
    *,
    game: str,
    job_type: str,
    original_path: str | Path,
    title: str,
    when: datetime,
    filename_format: str = "{source}__{datetime}__{title}",
    datetime_format: str = "%Y-%m-%d_%H-%M-%S",
    job_type_tokens: dict[str, str] | None = None,
    unknown_source_token: str = "unknown-game",
) -> str:
    tokens = job_type_tokens or JOB_TYPE_TOKENS
    source = Path(original_path)
    extension = source.suffix
    date_value = _datetime_from_source(source, when).strftime(datetime_format)
    source_value = _source_token(game, unknown_source_token)
    values = {
        "source": source_value,
        "game": sanitize_slug(game, fallback=unknown_source_token),
        "job_type": tokens[job_type],
        "datetime": date_value,
        "title": sanitize_slug(title),
    }
    name = filename_format.format(**values)
    name = sanitize_filename_template_result(name)
    return f"{name}{extension}"


def sanitize_filename_template_result(value: str, fallback: str = "untitled") -> str:
    text = "".join("-" if char in FORBIDDEN_WINDOWS_CHARS else char for char in value)
    text = "".join("" if ord(char) < 32 else char for char in text)
    text = re.sub(r"[\s]+", "-", text)
    text = re.sub(r"__+", "__", text)
    text = re.sub(r"--+", "-", text)
    text = re.sub(r"(^[-_.]+|[-_.]+$)", "", text)
    return text or fallback


def _source_token(value: str, unknown_source_token: str) -> str:
    source = sanitize_slug(value, fallback="")
    if source == sanitize_slug(unknown_source_token, fallback=""):
        return ""
    return source


def next_available_path(path: Path) -> Path:
    if not path.exists():
        return path

    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}({index}){path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _datetime_from_source(path: Path, fallback: datetime) -> datetime:
    match = re.search(r"(\d{4}-\d{2}-\d{2})[ _](\d{2}-\d{2}-\d{2})", path.stem)
    if not match:
        return fallback
    return datetime.strptime(f"{match.group(1)}_{match.group(2)}", "%Y-%m-%d_%H-%M-%S")
