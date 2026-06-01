from __future__ import annotations

import argparse
import ctypes
import threading
import logging
import os
import sys
import time

from .api import BackendApi
from .config import load_config
from .logging_setup import configure_logging
from .server import create_server
from .ui import run_ui


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    config = load_config()
    configure_logging(config)
    logger = logging.getLogger(__name__)
    logger.info("Starting backend app: headless=%s", args.headless)
    api = BackendApi(config)
    if args.obs_pid:
        threading.Thread(target=_monitor_obs_process, args=(api, args.obs_pid), daemon=True).start()
    server = create_server(api)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f"SayClip listening on http://{config.backend_host}:{config.backend_port}")
    try:
        if args.headless:
            _run_headless(api)
        else:
            run_ui(api, server)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        logger.info("Shutting down backend app")
        api.request_shutdown()
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.set_defaults(headless=True)
    parser.add_argument("--headless", action="store_true", dest="headless")
    parser.add_argument("--ui", action="store_false", dest="headless")
    parser.add_argument("--obs-pid", type=int, default=None)
    return parser.parse_args(argv)


def _run_headless(api: BackendApi) -> None:
    while not api.shutdown_requested.is_set():
        time.sleep(0.2)


def _monitor_obs_process(api: BackendApi, obs_pid: int) -> None:
    logger = logging.getLogger(__name__)
    logger.info("Monitoring OBS process: pid=%s", obs_pid)
    while not api.shutdown_requested.is_set():
        if not _process_exists(obs_pid):
            logger.info("OBS process disappeared; backend will shut down")
            api.request_shutdown()
            return
        time.sleep(1.0)


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        handle = ctypes.windll.kernel32.OpenProcess(0x100000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
