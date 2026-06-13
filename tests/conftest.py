from instant_easy_rename_server.audio_feedback import NullSoundPlayer
import pytest


def _null_sound_player(config):
    del config
    return NullSoundPlayer()


@pytest.fixture(autouse=True)
def no_native_listening_beeps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("instant_easy_rename_server.api.build_listening_sound_player", _null_sound_player)
