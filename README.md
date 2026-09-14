# NVDA Dark Mode (add-on)

Makes NVDA's own interface dark: NVDA menu, Settings dialog, Add-on Store, message boxes, everything drawn by NVDA itself. Follows the Windows light/dark app setting by default, can be forced on or off, and turns itself off while a Windows High Contrast theme is active.

This folder is NOT part of the website. It is excluded from SFTP uploads (see `.vscode/sftp.json` ignore list). If the add-on is ever offered for download on apps.carrieonaccessibility.com, copy the built `.nvda-addon` file into a product folder under `apps/` and link it from there.

## Layout

- `addon/` - the add-on itself (what gets zipped). `manifest.ini` + `globalPlugins/nvdaDarkMode/`.
  - `theming.py` - the engine: Windows dark-mode switches + wx recolouring. Read its header comment before changing anything; it explains the one accessibility rule that must never be broken (never set text colour on checkboxes/radio buttons/buttons).
  - `__init__.py` - NVDA plumbing: settings category, toggle command, config.
- `build.py` - `python build.py` writes `dist/nvdaDarkMode-<version>.nvda-addon`. `python build.py --install` also copies the add-on into `%APPDATA%\nvda\addons\` for testing (restart NVDA after).
- `dev/testbench.py` - opens a fake "NVDA Settings" dialog using NVDA's own bundled wxPython (no NVDA needed), applies the engine, saves screenshots to `dev/shots/`. Fastest way to check a change visually. `--light` gives the untouched baseline.
- `dev/shoot_nvda.py` - screenshots the running NVDA's windows. Sends NVDA keyboard shortcuts by injecting keystrokes, which only lands in NVDA's dialogs if they have focus; use with care.
- `dev/flashcap.py` - films the screen centre at ~60 fps from outside NVDA and reports how bright each frame was, to catch flashes when the NVDA menu opens. `python dev/flashcap.py NAME` pops the menu through the dev hook; `--wait 60` films while you open it yourself with NVDA+N. Filming from inside NVDA slows NVDA down and distorts what you're measuring, which is why this is a separate process.
- `dev/exp_grip.py` - tiny resizable dialog for checking the size grip painter (the bench dialog is not resizable).
- `dev/exp_erase.py` - shows one of every control type, then blocks its own main thread so nothing can paint, while a helper thread photographs it: whatever is white in that photo is what flashes in NVDA between a dialog's erase and its first paint. Pops a window titled "Erase test (Not Responding)" - that is expected.
- `dev/sweep.py` - the full audit: every settings category (through the category list, top and scrolled to the bottom), every dialog the dev hook can open, and the menus; flags dark text on dark backgrounds and light backgrounds per control. Run it after any painting change; it should end with "nothing flagged".
- `dist/` - built packages.

## Versioning

Bump `version` in `addon/manifest.ini` (major.minor.patch) and rebuild. `lastTestedNVDAVersion` should be raised after testing on a new NVDA release.

## Add-on Store

Needs: a public source repo, the `.nvda-addon` at a permanent https URL, a licence (GPL v2 like NVDA), then the registration issue form at https://github.com/nvaccess/addon-datastore. First submission takes up to two weeks for publisher approval.
