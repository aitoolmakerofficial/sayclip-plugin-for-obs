from __future__ import annotations

from pathlib import Path
from typing import Any
from html import escape
import logging
import os
import queue
import signal
import sys
import tempfile
import threading

from .api import BackendApi
from .audio import FakeAudioRecorder, list_input_devices
from .config import save_config
from .stt import FakeSpeechToTextEngine


logger = logging.getLogger(__name__)

STREAMDECK_PLUGIN_REPOSITORY_URL = "https://github.com/aitoolmakerofficial/obs-sayclip-plugin-streamdeck"


def _set_windows_app_user_model_id(app_id: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception as error:
        logger.debug("Could not set Windows AppUserModelID: %s", error)


def run_ui(api: BackendApi, server: Any) -> int:
    try:
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtGui import QColor, QIcon, QPalette
        from PySide6.QtWidgets import (
            QApplication,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFileDialog,
            QFrame,
            QFormLayout,
            QGridLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QProgressBar,
            QPushButton,
            QSizePolicy,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
    except ModuleNotFoundError as error:
        raise SystemExit("PySide6 is not installed. Run install.bat, then start.bat again.") from error

    class Card(QFrame):
        def __init__(self) -> None:
            super().__init__()
            self.setObjectName("Card")
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(12, 10, 12, 10)
            self.layout.setSpacing(6)

    class StatusChip(QLabel):
        def __init__(self, text: str = "", variant: str = "muted") -> None:
            super().__init__()
            self.setObjectName("StatusChip")
            self.setAlignment(Qt.AlignCenter)
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.set_status(text, variant)

        def set_status(self, text: str, variant: str) -> None:
            self.setText(text.upper())
            self.setProperty("variant", variant)
            self.style().unpolish(self)
            self.style().polish(self)

    class CurrentJobCard(Card):
        def __init__(self) -> None:
            super().__init__()
            header = QGridLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setColumnStretch(1, 1)
            label = QLabel("Session status")
            label.setObjectName("SectionTitle")
            self.status_chip = StatusChip("IDLE", "idle")
            header.addWidget(label, 0, 0)
            header.addWidget(self.status_chip, 0, 2, alignment=Qt.AlignRight | Qt.AlignTop)

            self.title = QLabel("Backend ready, idle")
            self.title.setObjectName("CurrentJobTitle")
            self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.subtitle = QLabel("Recent jobs appear here for this backend session only.")
            self.subtitle.setObjectName("Muted")
            self.subtitle.setTextInteractionFlags(Qt.TextSelectableByMouse)

            self.layout.addLayout(header)
            self.layout.addWidget(self.title)
            self.layout.addWidget(self.subtitle)

        def update_jobs(self, jobs: list[dict[str, Any]], errors: list[dict[str, Any]]) -> str:
            if errors:
                message = str(errors[0].get("message") or errors[0].get("error") or "OBS bridge reported an error.")
                self.status_chip.set_status("ERROR", "error")
                self.title.setText(_short_text(message, 96))
                self.subtitle.setText("OBS bridge error")
                self.setToolTip(message)
                return "error"
            if not jobs:
                self.status_chip.set_status("IDLE", "idle")
                self.title.setText("Backend ready, idle")
                self.subtitle.setText("Recent jobs appear here for this backend session only.")
                self.setToolTip("")
                return "idle"

            job = jobs[0]
            status = str(job.get("status") or "created")
            variant = _status_variant(status)
            self.status_chip.set_status(_status_chip_text(status), variant)
            self.title.setText(_current_job_title(job))
            self.subtitle.setText(_current_job_subtitle(job))
            self.setToolTip(_paths_tooltip(job))
            return status

    class MicrophoneCard(Card):
        def __init__(self) -> None:
            super().__init__()
            header = QGridLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setColumnStretch(1, 1)
            label = QLabel("Microphone")
            label.setObjectName("SectionTitle")
            self.device = QLabel()
            self.device.setObjectName("PrimaryText")
            self.status_chip = StatusChip("INACTIVE", "idle")
            header.addWidget(label, 0, 0)
            header.addWidget(self.status_chip, 0, 2, alignment=Qt.AlignRight | Qt.AlignTop)

            self.message = QLabel("")
            self.message.setObjectName("Muted")
            self.meter = QProgressBar()
            self.meter.setRange(0, 100)
            self.meter.setValue(0)
            self.meter.setTextVisible(False)

            self.layout.addLayout(header)
            self.layout.addWidget(self.device)
            self.layout.addWidget(self.meter)
            self.layout.addWidget(self.message)

        def update_state(self, device: str, level: float, listening: bool, ok: bool, message: str) -> None:
            self.device.setText(device)
            self.device.setToolTip(device)
            self.meter.setValue(round(level * 100))
            if not ok:
                self.status_chip.set_status("ERROR", "error")
                self.message.setText(_short_text(message, 140))
                self.setProperty("state", "error")
            elif listening:
                self.status_chip.set_status("LISTENING", "active")
                self.message.setText("Speak the title now.")
                self.setProperty("state", "active")
            else:
                self.status_chip.set_status("INACTIVE", "idle")
                self.message.setText("Ready for the next voice title.")
                self.setProperty("state", "idle")
            self.style().unpolish(self)
            self.style().polish(self)

    class SystemChecksCard(Card):
        def __init__(self) -> None:
            super().__init__()
            self.check_chips: dict[str, StatusChip] = {}

            title = QLabel("System details")
            title.setObjectName("SectionTitle")

            self.details = QWidget()
            details_layout = QGridLayout(self.details)
            details_layout.setContentsMargins(0, 0, 0, 0)
            details_layout.setHorizontalSpacing(16)
            details_layout.setVerticalSpacing(6)
            self.detail_labels: dict[str, QLabel] = {}
            rows = [
                ("Config loaded", "Config"),
                ("Model found", "Model"),
                ("Microphone available", "Mic"),
                ("Session jobs", "Jobs"),
                ("Logs writable", "Logs"),
            ]
            for index, (label_text, key) in enumerate(rows):
                name = QLabel(label_text)
                name.setObjectName("Muted")
                status = QLabel()
                status.setObjectName("DetailStatus")
                extra = QLabel()
                extra.setObjectName("Muted")
                extra.setTextInteractionFlags(Qt.TextSelectableByMouse)
                self.detail_labels[key] = status
                self.detail_labels[f"{key}Extra"] = extra
                details_layout.addWidget(name, index, 0)
                details_layout.addWidget(status, index, 1)
                details_layout.addWidget(extra, index, 2)
            details_layout.setColumnStretch(2, 1)

            self.actions = QWidget()
            actions_layout = QGridLayout(self.actions)
            actions_layout.setContentsMargins(0, 4, 0, 0)
            self.open_logs_button = QPushButton("Open logs")
            self.test_without_obs_button = QPushButton("Test without OBS")
            self.test_microphone_button = QPushButton("Test microphone")
            self.test_voice_button = QPushButton("Test voice")
            actions_layout.addWidget(self.open_logs_button, 0, 0)
            actions_layout.addWidget(self.test_without_obs_button, 0, 1)
            actions_layout.addWidget(self.test_microphone_button, 0, 2)
            actions_layout.addWidget(self.test_voice_button, 0, 3)
            actions_layout.setColumnStretch(4, 1)

            self.layout.addWidget(title)
            self.layout.addWidget(self.details)
            self.layout.addWidget(self.actions)

        def update_checks(self, checks: dict[str, bool], messages: dict[str, str], model_path: str, log_path: str) -> None:
            names = {
                "Config": "Config loaded",
                "Model": "Model found",
                "Mic": "Microphone available",
                "Jobs": "Session jobs",
                "Logs": "Logs writable",
            }
            for key, source in names.items():
                ok = bool(checks[source])
                self.detail_labels[key].setText("OK" if ok else "Missing")
                self.detail_labels[key].setProperty("state", "ok" if ok else "warn")
                self.detail_labels[key].style().unpolish(self.detail_labels[key])
                self.detail_labels[key].style().polish(self.detail_labels[key])
            self.detail_labels["ModelExtra"].setText(model_path or "Not configured")
            self.detail_labels["JobsExtra"].setText("In memory, latest 50")
            self.detail_labels["LogsExtra"].setText(log_path)
            self.detail_labels["Model"].setToolTip(messages.get("model", ""))
            self.detail_labels["Mic"].setToolTip(messages.get("microphone", ""))

    class AdditionalSetupCard(Card):
        def __init__(self) -> None:
            super().__init__()
            header = QGridLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setColumnStretch(0, 1)
            title = QLabel("Additional setup")
            title.setObjectName("SectionTitle")
            self.hide_button = QPushButton("Hide")
            header.addWidget(title, 0, 0)
            header.addWidget(self.hide_button, 0, 1, alignment=Qt.AlignRight)

            self.summary = QLabel(
                "The backend UI is open for setup. Normal OBS startup will run the backend headless; use Open Backend UI from the OBS script when you need this window again."
            )
            self.summary.setObjectName("Muted")
            self.summary.setWordWrap(True)

            dock_url = _dock_url(api.config)
            self.dock_url = QLabel(f'<a href="{escape(dock_url)}">{escape(dock_url)}</a>')
            self.dock_url.setObjectName("Link")
            self.dock_url.setTextInteractionFlags(Qt.TextBrowserInteraction)
            self.dock_url.setOpenExternalLinks(True)

            dock_actions = QWidget()
            dock_layout = QGridLayout(dock_actions)
            dock_layout.setContentsMargins(0, 0, 0, 0)
            self.copy_dock_url_button = QPushButton("Copy OBS dock URL")
            self.open_dock_button = QPushButton("Open dock in browser")
            dock_layout.addWidget(self.copy_dock_url_button, 0, 0)
            dock_layout.addWidget(self.open_dock_button, 0, 1)
            dock_layout.setColumnStretch(2, 1)

            dock_help = QLabel("OBS dock: Docks -> Custom Browser Docks -> Name: SayClip -> URL above.")
            dock_help.setObjectName("Muted")
            dock_help.setWordWrap(True)

            plugin_actions = QWidget()
            plugin_layout = QGridLayout(plugin_actions)
            plugin_layout.setContentsMargins(0, 0, 0, 0)
            self.open_streamdeck_repository_button = QPushButton("Open Stream Deck plugin repository")
            plugin_layout.addWidget(self.open_streamdeck_repository_button, 0, 0)
            plugin_layout.setColumnStretch(1, 1)

            self.layout.addLayout(header)
            self.layout.addWidget(self.summary)
            self.layout.addWidget(self.dock_url)
            self.layout.addWidget(dock_actions)
            self.layout.addWidget(dock_help)
            self.layout.addWidget(plugin_actions)

    class JobsTable(QTableWidget):
        def __init__(self) -> None:
            super().__init__(0, 6)
            self.setHorizontalHeaderLabels(["Type", "Status", "Game", "Title", "Output", "Error"])
            header = self.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Stretch)
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            self.verticalHeader().setVisible(False)
            self.setSelectionBehavior(QTableWidget.SelectRows)
            self.setEditTriggers(QTableWidget.NoEditTriggers)
            self.setAlternatingRowColors(True)

        def populate(self, rows: list[list[str]]) -> None:
            display_rows = rows or [_empty_jobs_row()]
            self.setRowCount(len(display_rows))
            for row_index, row in enumerate(display_rows):
                values = _presentation_row(row)
                tooltip = _row_tooltip(row)
                for column_index, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(tooltip)
                    item.setData(Qt.UserRole, {"original": row[3], "final": row[5]})
                    if column_index == 1:
                        item.setData(Qt.UserRole + 1, _status_variant(row[1]))
                        item.setForeground(QColor(_status_color(row[1])))
                        item.setTextAlignment(Qt.AlignCenter)
                    self.setItem(row_index, column_index, item)

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle(api.config.app_name)
            self.resize(980, 620)

            root = QWidget()
            self.background_results: queue.Queue[tuple[str, str, dict[str, Any]]] = queue.Queue()
            self.latest_checks = {
                "Microphone available": True,
            }
            self.latest_messages = {
                "microphone": "",
            }
            self.current_job_status = "idle"
            layout = QVBoxLayout(root)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            header = QGridLayout()
            header.setContentsMargins(0, 0, 0, 4)
            header.setColumnStretch(0, 1)
            title = QLabel(f"{api.config.app_name} Version 1")
            title.setObjectName("Title")
            self.backend_status = StatusChip("Backend OK", "ok")
            self.bridge_status = StatusChip("Bridge waiting", "idle")
            header.addWidget(title, 0, 0)
            header.addWidget(self.backend_status, 0, 1, alignment=Qt.AlignRight)
            header.addWidget(self.bridge_status, 0, 2, alignment=Qt.AlignRight)
            layout.addLayout(header)

            self.current_job_card = CurrentJobCard()
            layout.addWidget(self.current_job_card)

            self.microphone_card = MicrophoneCard()
            layout.addWidget(self.microphone_card)

            self.system_card = SystemChecksCard()
            self.system_card.open_logs_button.clicked.connect(self.open_logs)
            self.system_card.test_without_obs_button.clicked.connect(self.create_test_job)
            self.system_card.test_microphone_button.clicked.connect(self.test_microphone)
            self.voice_test_button = self.system_card.test_voice_button
            self.voice_test_button.clicked.connect(self.create_voice_test_job)
            self.system_card.setVisible(False)
            layout.addWidget(self.system_card)

            self.additional_setup_card = AdditionalSetupCard()
            self.additional_setup_card.copy_dock_url_button.clicked.connect(self.copy_dock_url)
            self.additional_setup_card.open_dock_button.clicked.connect(self.open_dock)
            self.additional_setup_card.open_streamdeck_repository_button.clicked.connect(self.open_streamdeck_repository)
            self.additional_setup_card.hide_button.clicked.connect(self.hide_additional_setup)
            show_additional_setup = bool(api.config.data.get("ui", {}).get("show_additional_setup", True))
            self.additional_setup_card.setVisible(show_additional_setup)
            if show_additional_setup:
                api.config.data.setdefault("ui", {})["show_additional_setup"] = False
                save_config(api.config)
            layout.addWidget(self.additional_setup_card)

            toolbar = QGridLayout()
            settings_button = QPushButton("Settings")
            settings_button.clicked.connect(self.open_settings)
            self.details_button = QPushButton("Details")
            self.details_button.clicked.connect(self.toggle_system_details)
            self.interfaces_button = QPushButton("Interfaces")
            self.interfaces_button.clicked.connect(self.show_additional_setup)
            toolbar.addWidget(settings_button, 0, 0)
            toolbar.addWidget(self.details_button, 0, 1)
            toolbar.addWidget(self.interfaces_button, 0, 2)
            toolbar.setColumnStretch(3, 1)
            layout.addLayout(toolbar)

            jobs_label = QLabel("Recent jobs")
            jobs_label.setObjectName("SectionTitle")
            layout.addWidget(jobs_label)
            self.table = JobsTable()
            self.table.cellDoubleClicked.connect(self.open_row_folder)
            layout.addWidget(self.table, 1)

            self.setCentralWidget(root)
            self.refresh()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.timeout.connect(self.poll_background_results)
            self.timer.start(200)

        def refresh(self) -> None:
            if api.shutdown_requested.is_set():
                QApplication.instance().quit()
                return
            health = api.health()
            backend_ok = health.get("status") == "ok"
            self.backend_status.set_status("Backend OK" if backend_ok else "Backend Error", "ok" if backend_ok else "error")
            self.backend_status.setToolTip(
                f"http://{api.config.backend_host}:{api.config.backend_port}"
            )
            self._refresh_checks()
            self._refresh_jobs()
            self._refresh_microphone()

        def _refresh_checks(self) -> None:
            system_checks = api.system_checks()
            checks = {
                "Config loaded": bool(system_checks["config"]["ok"]),
                "Model found": bool(system_checks["model"]["ok"]),
                "Microphone available": bool(system_checks["microphone"]["ok"]),
                "Session jobs": True,
                "Logs writable": _is_writable(api.config.resolve_path(str(api.config.data["logging"]["log_path"]))),
            }
            messages = {
                "model": str(system_checks["model"]["message"]),
                "microphone": str(system_checks["microphone"]["message"]),
            }
            self.latest_checks = checks
            self.latest_messages = messages
            self.system_card.update_checks(
                checks,
                messages,
                str(api.config.stt.get("model_path") or "Not configured"),
                str(api.config.resolve_path(str(api.config.data["logging"]["log_path"]))),
            )

        def _refresh_jobs(self) -> None:
            jobs = api.list_jobs()["jobs"]
            errors = api.list_errors()["errors"]
            rows = [_job_row(job) for job in jobs] + [_error_row(error) for error in errors]
            self.current_job_status = self.current_job_card.update_jobs(jobs, errors)
            self.table.populate(rows)

        def _refresh_microphone(self) -> None:
            self.microphone_card.update_state(
                str(api.config.audio.get("device", "default")),
                api.mic_level,
                self.current_job_status == "listening",
                bool(self.latest_checks.get("Microphone available", True)),
                self.latest_messages.get("microphone", ""),
            )

        def toggle_system_details(self) -> None:
            visible = not self.system_card.isVisible()
            self.system_card.setVisible(visible)
            self.details_button.setText("Hide details" if visible else "Details")

        def show_additional_setup(self) -> None:
            self.additional_setup_card.setVisible(True)

        def hide_additional_setup(self) -> None:
            self.additional_setup_card.setVisible(False)
            api.config.data.setdefault("ui", {})["show_additional_setup"] = False
            save_config(api.config)

        def copy_dock_url(self) -> None:
            QApplication.clipboard().setText(_dock_url(api.config))
            QMessageBox.information(self, "OBS dock URL", "OBS dock URL copied.")

        def open_dock(self) -> None:
            os.startfile(_dock_url(api.config))

        def open_streamdeck_repository(self) -> None:
            os.startfile(STREAMDECK_PLUGIN_REPOSITORY_URL)

        def open_row_folder(self, row: int, column: int) -> None:
            del column
            item = self.table.item(row, 0)
            data = item.data(Qt.UserRole) if item else {}
            if not isinstance(data, dict):
                data = {}
            if not data.get("final") and not data.get("original"):
                return
            folder = _folder_for_paths(str(data.get("final") or ""), str(data.get("original") or ""))
            self._open_folder(folder)

        def open_selected_folder(self) -> None:
            row = self.table.currentRow()
            if row < 0:
                folder = api.config.root
            else:
                item = self.table.item(row, 0)
                data = item.data(Qt.UserRole) if item else {}
                if not isinstance(data, dict):
                    data = {}
                folder = _folder_for_paths(str(data.get("final") or ""), str(data.get("original") or ""))
            self._open_folder(folder)

        def _open_folder(self, folder: Path) -> None:
            if not folder.exists():
                QMessageBox.warning(self, "Open folder", "Folder does not exist yet.")
                return
            os.startfile(folder)

        def create_test_job(self) -> None:
            logger.info("UI Test without OBS clicked")
            original = api.config.root / "temp" / "manual-ui-test" / "Forza Horizon 6" / "Replays" / "2026-05-27 22-10-44.mkv"
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(b"fake video bytes")

            previous_recorder = api.audio_recorder
            previous_engine = api.stt_engine
            api.audio_recorder = FakeAudioRecorder()
            api.stt_engine = FakeSpeechToTextEngine(str(api.config.stt.get("fake_transcript", "clean overtake")))
            try:
                api.create_job(
                    {
                        "type": "moment",
                        "original_path": str(original),
                        "source_title": "Forza Horizon 6",
                        "created_by": "ui_test_without_obs",
                    }
                )
            finally:
                api.audio_recorder = previous_recorder
                api.stt_engine = previous_engine

            self.refresh()
            QMessageBox.information(self, "Test without OBS", "A sample video was renamed and added to the jobs table.")

        def test_microphone(self) -> None:
            logger.info("UI Test microphone clicked")
            self.background_results.put(("notice", "info", {"title": "Test microphone", "message": "Listening started."}))
            thread = threading.Thread(target=self._run_microphone_test, daemon=True)
            thread.start()

        def _run_microphone_test(self) -> None:
            try:
                audio = api.audio_recorder.record(on_level=api._set_mic_level)
                output = api.config.root / "temp" / "microphone-test.wav"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(audio.data or b"")
                self.background_results.put(
                    (
                        "microphone",
                        "done",
                        {
                            "path": str(output),
                            "peak": round(api.mic_level * 100),
                            "bytes": len(audio.data or b""),
                        },
                    )
                )
            except Exception as error:
                logger.exception("UI microphone test failed")
                self.background_results.put(("microphone", "error", {"error": str(error)}))

        def create_voice_test_job(self) -> None:
            logger.info("UI Test voice clicked")
            self.voice_test_button.setEnabled(False)
            self.voice_test_button.setText("Listening...")
            thread = threading.Thread(target=self._run_voice_test_job, daemon=True)
            thread.start()

        def _run_voice_test_job(self) -> None:
            original = api.config.root / "temp" / "manual-voice-test" / "Forza Horizon 6" / "Replays" / "2026-05-27 22-10-44.mkv"
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(b"fake video bytes")

            try:
                created = api.create_job(
                    {
                        "type": "moment",
                        "original_path": str(original),
                        "source_title": "Forza Horizon 6",
                        "created_by": "ui_voice_test_without_obs",
                    }
                )
                job = api.list_jobs()["jobs"][0]
                self.background_results.put(("voice", created["status"], job))
            except Exception as error:
                self.background_results.put(("voice", "error", {"error": str(error)}))

        def poll_background_results(self) -> None:
            while True:
                try:
                    kind, status, payload = self.background_results.get_nowait()
                except queue.Empty:
                    return
                if kind == "voice":
                    self._finish_voice_test(status, payload)
                elif kind == "microphone":
                    self._finish_microphone_test(status, payload)
                elif kind == "notice":
                    QMessageBox.information(self, str(payload["title"]), str(payload["message"]))

        def _finish_microphone_test(self, status: str, payload: dict[str, Any]) -> None:
            self.refresh()
            if status == "done":
                QMessageBox.information(
                    self,
                    "Test microphone",
                    "Microphone test completed.\n\n"
                    f"Peak level: {payload.get('peak')}%\n"
                    f"Bytes: {payload.get('bytes')}\n"
                    f"Saved audio: {payload.get('path')}",
                )
                return
            QMessageBox.warning(
                self,
                "Test microphone",
                f"Microphone test failed.\n\n{payload.get('error') or 'Unknown error'}",
            )

        def _finish_voice_test(self, status: str, job: dict[str, Any]) -> None:
            self.voice_test_button.setEnabled(True)
            self.voice_test_button.setText("Test voice")
            self.refresh()
            if status == "done":
                QMessageBox.information(
                    self,
                    "Test voice",
                    f"Voice test completed.\n\nTranscript: {job.get('transcript')}\n\nNew file: {job.get('final_path')}",
                )
                return
            QMessageBox.warning(
                self,
                "Test voice",
                f"Voice test failed.\n\n{job.get('error') or 'Unknown error'}",
            )

        def open_settings(self) -> None:
            logger.info("UI Settings opened")
            dialog = SettingsDialog(self)
            if dialog.exec() != QDialog.Accepted:
                return
            dialog.apply()
            api.apply_runtime_config()
            self.refresh()
            QMessageBox.information(self, "Settings", "Settings saved.")

        def open_logs(self) -> None:
            log_path = api.config.resolve_path(str(api.config.data["logging"]["log_path"]))
            log_path.parent.mkdir(parents=True, exist_ok=True)
            if not log_path.exists():
                log_path.write_text("", encoding="utf-8")
            os.startfile(log_path)

    class SettingsDialog(QDialog):
        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("Settings")
            self.setMinimumWidth(620)

            layout = QVBoxLayout(self)
            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignRight)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

            self.engine = QComboBox()
            self.engine.addItems(["fake", "faster_whisper"])
            self.engine.setCurrentText(str(api.config.stt.get("engine", "fake")))
            form.addRow("STT engine", self.engine)

            model_row = QWidget()
            model_layout = QGridLayout(model_row)
            model_layout.setContentsMargins(0, 0, 0, 0)
            model_layout.setColumnStretch(0, 1)
            self.model_path = QLineEdit(str(api.config.stt.get("model_path", "")))
            browse_model = QPushButton("Folder")
            browse_model.clicked.connect(self.choose_model_path)
            model_layout.addWidget(self.model_path, 0, 0)
            model_layout.addWidget(browse_model, 0, 1)
            form.addRow("Model path", model_row)

            self.language = QLineEdit(str(api.config.stt.get("language", "ru")))
            form.addRow("Language", self.language)

            self.filename_format = QComboBox()
            filename_format_options = [
                ("Spoken title only - clean-overtake", "{title}"),
                ("Time + spoken title - 2026-05-27_22-10-44__clean-overtake", "{datetime}__{title}"),
                (
                    "Source + time + spoken title - forza-horizon-6__2026-05-27_22-10-44__clean-overtake",
                    "{source}__{datetime}__{title}",
                ),
                (
                    "Source + clip type + time + spoken title - forza-horizon-6__mom__2026-05-27_22-10-44__clean-overtake",
                    "{source}__{job_type}__{datetime}__{title}",
                ),
            ]
            current_filename_format = str(api.config.naming.get("format", "{source}__{datetime}__{title}"))
            for label, value in filename_format_options:
                self.filename_format.addItem(label, value)
            known_format_values = [value for _, value in filename_format_options]
            if current_filename_format not in known_format_values:
                self.filename_format.addItem(f"Custom - {current_filename_format}", current_filename_format)
            self.filename_format.setCurrentIndex(
                max(0, self.filename_format.findData(current_filename_format))
            )
            form.addRow("Rename format", self.filename_format)

            self.datetime_format = QLineEdit(str(api.config.naming.get("datetime_format", "%Y-%m-%d_%H-%M-%S")))
            form.addRow("Time format", self.datetime_format)

            audio_row = QWidget()
            audio_layout = QGridLayout(audio_row)
            audio_layout.setContentsMargins(0, 0, 0, 0)
            audio_layout.setColumnStretch(0, 1)
            self.audio_device = QComboBox()
            self.audio_device.setEditable(True)
            self.refresh_audio_devices()
            refresh_audio = QPushButton("Refresh")
            refresh_audio.clicked.connect(self.refresh_audio_devices)
            audio_layout.addWidget(self.audio_device, 0, 0)
            audio_layout.addWidget(refresh_audio, 0, 1)
            form.addRow("Microphone", audio_row)

            layout.addLayout(form)

            buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

        def choose_model_path(self) -> None:
            current = api.config.resolve_path(self.model_path.text()) if self.model_path.text().strip() else api.config.root
            folder = QFileDialog.getExistingDirectory(self, "Model path", str(current))
            if folder:
                self.model_path.setText(_display_path(api.config.root, Path(folder)))

        def refresh_audio_devices(self) -> None:
            selected = self.audio_device.currentText().strip() if hasattr(self, "audio_device") else ""
            if not selected:
                selected = str(api.config.audio.get("device", "default"))
            self.audio_device.clear()
            self.audio_device.addItems(list_input_devices())
            self.audio_device.setCurrentText(selected)

        def apply(self) -> None:
            api.config.data["stt"]["engine"] = self.engine.currentText().strip()
            api.config.data["stt"]["model_path"] = self.model_path.text().strip()
            api.config.data["stt"]["language"] = self.language.text().strip()
            api.config.data["naming"]["format"] = str(self.filename_format.currentData() or "{title}")
            api.config.data["naming"]["datetime_format"] = self.datetime_format.text().strip() or "%Y-%m-%d_%H-%M-%S"
            api.config.data["audio"]["device"] = self.audio_device.currentText().strip() or "default"
            save_config(api.config)

    def app_icon() -> QIcon:
        path = Path(__file__).resolve().parent / "img" / "sayclip-icon.png"
        if not path.exists():
            path = api.config.root / "img" / "sayclip-icon.png"
        if not path.exists():
            return QIcon()
        return QIcon(str(path))

    _set_windows_app_user_model_id("aitoolmaker.sayclip")
    app = QApplication.instance() or QApplication(sys.argv)
    previous_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda signum, frame: app.quit())
    app.setStyle("Fusion")
    app.setPalette(_dark_palette(QPalette, QColor))
    app.setStyleSheet(_stylesheet())
    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    signal_timer = QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(200)
    auto_exit_ms = os.environ.get("OBS_EASY_RENAME_UI_TEST_EXIT_MS")
    if auto_exit_ms:
        QTimer.singleShot(int(auto_exit_ms), app.quit)
    try:
        return app.exec()
    finally:
        signal_timer.stop()
        signal.signal(signal.SIGINT, previous_sigint)


def _job_row(job: dict[str, Any]) -> list[str]:
    original = str(job.get("original_path") or "")
    final = str(job.get("final_path") or "")
    folder = str(Path(final or original).parent) if (final or original) else ""
    return [
        str(job.get("type") or ""),
        str(job.get("status") or ""),
        str(job.get("game") or ""),
        original,
        str(job.get("transcript") or ""),
        final,
        folder,
        str(job.get("error") or ""),
    ]


def _error_row(error: dict[str, Any]) -> list[str]:
    message = str(error.get("error") or error.get("message") or error)
    path = str(error.get("original_path") or error.get("path") or "")
    folder = str(Path(path).parent) if path else ""
    return ["error", "error", str(error.get("game") or ""), path, "", "", folder, message]


def _empty_jobs_row() -> list[str]:
    return ["-", "idle", "-", "", "No jobs yet", "", "", "Current session is empty"]


def _presentation_row(row: list[str]) -> list[str]:
    job_type, status, game, original, transcript, final, folder, error = row
    del folder
    return [
        _type_label(job_type),
        _status_chip_text(status),
        game,
        transcript,
        Path(final or original).name if (final or original) else "",
        _short_text(error, 80),
    ]


def _row_tooltip(row: list[str]) -> str:
    labels = ["Type", "Status", "Game", "Original", "Title", "Output", "Folder", "Error"]
    return "\n".join(f"{label}: {value}" for label, value in zip(labels, row, strict=True) if value)


def _current_job_title(job: dict[str, Any]) -> str:
    status = str(job.get("status") or "")
    if status == "listening":
        return "Listening for voice title..."
    if status == "transcribing":
        return "Transcribing voice title..."
    if status == "renaming":
        return "Renaming output file..."
    if status == "error":
        return _short_text(str(job.get("error") or "The last rename flow failed."), 96)
    final = str(job.get("final_path") or "")
    if status == "done" and final:
        return Path(final).name
    return "Waiting for job..."


def _current_job_subtitle(job: dict[str, Any]) -> str:
    parts = [
        _job_type_name(str(job.get("type") or "")),
        str(job.get("game") or ""),
    ]
    transcript = str(job.get("transcript") or "").strip()
    status = str(job.get("status") or "").strip()
    if transcript:
        parts.append(transcript)
    elif status and status not in {"done", "error"}:
        parts.append(status.replace("_", " "))
    return " · ".join(part for part in parts if part)


def _paths_tooltip(job: dict[str, Any]) -> str:
    original = str(job.get("original_path") or "")
    final = str(job.get("final_path") or "")
    tooltip = []
    if original:
        tooltip.append(f"Original: {original}")
    if final:
        tooltip.append(f"Output: {final}")
    return "\n".join(tooltip)


def _type_label(job_type: str) -> str:
    if job_type == "recording":
        return "rec"
    if job_type == "moment":
        return "mom"
    return job_type


def _job_type_name(job_type: str) -> str:
    if job_type == "recording":
        return "Recording"
    if job_type == "moment":
        return "Moment"
    return job_type.title()


def _status_chip_text(status: str) -> str:
    values = {
        "created": "queued",
        "waiting_for_voice": "waiting",
        "listening": "listening",
        "transcribing": "transcribing",
        "renaming": "renaming",
        "done": "done",
        "error": "error",
    }
    return values.get(status, status.replace("_", " "))


def _status_variant(status: str) -> str:
    if status == "done":
        return "ok"
    if status == "listening":
        return "active"
    if status in {"created", "waiting_for_voice", "transcribing", "renaming"}:
        return "warning"
    if status == "error":
        return "error"
    return "muted"


def _status_color(status: str) -> str:
    return {
        "done": "#7bd88f",
        "listening": "#7ef0ad",
        "created": "#f2c94c",
        "waiting_for_voice": "#f2c94c",
        "transcribing": "#68b8ff",
        "renaming": "#68b8ff",
        "error": "#ff7a7a",
    }.get(status, "#aeb8c5")


def _short_text(value: str, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _folder_for_paths(final_path: str, original_path: str) -> Path:
    selected = final_path.strip() or original_path.strip()
    if not selected:
        return Path.cwd()
    return Path(selected).parent


def _is_writable(path: Path) -> bool:
    directory = path if path.suffix == "" else path.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, delete=True):
            return True
    except OSError:
        return False


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _dock_url(config: Any) -> str:
    return f"http://{config.backend_host}:{config.backend_port}/dock"


def _dark_palette(qpalette: Any, qcolor: Any) -> Any:
    palette = qpalette()
    palette.setColor(qpalette.Window, qcolor(24, 26, 30))
    palette.setColor(qpalette.WindowText, qcolor(232, 236, 241))
    palette.setColor(qpalette.Base, qcolor(18, 20, 24))
    palette.setColor(qpalette.AlternateBase, qcolor(31, 34, 39))
    palette.setColor(qpalette.ToolTipBase, qcolor(232, 236, 241))
    palette.setColor(qpalette.ToolTipText, qcolor(18, 20, 24))
    palette.setColor(qpalette.Text, qcolor(232, 236, 241))
    palette.setColor(qpalette.Button, qcolor(42, 46, 53))
    palette.setColor(qpalette.ButtonText, qcolor(232, 236, 241))
    palette.setColor(qpalette.Highlight, qcolor(64, 132, 214))
    palette.setColor(qpalette.HighlightedText, qcolor(255, 255, 255))
    return palette


def _stylesheet() -> str:
    return """
    QWidget {
        background: #15171b;
        color: #e8ecf1;
        font-size: 13px;
    }
    QLabel {
        background: transparent;
    }
    QLabel#Title {
        font-size: 22px;
        font-weight: 700;
    }
    QLabel#SectionTitle {
        color: #f6f8fb;
        font-weight: 700;
    }
    QLabel#PrimaryText {
        color: #f6f8fb;
        font-size: 14px;
        font-weight: 600;
    }
    QLabel#CurrentJobTitle {
        color: #ffffff;
        font-size: 18px;
        font-weight: 700;
    }
    QLabel#Muted {
        color: #aeb8c5;
    }
    QFrame#Card {
        background: #20242a;
        border: 1px solid #333a44;
        border-radius: 8px;
    }
    QFrame#Card[state="active"] {
        background: #183628;
        border-color: #3fb878;
    }
    QFrame#Card[state="error"] {
        border-color: #8b3b3b;
    }
    QLabel#StatusChip {
        border-radius: 10px;
        padding: 3px 9px;
        min-height: 16px;
        font-size: 11px;
        font-weight: 700;
    }
    QLabel#StatusChip[variant="ok"] {
        color: #08140d;
        background: #7bd88f;
    }
    QLabel#StatusChip[variant="idle"] {
        color: #d5dbe4;
        background: #343a43;
    }
    QLabel#StatusChip[variant="active"] {
        color: #06150c;
        background: #41b883;
    }
    QLabel#StatusChip[variant="warning"] {
        color: #1c1400;
        background: #f2c94c;
    }
    QLabel#StatusChip[variant="error"] {
        color: #210606;
        background: #ff7a7a;
    }
    QLabel#StatusChip[variant="muted"] {
        color: #c4ccd6;
        background: #2b3038;
    }
    QLabel#DetailStatus[state="ok"] {
        color: #7bd88f;
        font-weight: 700;
    }
    QLabel#DetailStatus[state="warn"] {
        color: #ffcf5a;
        font-weight: 700;
    }
    QPushButton {
        background: #2b3038;
        border: 1px solid #424a55;
        border-radius: 6px;
        padding: 6px 12px;
    }
    QPushButton:hover {
        background: #363d47;
    }
    QTableWidget {
        background: #121418;
        alternate-background-color: #1a1d22;
        border: 1px solid #343a43;
        gridline-color: #2d333b;
        selection-background-color: #315f9e;
        selection-color: #ffffff;
    }
    QHeaderView::section {
        background: #20242a;
        border: 0;
        border-bottom: 1px solid #343a43;
        padding: 5px 7px;
        font-weight: 700;
    }
    QProgressBar {
        background: #111317;
        border: 1px solid #343a43;
        border-radius: 7px;
        min-height: 16px;
        max-height: 16px;
    }
    QProgressBar::chunk {
        background: #586170;
        border-radius: 7px;
    }
    QFrame#Card[state="active"] QProgressBar::chunk {
        background: #41b883;
    }
    """
