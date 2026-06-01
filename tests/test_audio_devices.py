from instant_easy_rename_server.audio_devices import list_audio_input_device_names, selected_audio_device_exists


def test_audio_device_list_always_has_default_and_fake() -> None:
    devices = list_audio_input_device_names()

    assert devices[0] == "default"
    assert devices[1] == "fake"


def test_builtin_audio_devices_are_selectable() -> None:
    assert selected_audio_device_exists("fake")
