from __future__ import annotations

from pathlib import Path
from types import TracebackType
import faulthandler
import logging
import sys

from .config import AppConfig


def configure_logging(config: AppConfig) -> Path:
    log_path = config.resolve_path(str(config.data["logging"]["log_path"]))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, str(config.data["logging"].get("level", "INFO")).upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)
    try:
        fault_log = (log_path.parent / "instant_easy_rename_server_faults.log").open("a", encoding="utf-8")
        faulthandler.enable(file=fault_log)
    except OSError:
        logging.getLogger(__name__).exception("Failed to enable fault handler")

    sys.excepthook = _log_uncaught_exception
    logging.getLogger(__name__).debug("Logging configured: %s", log_path)
    return log_path


def _log_uncaught_exception(
    exception_type: type[BaseException],
    exception: BaseException,
    traceback: TracebackType | None,
) -> None:
    logging.getLogger("instant_easy_rename_server.uncaught").error(
        "Uncaught exception",
        exc_info=(exception_type, exception, traceback),
    )
