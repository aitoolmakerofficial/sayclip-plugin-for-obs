# SayClip

![SayClip GitHub cover](public/sayclip-github-cover.png)

SayClip is a local companion tool for OBS Studio that renames recordings and
Replay Buffer saves using spoken voice titles.

Everything runs locally on your computer. Audio recording, speech recognition,
the backend, browser dock, and file renaming never require cloud services.

📖 **Documentation**  
See the detailed setup and troubleshooting guide:
[`public/user-guide.md`](public/user-guide.md)

🎥 **Video Tutorial**  
Watch the installation and usage guide:
https://www.youtube.com/watch?v=VeY80kJk3RM&list=PLOz1A1R4o9mg

🎮 **Stream Deck Plugin**  
Control SayClip directly from your Stream Deck:
https://github.com/aitoolmakerofficial/sayclip-plugin-for-streamdeck

The local backend listens on:

```text
http://127.0.0.1:17891
```

---

# Quick Install

1. Download or clone the SayClip repository.
2. Open OBS Studio.
3. Go to **Tools → Scripts**.
4. Add `SayClip_Starter.py`.
5. SayClip Onboarding will start automatically if setup is required.
6. Complete the onboarding steps.
7. (Optional) Add the browser dock using:

```text
http://127.0.0.1:17891/dock
```

SayClip creates its own `.venv` inside the project directory and installs all
required Python packages there. Your system Python installation is not modified.

---

# Features

- Voice-powered recording names
- Voice-powered Replay Buffer names
- Local speech recognition
- Faster Whisper support
- Custom filename templates
- Browser Dock
- Stream Deck integration
- Local-only backend
- GPL v2+ Open Source

---

# Local Speech Recognition

SayClip uses Faster Whisper to convert spoken titles into filenames.

Speech recognition is performed locally:

- Audio is recorded locally.
- Temporary audio files remain on your computer.
- Recognition models are loaded from local storage.

During onboarding you can download one of the supported models:

- **Fastest**
  `Systran/faster-whisper-tiny`
  https://huggingface.co/Systran/faster-whisper-tiny

- **Balanced**
  `Systran/faster-whisper-small`
  https://huggingface.co/Systran/faster-whisper-small

Models are stored inside:

```text
models\faster-whisper-tiny
models\faster-whisper-small
```

You may also select an existing Faster Whisper model already available on your
computer.

A valid model folder should contain files such as:

- `config.json`
- `model.bin`
- `tokenizer.json` or `vocabulary.txt`

---

# Speech Language

Common language codes:

- `en` — English
- `zh` — Chinese
- `es` — Spanish
- `fr` — French
- `de` — German
- `ja` — Japanese
- `ru` — Russian

Any Faster Whisper language code may also be entered manually.

---

# Rename Format And Folders

Rename templates support the following variables:

- `{title}`
- `{datetime}`
- `{source}`
- `{short_source}`
- `{job_type}`
- `{game}` (legacy alias)

Examples:

```text
{title}
→ clean-overtake.mkv

{datetime}__{title}
→ 2026-05-27_22-10-44__clean-overtake.mkv

{source}__{datetime}__{title}
→ test-game__2026-05-27_22-10-44__clean-overtake.mkv

{source}__{job_type}__{datetime}__{title}
→ test-game__clip__2026-05-27_22-10-44__clean-overtake.mkv
```

Custom templates must include `{title}`.

`{short_source}` builds a compact source ticker. Hyphen-separated names use
the first character of each part (`dying-light-the-beast` -> `dltb`). One
unbroken name stays unchanged up to 10 characters; a longer one uses its first
five and last five characters (`reddeadredemption` -> `reddeption`).

The same template can organize files into subfolders. In the settings window,
enable `Make folder` beside Source, Short source, Clip type, or Time. SayClip
inserts a folder boundary after that part and creates the directory when the
file is renamed.

```text
{source}/{job_type}/{title}
→ test-game/clip/clean-overtake.mkv

{source}/{datetime}/{title}
→ test-game/2026-05-27/clean-overtake.mkv
```

The folder containing the original file returned by OBS remains the root. For
example, a replay initially saved under `Recordings/moments` stays under that
root and can become `Recordings/moments/test-game/clip/...`.

---

# Date & Time Format

`datetime_format` uses standard Python `strftime` formatting.

Examples:

```text
%Y-%m-%d_%H-%M-%S
→ 2026-05-27_22-10-44

%Y%m%d_%H%M%S
→ 20260527_221044

%Y-%m-%d
→ 2026-05-27

%H-%M-%S
→ 22-10-44
```

---

# Stream Deck Plugin

A native Stream Deck plugin is available for SayClip.

Repository:

https://github.com/aitoolmakerofficial/sayclip-plugin-for-streamdeck

The plugin communicates with the local backend:

```text
http://127.0.0.1:17891
```

Available actions:

- **CLIP** — Save Replay Buffer.
- **REC** — Stop recording and rename it.
- **STATUS** — Show backend status.

The Stream Deck plugin communicates only with the local backend. OBS Studio is
controlled exclusively through the SayClip bridge.

---

# OBS Script

Load the following script:

```text
SayClip_Starter.py
```

If setup has not been completed, the onboarding wizard opens automatically.

During normal startup the script launches the backend in headless mode.

The **Open Backend UI** button can be used to restart the backend with the full
desktop interface.

---

# Source Name in Filenames

If `{source}` is used, SayClip resolves it in this order:

1. The configured **Title source name** from the script settings.
2. `source_title` provided by the bridge.
3. The recording folder name.
4. Omit the value if unavailable.

If the configured OBS source exists but does not expose a usable window title,
SayClip automatically falls back to the recording folder.

---

# Browser Dock

1. Start the backend.
2. Open OBS Studio.
3. Go to **Docks → Custom Browser Docks**.
4. Create a dock named **SayClip**.
5. Use:

```text
http://127.0.0.1:17891/dock
```
# License

SayClip is free and open-source software licensed under the GNU General Public
License v2.0 or later (GPL-2.0-or-later).

---

# Author
Created and maintained by **AI Toolmaker**.
