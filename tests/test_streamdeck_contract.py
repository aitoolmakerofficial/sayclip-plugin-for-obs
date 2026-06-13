from instant_easy_rename_server.streamdeck import (
    BACKEND_BASE_URL,
    SAVE_MOMENT_PATH,
    SAVE_RECORDING_PATH,
    STATUS_PATH,
    StreamDeckTitle,
    title_for_save_response,
    title_for_status_snapshot,
)


def test_streamdeck_contract_uses_shared_backend_endpoints() -> None:
    assert BACKEND_BASE_URL == "http://127.0.0.1:17891"
    assert STATUS_PATH == "/api/status"
    assert SAVE_MOMENT_PATH == "/api/save/moment"
    assert SAVE_RECORDING_PATH == "/api/save/recording"


def test_streamdeck_status_titles_map_from_canonical_backend_phases() -> None:
    assert title_for_status_snapshot({"phase": "idle", "busy": False}) == StreamDeckTitle.IDLE
    assert title_for_status_snapshot({"phase": "command_sent", "busy": True}) == StreamDeckTitle.BUSY
    assert title_for_status_snapshot({"phase": "waiting_for_obs", "busy": True}) == StreamDeckTitle.BUSY
    assert title_for_status_snapshot({"phase": "waiting_for_file", "busy": True}) == StreamDeckTitle.BUSY
    assert title_for_status_snapshot({"phase": "listening", "busy": True}) == StreamDeckTitle.SPEAK
    assert title_for_status_snapshot({"phase": "transcribing", "busy": True}) == StreamDeckTitle.STT
    assert title_for_status_snapshot({"phase": "renaming", "busy": True}) == StreamDeckTitle.BUSY
    assert title_for_status_snapshot({"phase": "done", "busy": False}) == StreamDeckTitle.DONE
    assert title_for_status_snapshot({"phase": "error", "busy": False}) == StreamDeckTitle.ERROR


def test_streamdeck_status_title_handles_backend_offline() -> None:
    assert title_for_status_snapshot(None, reachable=False) == StreamDeckTitle.OFFLINE


def test_streamdeck_save_response_titles_match_action_contract() -> None:
    assert title_for_save_response({"ok": True, "accepted": True, "command_id": "cmd"}) == StreamDeckTitle.SENT
    assert title_for_save_response({"ok": True, "accepted": False, "reason": "busy"}) == StreamDeckTitle.BUSY
    assert title_for_save_response({"ok": False, "error": "Bridge is not connected"}) == StreamDeckTitle.OFFLINE
    assert title_for_save_response(None, reachable=False) == StreamDeckTitle.OFFLINE
