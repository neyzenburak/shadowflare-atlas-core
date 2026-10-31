# First-run setup and local packages

Clone/download the repository into a writable folder and open `start.cmd`.
No existing Atlas asset ZIP, research workspace or Cheat Engine installation
is required. Use your own verified English ShadowFlare v2.004 installation.
The executable must match the SHA-256 checked by the live companion.

The Windows launcher:

1. Finds Python 3.9+ or installs it for the current user. Its fallback is the
   [official Python 3.14.10 installer](https://www.python.org/downloads/release/python-31410/),
   checked against the published SHA-256 and a valid Python Software
   Foundation Authenticode signature before execution.
2. Finds the selected/running/registered game, or opens a file picker for
   `ShadowFlare.exe`. `-GamePath` overrides discovery. The choice is saved in
   `app/installation.json`, which is personal and excluded from packages.
3. When assets are missing, creates `.setup-venv` and installs
   `requirements-setup.txt`. These dependencies are used only to build assets.
4. Runs the nine-phase read-only extraction pipeline: native items/tables and
   scenarios, catalogue/drop model, inventory icons and monster animations,
   bitmap fonts, map scenes/textures, spawn links, world terrain, an empty
   trainer catalogue and the scenario-item guide.
5. Validates generated references before publishing them into `app/`, then
   creates a desktop shortcut and starts the local companion/browser.

The first build is CPU-intensive. Keep the console open and follow its phase
messages. The original full-edition clean Windows/Python 3.12 verification run took about 47 minutes;
time varies with CPU and storage. Later launches reuse the completed assets and need no build tools
or Internet. `setup.cmd` performs setup without starting the companion.
Use the Atlas launch card to start the game at your preferred resolution,
then load a character to use live controls.

## Resuming or rebuilding

Build state lives in `.setup-cache`, keyed by the selected source files and
builder version. Completed phases are skipped; completed monster variants
and map checkpoints can also be reused. A process lock prevents overlapping
builds in the same checkout. Failed extraction does not publish a half-built
catalogue. Keep the cache when retrying an interrupted first setup.

`start.cmd -RebuildAssets` reruns the builder and republishes verified assets.
`start.cmd -CheckOnly` checks the runtime and required asset entry points
without installing, opening a picker or writing configuration.

Advanced/manual build, after installing `requirements-setup.txt`:

```powershell
python tools/build_assets.py --game "C:\Games\ShadowFlare"
```

The optional `--output` and `--work` arguments select an installation target
and an isolated cache. Do not reuse a work directory with another game/tool
version. Source extraction writes no game resources and never loads a save.

## Build a complete ZIP

Open `make-zip.cmd`, or run `start.cmd -Package`. Missing assets are generated
first. `tools/package_local.py` writes `ShadowFlare-Atlas-Core.zip` in the parent
folder, validates ZIP integrity and compares every entry with its source.

The ZIP includes the browser, companion, plans, generated artwork/data and
portable extraction tools. It excludes Python/virtual environments, caches,
game EXE/DLLs, saves, personal settings/paths, grail databases, logs and dumps.
A recipient with Python can use the prebuilt assets offline; missing Python
still requires its initial download.

Core contains no game-language patch, installer, text corpus or font/story
patch recipes. It never installs or removes a language patch from your game.

## Optional resources and resolution helpers

Curated guide facts provide episode/map ordering and item cross-references.
Guide scans/screenshots are not present in a stock game and are optional.
Unavailable image buttons are hidden; native game renders and map navigation
remain available. A CT file is entirely optional. Place your own CT beside
`ShadowFlare.exe` for automatic import, or select one with **Add CT file** in
Trainer. Its contents stay local and never enter a generated ZIP.
Atlas-specific features work without an imported CT.

Custom resolution startup is built into **Control Desk → Launch ShadowFlare**.
Width/height default to 1920×900 and are remembered locally.
`start.cmd -LaunchGame -Width 1920 -Height 900` provides the same launch path.
Neither external configurator/patcher executable is required. Existing games
are kept running; a changed preference applies to the next launch. See
[resolution startup](GAME_LAUNCH.md).
