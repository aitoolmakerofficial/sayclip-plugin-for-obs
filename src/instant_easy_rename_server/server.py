# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 AI Toolmaker (AI Toolmaker Official)

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import logging
import json
import threading
from urllib.parse import urlparse

from .api import BackendApi
from . import APP_VERSION
from .config import load_config


logger = logging.getLogger(__name__)
DOCK_STATIC_DIR = Path(__file__).resolve().parent / "dock_static"


def make_handler(api: BackendApi) -> type[BaseHTTPRequestHandler]:
    class SayClipHandler(BaseHTTPRequestHandler):
        server_version = f"SayClip/{APP_VERSION}"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/health":
                self._send_json(200, api.health())
                return
            if path == "/jobs":
                self._send_json(200, api.list_jobs())
                return
            if path == "/errors":
                self._send_json(200, api.list_errors())
                return
            if path == "/api/status":
                self._send_json(200, api.status())
                return
            if path == "/dock":
                self._send_file(200, DOCK_STATIC_DIR / "dock.html", "text/html; charset=utf-8")
                return
            if path == "/dock/static/dock.css":
                self._send_file(200, DOCK_STATIC_DIR / "dock.css", "text/css; charset=utf-8")
                return
            if path == "/dock/static/dock.js":
                self._send_file(200, DOCK_STATIC_DIR / "dock.js", "application/javascript; charset=utf-8")
                return
            if path == "/api/bridge/command":
                self._send_json(200, api.poll_bridge_command())
                return
            self._send_json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            try:
                payload = self._read_json()
                path = urlparse(self.path).path
                if path == "/jobs":
                    self._send_json(201, api.create_job_async(payload))
                    return
                if path == "/events/error":
                    self._send_json(202, api.record_error(payload))
                    return
                if path in {"/shutdown", "/api/system/shutdown"}:
                    result = api.request_shutdown()
                    self._send_json(202 if result.get("ok") else 500, {"status": "shutting_down", **result})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                if path == "/api/system/open-folder":
                    result = api.open_latest_output_folder()
                    self._send_json(200 if result.get("ok") else 422, result)
                    return
                if path == "/api/save/moment":
                    result = api.save_moment()
                    self._send_json(_save_status_code(result), result)
                    return
                if path == "/api/save/recording":
                    result = api.save_recording()
                    self._send_json(_save_status_code(result), result)
                    return
                if path == "/api/discard/recording":
                    if payload:
                        raise ValueError("Discard recording request body must be empty")
                    result = api.discard_recording()
                    self._send_json(_save_status_code(result), result)
                    return
                if path == "/api/extended-clip/start":
                    result = api.start_extended_clip()
                    self._send_json(_save_status_code(result), result)
                    return
                if path == "/api/extended-clip/finish":
                    result = api.finish_extended_clip()
                    self._send_json(_save_status_code(result), result)
                    return
                if path == "/api/extended-clip/cancel":
                    result = api.cancel_extended_clip()
                    self._send_json(_save_status_code(result), result)
                    return
                if path == "/api/bridge/command-result":
                    result = api.record_bridge_command_result(payload)
                    self._send_json(200 if result.get("ok") else 404, result)
                    return
                if path == "/api/bridge/state":
                    result = api.record_bridge_state(payload)
                    self._send_json(200 if result.get("ok") else 422, result)
                    return
                if path == "/api/bridge/extended-clip-event":
                    result = api.record_extended_clip_event(payload)
                    self._send_json(200 if result.get("ok") else 422, result)
                    return
                self._send_json(404, {"error": "not_found"})
            except ValueError as error:
                self._send_json(422, {"error": str(error)})
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid_json"})

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")
            return payload

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                logger.debug("HTTP client disconnected before response was written: path=%s", self.path)

        def _send_file(self, status: int, path: Path, content_type: str) -> None:
            try:
                body = path.read_bytes()
            except OSError:
                self._send_json(404, {"error": "not_found"})
                return
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                logger.debug("HTTP client disconnected before response was written: path=%s", self.path)

    return SayClipHandler


def _save_status_code(result: dict[str, Any]) -> int:
    if result.get("accepted") is True:
        return 202
    if result.get("ok") and result.get("accepted") is False:
        return 200
    return 409


def create_server(api: BackendApi | None = None) -> ThreadingHTTPServer:
    config = api.config if api else load_config()
    backend_api = api or BackendApi(config)
    server = ThreadingHTTPServer(
        (config.backend_host, config.backend_port),
        make_handler(backend_api),
    )
    return server


def main() -> None:
    config = load_config()
    server = create_server(BackendApi(config))
    print(f"SayClip backend listening on http://{config.backend_host}:{config.backend_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SayClip backend...")
    finally:
        server.shutdown()
        server.server_close()
