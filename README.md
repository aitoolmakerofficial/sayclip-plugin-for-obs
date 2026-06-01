# SayClip

Local OBS companion tool for voice-titled recording and replay-buffer renames.

## Stream Deck Plugin

SayClip has planned first-class Stream Deck support that does not use hotkeys.

The plugin talks to the SayClip backend on localhost:

```text
http://127.0.0.1:17891
```

OBS bridge remains the only component that controls OBS. The Stream Deck plugin calls backend save endpoints, the backend exposes one bridge command, and the OBS bridge polls and executes OBS actions.

PySide, OBS dock, and Stream Deck should all use the same backend save/status contract.

v1 actions:

- MOM: save replay buffer moment.
- REC: stop active recording and rename it.
- STATUS: show backend state.

Build from the Stream Deck plugin folder:

```bat
cd src\stream_deck_module\easy-rename-stream-plugin
npm install
npm run build
npm run pack
```

Do not install `@elgato/cli` globally. The plugin project must use local npm dependencies through `npm run ...` scripts or local `npx` commands.

Install by opening the generated `.streamDeckPlugin` file, or by using the `Install Stream Deck Plugin` action in the app after the package has been built.

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
