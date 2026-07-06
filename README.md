# SayClip

![SayClip GitHub cover](public/sayclip-github-cover.png)

SayClip is a local OBS companion tool for voice-titled recording and
replay-buffer renames.

For the detailed creator-focused setup and troubleshooting guide, see
[`public/user-guide.md`](public/user-guide.md).

SayClip runs on your machine. The OBS bridge, backend UI, browser dock, audio
recording, speech recognition, and file rename flow are designed for local use.
The backend listens on localhost only by default:

http://127.0.0.1:17891

## Video Guide

Installation and usage videos are published through the official AI Toolmaker
YouTube channel:

https://www.youtube.com/@WorkingAiTools

Use the official repository and official video links when installing SayClip.
Do not download modified installers or model links from random mirrors unless
you have reviewed and trust them.

## Quick Install Path

1. Download or clone the official SayClip repository.
2. Open OBS.
3. Go to Tools -> Scripts.
4. Add `SayClip_Starter.py`.
5. SayClip Onboarding opens from the OBS script when setup is missing.
6. Follow SayClip Onboarding step by step.
7. Add the OBS dock at `http://127.0.0.1:17891/dock` if you want the browser
   panel inside OBS.

SayClip Onboarding creates a `.venv` folder inside this project and installs
Python dependencies there. It does not modify your system Python packages.

## Local Speech Recognition

SayClip uses speech recognition to turn your spoken title into the final file
name. Recognition is local at runtime: audio is recorded locally, temporary
audio stays on your machine, and the configured Faster Whisper model is loaded
from a local folder.

To recognize speech locally, SayClip needs a recognition model on disk. The
onboarding installer can download one of these Faster Whisper model folders:

- Fastest: `Systran/faster-whisper-tiny`
  `https://huggingface.co/Systran/faster-whisper-tiny`
- Balanced: `Systran/faster-whisper-small`
  `https://huggingface.co/Systran/faster-whisper-small`

Downloaded models are saved under this project folder:

```text
models\faster-whisper-tiny
models\faster-whisper-small
```

The model download comes from Hugging Face, which is a third-party source.
Review the shown link before continuing. SayClip does not control third-party
files, hosting, availability, or future changes to those pages.

You can also skip the download and choose an existing local Faster Whisper model
folder. A valid folder should contain at least `config.json`, `model.bin`, and
`tokenizer.json` or `vocabulary.txt`.

## Speech Language

The speech language setting tells Faster Whisper what language to expect for
your voice titles. The UI lists common choices:

- `en` for English
- `zh` for Chinese
- `es` for Spanish
- `fr` for French
- `de` for German
- `ja` for Japanese
- `ru` for Russian

Other Faster Whisper/Whisper language codes can be typed manually.

## Rename Format

The rename format controls how SayClip builds the new recording or replay file
name. The spoken title is always sanitized for Windows filenames.

Supported variables:

- `{title}`: recognized spoken title. This is required for voice naming.
- `{datetime}`: clip or recording time formatted with `datetime_format`.
- `{source}`: OBS/game/source title resolved by the OBS bridge.
- `{job_type}`: short action type, `rec` for recording or `clip` for replay
  buffer moment.
- `{game}`: legacy alias for the source/game value.

Built-in presets:

- Spoken title only:
  `{title}` -> `clean-overtake.mkv`
- Time + spoken title:
  `{datetime}__{title}` -> `2026-05-27_22-10-44__clean-overtake.mkv`
- Source + time + spoken title:
  `{source}__{datetime}__{title}` ->
  `test-game__2026-05-27_22-10-44__clean-overtake.mkv`
- Source + clip type + time + spoken title:
  `{source}__{job_type}__{datetime}__{title}` ->
  `test-game__clip__2026-05-27_22-10-44__clean-overtake.mkv`

Custom formats must include `{title}`. Without it, the recognized voice title
has nowhere to go.

## Date And Time Format

`datetime_format` uses Python `strftime` patterns. It is only used when your
rename format contains `{datetime}`.

Common patterns:

- `%Y-%m-%d_%H-%M-%S` -> `2026-05-27_22-10-44`
- `%Y%m%d_%H%M%S` -> `20260527_221044`
- `%Y-%m-%d` -> `2026-05-27`
- `%H-%M-%S` -> `22-10-44`

Avoid characters that Windows does not allow in filenames, such as `:`, `?`,
`*`, `<`, `>`, `|`, and quotes. SayClip sanitizes invalid filename characters,
but readable patterns are easier to debug.

## Stream Deck Plugin

SayClip has planned first-class Stream Deck support that does not use hotkeys.

The plugin talks to the SayClip backend on localhost:

```text
http://127.0.0.1:17891
```

OBS bridge remains the only component that controls OBS. The Stream Deck plugin calls backend save endpoints, the backend exposes one bridge command, and the OBS bridge polls and executes OBS actions.

PySide, OBS dock, and Stream Deck should all use the same backend save/status contract.

v1 actions:

- CLIP: save replay buffer moment.
- REC: stop active recording and rename it.
- STATUS: show backend state.

## OBS Script

Load this product-facing script in OBS:

```text
SayClip_Starter.py
```

If setup is missing, it opens SayClip Onboarding. On normal OBS startup it launches the backend in headless mode. Use `Open Backend UI` from the script properties to restart the backend with the PySide window visible.

## Source Name In Filenames

The OBS script has two setup areas:

- Backend: controls how the local backend starts.
- Title setup: optionally chooses the OBS source name used for `{source}` in renamed files.

For filename formats that include `{source}`, SayClip resolves the source like this:

1. If `Title source name` is filled in the OBS script settings and OBS has a source with that name, read that source's window/title setting as `source_title`.
2. Otherwise use `source_title` if the OBS bridge provides one.
3. Otherwise use the parent folder of the saved recording/replay file.
4. If neither value is usable, omit the source token.

If the configured OBS source exists but does not expose a usable window/title setting, SayClip still falls back to the parent folder instead of using the OBS source name itself. Leave `Title source name` empty to keep the previous parent-folder behavior.

## OBS Custom Browser Dock

1. Start SayClip backend.
2. Open OBS.
3. Go to Docks -> Custom Browser Docks.
4. Add:
   Name: SayClip
   URL: http://127.0.0.1:17891/dock
5. Apply.

## License and Attribution

SayClip is free and open-source software licensed under the GNU General Public
License v2.0 or later.

You are free to use, study, modify, and redistribute SayClip under the terms of
the GPL-2.0-or-later license.

SayClip was originally created by AI Toolmaker (AI Toolmaker Official).

If SayClip helps you, attribution is appreciated:

- Star the official repository:
  https://github.com/aitoolmakerofficial/obs-sayclip
- Credit the original author: AI Toolmaker (AI Toolmaker Official)
- Subscribe to the YouTube channel:
  https://www.youtube.com/@WorkingAiTools
- Share the official project page:
  https://github.com/aitoolmakerofficial/obs-sayclip

Please do not present modified builds, forks, mirrors, or unofficial
distributions as the official SayClip release.

Official releases are published only through the official SayClip repository:

https://github.com/aitoolmakerofficial/obs-sayclip
