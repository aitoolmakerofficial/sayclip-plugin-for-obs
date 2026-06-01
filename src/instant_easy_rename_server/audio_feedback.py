from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import logging

from .config import AppConfig


logger = logging.getLogger(__name__)


class ListeningSoundPlayer(Protocol):
    def listening_started(self) -> None:
        ...

    def listening_finished(self) -> None:
        ...


@dataclass(frozen=True)
class NativeBeepSoundPlayer:
    start_enabled: bool = True
    end_enabled: bool = True
    start_frequency: int = 880
    end_frequency: int = 660
    duration_ms: int = 90

    def listening_started(self) -> None:
        if self.start_enabled:
            self._beep(self.start_frequency)

    def listening_finished(self) -> None:
        if self.end_enabled:
            self._beep(self.end_frequency)

    def _beep(self, frequency: int) -> None:
        try:
            import winsound

            winsound.Beep(frequency, self.duration_ms)
        except Exception:
            logger.debug("Native listening beep could not be played", exc_info=True)


class NullSoundPlayer:
    def listening_started(self) -> None:
        return

    def listening_finished(self) -> None:
        return


def build_listening_sound_player(config: AppConfig) -> ListeningSoundPlayer:
    return NativeBeepSoundPlayer(
        start_enabled=bool(config.audio.get("beep_start", True)),
        end_enabled=bool(config.audio.get("beep_end", True)),
    )
