from pathlib import Path


DOCK_ROOT = Path(__file__).resolve().parents[1] / "src" / "instant_easy_rename_server" / "dock_static"


def test_discard_button_has_stable_public_dom_contract() -> None:
    html = (DOCK_ROOT / "dock.html").read_text(encoding="utf-8")

    assert 'id="discardRecording"' in html
    assert 'id="discardRecordingLabel"' in html
    assert 'data-icon="discard"' in html


def test_discard_button_uses_canonical_backend_confirmation() -> None:
    javascript = (DOCK_ROOT / "dock.js").read_text(encoding="utf-8")

    assert 'actionAvailability("discard_recording")' in javascript
    assert 'discardConfirming ? "CONFIRM" : "DISCARD"' in javascript
    assert 'sendAction("/api/discard/recording", elements.discardRecording)' in javascript
    assert "discardConfirmationTimer" not in javascript


def test_dock_uses_two_by_two_action_layout() -> None:
    css = (DOCK_ROOT / "dock.css").read_text(encoding="utf-8")

    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert ".action-button--discard.is-confirming" in css
