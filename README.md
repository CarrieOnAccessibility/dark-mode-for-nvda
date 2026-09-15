# Dark Mode for NVDA

Dark mode for NVDA's own user interface, including windows, dialogs, and menus. An NVDA add-on by [Carrie on Accessibility](https://apps.carrieonaccessibility.com).

NVDA has no dark mode of its own yet (NVDA issue #16683 is the one to watch). Until it does, this add-on asks Windows for the same dark treatment that File Explorer gets, and repaints the few pieces Windows will not. It changes only how NVDA's windows are painted, never what the controls are, so nothing NVDA announces changes.

- NVDA's help pages (User Guide, Commands Quick Reference, What's New, add-on help) open as dark copies; the originals are never touched.
- Turn it off and on from the NVDA menu (Preferences > Dark mode), the Dark Mode settings category, or a command you assign under Input Gestures.
- Steps aside automatically while a Windows High Contrast theme is active.
- Needs NVDA 2026.1 or later; black title bars and the grey window outline need Windows 11.

## Install

Download the latest `darkMode-<version>.nvda-addon` from the Releases page and open it; NVDA asks to install it.

## Licence

Copyright (C) 2026 Carrie on Accessibility. Free software under the GNU General Public License, version 2 - see [LICENSE](LICENSE).

## Development notes

## Layout

- `addon/` - the add-on itself (what gets zipped). `manifest.ini` + `globalPlugins/darkMode/`. `darkdocs.py` wraps NVDA's `getDocFilePath` so help files open from a dark copy under `%TEMP%\darkMode-docs\` (one folder per source folder + stylesheet; older copies are dropped).
  - `theming.py` - the engine: Windows dark-mode switches + wx recolouring. Read its header comment before changing anything; it explains the one accessibility rule that must never be broken (never set text colour on checkboxes/radio buttons/buttons).
  - `__init__.py` - NVDA plumbing: settings category, toggle command, config.
- `build.py` - `python build.py` writes `dist/darkMode-<version>.nvda-addon`. `python build.py --install` also copies the add-on into `%APPDATA%\nvda\addons\` for testing (restart NVDA after).
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
