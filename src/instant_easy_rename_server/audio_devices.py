from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import logging
import re
import sys


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioInputDevice:
    name: str
    source: str
    is_default: bool = False


def list_audio_input_devices() -> list[AudioInputDevice]:
    devices = [
        AudioInputDevice(name="default", source="app", is_default=True),
        AudioInputDevice(name="fake", source="app"),
    ]
    devices.extend(_sounddevice_inputs())
    devices.extend(_winmm_inputs())
    unique = _dedupe_devices(devices)
    logger.debug("Discovered audio input devices: %s", [f"{device.name} ({device.source})" for device in unique])
    return unique


def list_audio_input_device_names() -> list[str]:
    return [device.name for device in list_audio_input_devices()]


def list_user_audio_input_device_names() -> list[str]:
    devices = [device for device in list_audio_input_devices() if device.name != "fake"]
    return [device.name for device in _dedupe_user_devices(devices)]


def selected_audio_device_exists(name: str) -> bool:
    selected = name.strip()
    if selected == "fake":
        return True
    devices = list_audio_input_devices()
    if selected == "default":
        return any(device.source != "app" for device in devices)
    return selected in [device.name for device in devices]


def _sounddevice_inputs() -> list[AudioInputDevice]:
    try:
        import sounddevice as sd  # type: ignore[import-not-found]
    except Exception:
        logger.debug("sounddevice device discovery failed during import", exc_info=True)
        return []

    devices: list[AudioInputDevice] = []
    try:
        for device in sd.query_devices():
            max_inputs = int(device.get("max_input_channels", 0))
            name = str(device.get("name", "")).strip()
            if max_inputs > 0 and name:
                devices.append(AudioInputDevice(name=name, source="sounddevice"))
    except Exception:
        logger.debug("sounddevice device discovery failed", exc_info=True)
        return []
    return devices


def _winmm_inputs() -> list[AudioInputDevice]:
    if sys.platform != "win32":
        return []

    class WAVEINCAPSW(ctypes.Structure):
        _fields_ = [
            ("wMid", wintypes.WORD),
            ("wPid", wintypes.WORD),
            ("vDriverVersion", wintypes.UINT),
            ("szPname", wintypes.WCHAR * 32),
            ("dwFormats", wintypes.DWORD),
            ("wChannels", wintypes.WORD),
            ("wReserved1", wintypes.WORD),
            ("dwSupport", wintypes.DWORD),
        ]

    try:
        winmm = ctypes.WinDLL("winmm")
        count = int(winmm.waveInGetNumDevs())
    except Exception:
        logger.debug("WinMM device discovery failed", exc_info=True)
        return []

    devices: list[AudioInputDevice] = []
    for index in range(count):
        caps = WAVEINCAPSW()
        result = winmm.waveInGetDevCapsW(index, ctypes.byref(caps), ctypes.sizeof(caps))
        if result == 0:
            name = str(caps.szPname).strip()
            if name:
                devices.append(AudioInputDevice(name=name, source="winmm"))
    return devices


def _dedupe_devices(devices: list[AudioInputDevice]) -> list[AudioInputDevice]:
    seen: set[str] = set()
    unique: list[AudioInputDevice] = []
    for device in devices:
        key = device.name.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(device)
    return unique


def _dedupe_user_devices(devices: list[AudioInputDevice]) -> list[AudioInputDevice]:
    unique = []
    seen = set()
    for device in devices:
        if _is_virtual_or_mapper_device(device.name):
            continue
        key = _canonical_device_name(device.name)
        if key in seen:
            continue
        seen.add(key)
        unique.append(device)
    if not any(device.name == "default" for device in unique):
        unique.insert(0, AudioInputDevice(name="default", source="app", is_default=True))
    return unique


def _canonical_device_name(name: str) -> str:
    value = name.casefold()
    value = re.sub(r"\s*\(\d+-\s*", " (", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _is_virtual_or_mapper_device(name: str) -> bool:
    value = name.casefold()
    ignored_fragments = [
        "microsoft sound mapper",
        "primary sound capture driver",
        "stereo mix",
        "what u hear",
        "wave out mix",
        "personal mix",
        "chat mix",
        "aux mix",
        "stream mix",
        "recording mix",
    ]
    return any(fragment in value for fragment in ignored_fragments)
