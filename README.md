# Instant Easy Rename

Local OBS companion tool for voice-titled recording and replay-buffer renames.

## Stream Deck Plugin

Instant Easy Rename has planned first-class Stream Deck support that does not use hotkeys.

The plugin talks to the Instant Easy Rename backend on localhost:

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
InstantEasyRename.py
```

If setup is missing, it opens the Zero Step installer. On normal OBS startup it launches the backend in headless mode. Use `Open Backend UI` from the script properties to restart the backend with the PySide window visible.

## Source Name In Filenames

The OBS script has two setup areas:

- Backend: controls how the local backend starts.
- Title setup: optionally chooses the OBS source name used for `{source}` in renamed files.

For filename formats that include `{source}`, Instant Easy Rename resolves the source like this:

1. If `Title source name` is filled in the OBS script settings and OBS has a source with that name, use that source name as `source_title`.
2. Otherwise use `source_title` if the OBS bridge provides one.
3. Otherwise use the parent folder of the saved recording/replay file.
4. If neither value is usable, omit the source token.

Leave `Title source name` empty to keep the previous parent-folder behavior.

## OBS Custom Browser Dock

1. Start Instant Easy Rename backend.
2. Open OBS.
3. Go to Docks -> Custom Browser Docks.
4. Add:
   Name: Instant Easy Rename
   URL: http://127.0.0.1:17891/dock
5. Apply.
