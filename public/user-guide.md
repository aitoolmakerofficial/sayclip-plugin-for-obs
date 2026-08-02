# SayClip User Guide

SayClip is a local OBS app for naming recordings and replay-buffer clips with your voice.

The main idea is simple:

1. You press `Save Clip` or `Save Recording`.
2. OBS saves or stops the media file.
3. SayClip listens for a short spoken title.
4. SayClip renames the file using your configured filename format.

Example:

```text
Original OBS file:
2026-06-14_17-08-20.mp4

You say:
test of my boo sink

Renamed file:
test-game__clip__2026-06-14_17-08-20__test-of-my-boo-sink.mp4
```

## Quick Start

1. Open OBS.
2. Go to `Tools -> Scripts`.
3. Add `SayClip_Starter.py`.
4. Finish SayClip onboarding if it opens.
5. In the OBS script panel, keep `Backend start mode` set to `Start with OBS`.
6. Open `Open Backend UI` if you want to change microphone, language, or rename format.
7. Optional: add the OBS browser dock at `http://127.0.0.1:17891/dock`.
8. Optional: install the Stream Deck plugin and add `Save Moment`, `Save Recording`, or `SayClip Status` actions.

## What Each Part Does

SayClip has a few moving parts:

- OBS script: starts the backend and talks to OBS.
- Backend: records audio, runs speech recognition, and renames files.
- Backend UI: lets you change settings and see recent jobs.
- OBS browser dock: gives you clip/record buttons inside OBS.
- Stream Deck plugin: gives you physical buttons for saving clips and recordings.


## How Source Names Work

This is one of the most important filename rules.

If your rename format contains `{source}`, SayClip needs a source/game name.

SayClip resolves `{source}` in this order:

1. If `Title source name` is filled in and OBS has a source with that name, SayClip tries to read that source's window/title setting.
2. If the bridge already has a `source_title`, SayClip uses it.
3. Otherwise, SayClip uses the parent folder of the saved OBS file.
4. If no useful value exists, SayClip omits the source part.

Example with parent-folder fallback:

```text
OBS saves:
D:\Recordings\Test Game\2026-06-14_17-08-20.mp4

Rename format:
{source}__{datetime}__{title}

You say:
clean overtake

Result:
test-game__2026-06-14_17-08-20__clean-overtake.mp4
```

If all recordings go into one generic folder, the fallback may look bad:

```text
D:\Recordings\2026-06-14_17-08-20.mp4
```

In that case `{source}` may become `recordings`, or it may be omitted depending on your configuration and file path. For better names, set `Title source name` in the OBS script to the source that represents your game/window capture.

Important: `Title source name` is the OBS source name, not the game title you want to type manually. For example, if your OBS source is named `Game Capture`, enter:

```text
Game Capture
```

SayClip then tries to read the actual window title behind that source.


## OBS Script Setup

![OBS Scripts window with SayClip Starter selected](<say_clip_ui_ (4).png>)

The OBS script panel has two main sections.

Backend:

- `Backend start mode`: choose whether SayClip starts with OBS or manually.
- `Backend status`: shows whether the backend is connected.
- `Stop Backend`: stops the local backend.
- `Force Restart Backend`: restarts the backend.
- `Open Backend UI`: restarts the backend with the settings window visible.

Title setup:

- `Title source name`: optional OBS source name used to resolve `{source}` in filenames.


## Backend UI

The backend UI shows the current SayClip session.

![SayClip backend UI while listening](<say_clip_ui_backend.png>)

Important areas:

- `Backend OK`: the local backend is running.
- `Bridge Waiting` or `Bridge Connected`: whether the OBS script is connected to the backend.
- `Session status`: the current rename flow.
- `Microphone`: selected input device and live level meter.
- `Recent jobs`: recent clips/recordings for this backend session.
- `Settings`: speech recognition, model path, language, rename format, and microphone.
- `Details`: diagnostic checks and logs.
- `Interfaces`: OBS dock URL and Stream Deck plugin link.


## Rename Format

![SayClip settings window with rename format builder](<say_clip_ui_ (2).png>)

Rename format controls the final filename and optional subfolders.

Available parts:

- `{title}`: the title you say out loud.
- `{datetime}`: date/time from the original OBS filename when possible, otherwise current time.
- `{source}`: game/source title or parent-folder fallback.
- `{short_source}`: compact game/source ticker for mixed clip folders.
- `{job_type}`: short token for recording or clip.
- `{game}`: legacy alias for `{source}`.

Common formats:

```toml
format = "{datetime}__{title}"
```

```text
2026-06-14_17-08-20__clean-overtake.mp4
```

```toml
format = "{source}__{datetime}__{title}"
```

```text
test-game__2026-06-14_17-08-20__clean-overtake.mp4
```

```toml
format = "{source}__{job_type}__{datetime}__{title}"
```

```text
test-game__clip__2026-06-14_17-08-20__clean-overtake.mp4
```

The voice title should always be included. If `{title}` is missing, your spoken title has nowhere to go.

`{short_source}` abbreviates normalized source names:

```text
dying-light-the-beast-inactive -> dltbi
banishers-ghosts-of-new-eden   -> bgone
reddeadredemption              -> reddeption
```

For names containing hyphens, it takes the first character of every part. One
unbroken name stays unchanged up to 10 characters; a longer one combines its
first five and last five characters. The ticker is intended for quick
recognition and is not guaranteed to be unique.

### Organizing Files Into Folders

The visual format builder has a `Make folder` checkbox for Source, Short source,
Clip type, and Time. It inserts a folder boundary after that part. Voice title
remains the filename and cannot currently be made into a folder.

For example, enable Source and Clip type and mark both as folders:

```toml
format = "{source}/{job_type}/{title}"
```

The result is organized automatically:

```text
test-game/clip/clean-overtake.mp4
test-game/rec/full-session.mp4
```

Time can also be a folder. Set the date/time pattern to `%Y-%m-%d` and use:

```toml
format = "{source}/{datetime}/{title}"
```

This produces paths such as:

```text
test-game/2026-06-14/clean-overtake.mp4
```

SayClip treats the folder where OBS created the original media file as the
root. If OBS saves replay-buffer files under `Recordings/moments`, a formatted
clip remains below that folder, for example
`Recordings/moments/test-game/clip/clean-overtake.mp4`.

## Clip And Recording Labels

SayClip has two media actions:

- recording: a full recording.
- moment: a replay-buffer save, displayed to users as a clip.

The internal API still uses the word `moment` in some places because it describes the replay-buffer action. The filename token is configurable.

In `config.toml`:

```toml
[naming.job_type_tokens]
recording = "rec"
moment = "clip"
```

With this config:

```text
recording -> rec
moment    -> clip
```

Change it to:

```toml
moment = "clip"
```

You can use any short label you prefer:

```toml
recording = "full"
moment = "highlight"
```

## Date And Time

`datetime_format` controls how `{datetime}` looks.

Examples:

```toml
datetime_format = "%Y-%m-%d_%H-%M-%S"
```

```text
2026-06-14_17-08-20
```

```toml
datetime_format = "%Y%m%d_%H%M%S"
```

```text
20260614_170820
```

Avoid Windows-forbidden filename characters such as:

```text
< > : " / \ | ? *
```

SayClip sanitizes filenames, but clean formats are easier to understand.

## Local Speech Recognition

SayClip uses local Faster Whisper speech recognition at runtime.

That means:

- your voice title is recorded locally;
- the configured model is loaded from a local folder;
- the backend listens on localhost by default;
- renamed media files stay on your machine.

During setup, the onboarding flow can download a Faster Whisper model. After the model is on disk, recognition runs locally.

Model examples:

```text
models\faster-whisper-tiny
models\faster-whisper-small
```

Use `tiny` if you want faster recognition. Use `small` if you want better recognition and can afford a little more CPU time.

## OBS Browser Dock

![SayClip OBS browser dock](<say_clip_ui_ (5).png>)

The browser dock gives you SayClip controls inside OBS.

Setup:

1. Start SayClip backend.
2. In OBS, go to `Docks -> Custom Browser Docks`.
3. Add a dock:

```text
Name: SayClip
URL:  http://127.0.0.1:17891/dock
```

The dock has buttons for:

- `Save Clip`: save replay buffer and voice-name the result.
- `Save Recording`: stop active recording and voice-name the result.
- status: shows whether SayClip is ready, busy, or waiting for OBS.
- latest job: shows the latest renamed file and an open button when available.

If the dock says the bridge is disconnected, make sure `SayClip_Starter.py` is loaded in OBS and the backend is running.

## Stream Deck

![Stream Deck app with SayClip actions](<say_clip_ui_ (1).png>)

The Stream Deck plugin provides:

- `Save Moment`: save replay buffer and voice-name it.
- `Save Recording`: stop active recording and voice-name it.
- `SayClip Status`: show whether SayClip is ready or busy.

The Stream Deck plugin talks to:

```text
http://127.0.0.1:17891
```

It does not control OBS directly. It asks SayClip backend for an action, then the OBS script executes that action in OBS.

If a Stream Deck button does nothing:

1. Check that OBS is open.
2. Check that `SayClip_Starter.py` is loaded in OBS scripts.
3. Check that the backend says `Backend OK`.
4. Check that the OBS bridge is connected.
5. For clips, check that replay buffer is active.
6. For recordings, check that recording is active.

## Configuration File

Most advanced settings live in:

```text
config.toml
```

Common settings:

```toml
[naming]
format = "{source}__{datetime}__{title}"
datetime_format = "%Y-%m-%d_%H-%M-%S"
unknown_game_token = "unknown-game"

[naming.job_type_tokens]
recording = "rec"
moment = "clip"

[stt]
engine = "faster_whisper"
model_path = "models/faster-whisper-small"
language = "en"

[audio]
device = "default"
max_record_seconds = 8
```

After editing `config.toml`, restart the backend from the OBS script with `Force Restart Backend`, or open the backend UI again.

### My filename has the wrong source

If `{source}` becomes a folder name like `recordings`, SayClip probably used the parent-folder fallback.

Fix options:

- set `Title source name` in the OBS script;
- make OBS save each game into a separate folder;
- remove `{source}` from your rename format.

### My filename starts with the date instead of the source

If `{source}` is unknown, SayClip omits it so the filename does not start with `unknown-game`.

Example:

```text
2026-06-14_17-08-20__clean-overtake.mp4
```

This is usually better than:

```text
unknown-game__2026-06-14_17-08-20__clean-overtake.mp4
```

### The microphone meter does not move

Open `Settings` and choose a different microphone. Then save settings and try again.

### The dock or Stream Deck says bridge disconnected

Check OBS:

- `SayClip_Starter.py` must be loaded in `Tools -> Scripts`.
- Backend status should be connected.
- If needed, click `Force Restart Backend`.

### Save Clip is disabled or does nothing

Replay buffer must be active in OBS. Start replay buffer first, then press `Save Clip`.

### Save Recording is disabled or does nothing

OBS must be actively recording. Start recording first, then press `Save Recording`.
