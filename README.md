**Languages:** [English](README.md) · [Русский](README.ru.md)

# EDHUD — one overlay from three tools

A top-of-screen overlay strip (like SrvSurvey) that shows your route (like
Exploration Buddy / EDEB), biology and geology on the current body, predicted
species, sample progress, distance to the next clonal colony, and exploration
data value with first-discovery multipliers. Primary target is Windows; macOS
and Linux run in terminal (TUI) mode.

```
███████████████·······························   ← route progress
ROUTE 1/3  →  HIP 36601 (A · 50.0 ly)   left 2 · 115.4 ly  Next star — scoopable
BODY Synuefe GG-O c22-4 1 · Icy body · 1 180 ls   BIO 2 (Bacterium, Fungoida) · geo 1   DSS ✔   ≈1.42 Mcr ×2.6
────────────────────────────────────────────────────────────────────────
● Bacterium Cerbrus - Lime  2/3  ≈1.69 Mcr
value: scan ≈120 Kcr · with DSS ≈1.42 Mcr · ×2.6 first discovery
prediction: Bacterium
≈ Bacterium Acies - Lime  1.00 Mcr
bio in system: 2
• Synuefe GG-O c22-4 2 a  1 sig. (Osseus)   DSS ✗   [spansh]   2 410 ls
system: 12 bodies · data ≈3.4 Mcr · with DSS ≈9.8 Mcr · EDSM ≈7.7 Mcr / mapped ≈9.1 Mcr
session: 2 jumps · scan 120 Kcr · DSS 1.3 Mcr · bio ≈1.69 Mcr
```

## What was taken from each project

| Project | Taken |
|---|---|
| **EDMarketConnector** (EDCD, Python) | Reading `Journal*.log` (newest file, resume from offset, startup replay), `Status.json` / `NavRoute.json` by mtime, journal folder discovery, `Flags` bit parsing. |
| **SrvSurvey** (njthomson, C#) | Overlay: borderless always-on-top click-through window. Biology prediction engine and `bio-criteria/*.json`, genus sample distances, galactic regions, codex reference, scan value formula, Guardian bubble, system cache. |
| **EDDiscovery** (C#) | Route ideas: `NavRoute.json`, progress/remaining, Spansh Galaxy Plotter, route independent of the game. |
| **EDEB / Exploration Buddy** | HUD feature set: route with progress, lock/import, species prediction, analysis status, clonal colony indicator, sample value, bodies discovered by other commanders, `?` for unknown bodies. |

## Features

* **Top overlay**: centered strip, transparency/colors/font in config. Windows tray
  icon (overlay, Spansh/EDSM map, settings, quit); `F8` details, `F9` click-through,
  `F10` show/hide, `F12` quit. Panels show **only in-game in space**; on planet /
  SRV / on-foot the dashboard dims; bio panel stays visible. Game-running is
  detected via fresh `Status.json`. Summary window keeps bodies + route.
* **Bio signals** (left panel): species with prices, first-logged ×5, sample radar,
  foreign Canonn points. Per-planet first footfall: `FF+` / `FF` from
  `WasFootfalled` in journal `Scan`.
* **Settings** (tray → Settings): journal folder, network, EDSM/Spansh/EDDN,
  optional EDSM and INARA API keys, voice, overlay geometry, **Statistics** tab,
  Spansh hotspot dump DB, update checks. **Appearance and localization** —
  theme/fonts/colors and **UI language** (Russian / English; default follows
  Windows). Config: `%LOCALAPPDATA%\EliteDangerousHUD\config.json`.
* **Summary** (Route / Bodies / Belts / Mining): system bodies, auto tab switch
  on jump charge / arrival. Own discoveries highlighted.
* **Mining**: ring type/reserve/density (edtools formula), hotspot composition,
  core vs laser, sell suggestions from local price index (`Market` + EDDN
  commodity), prospecting metrics (`ProspectedAsteroid` / `MiningRefined`).
* **Voice** (Windows SAPI): bio found / system first discovery (after journal
  catch-up; replay is silent).
* **Route**: progress, next system, scoopable hint, lock/import/export, Spansh
  plotter.
* **Other commanders’ data**: EDSM + Spansh cache and live EDDN subscribe
  (`tcp://eddn.edcd.io:9500`). Bodies tagged `[EDSM]` / `[spansh]` / `[EDDN]`.
* **Uploading your own data** (see [docs/data-uploads.md](docs/data-uploads.md)):
  - **EDSM** — journal API (commander + API key).
  - **EDDN** — live upload, no key; feeds Spansh / EDSM / INARA / edastro.
  - **INARA** — travel events (commander + personal API key). App name `EDHUD`
    must be whitelisted by INARA. Body scans reach INARA via EDDN, not INARA API.
  - **Spansh** has no public write API — it consumes EDDN.
* **Values**: scan / DSS / first discovery ×2.6 / mapping multipliers / Odyssey
  bonus / First Logged ×5 for organics.
* **Legacy 3.8**: Odyssey bonus, bio prediction and remote feeds disabled;
  HUD shows `[Legacy 3.8]`.
* **Terminal mode** (`--tui`) and `--demo` synthetic journal.

More detail (Russian, full): [README.ru.md](README.ru.md).

## Quick start (Windows)

Python 3.10+ with tkinter (python.org installer, enable tcl/tk). No third-party
packages.

```bat
python run.py
python run.pyw
python run.py run --journal-dir "C:\Users\me\Saved Games\Frontier Developments\Elite Dangerous"
python run.py run --tui
python run.py run --demo
python run.py run --offline
python run.py dump
python run.py remote "HIP 36601"
python run.py eddn --seconds 20
```

Default journal folders:

* Windows: `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`
* macOS: `~/Library/Application Support/Frontier Developments/Elite Dangerous`
* Linux/Proton: `…/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous`

Settings and caches live under `%LOCALAPPDATA%\EliteDangerousHUD`
(`config.json`, `systems/`, `remote/`, `spansh.db`, `stats.json`, `prices.json`, …).

Step-by-step: [docs/install-windows.md](docs/install-windows.md).

### Exclusive fullscreen

DirectX exclusive fullscreen blocks third-party overlays. Use **Borderless**
(or `Alt+Enter`). EDHUD reasserts topmost every 2 s and can warn once per
session when exclusive mode is detected.

### Build exe (portable + setup)

Python 3.10+ with tkinter. For the installer: [Inno Setup 6](https://jrsoftware.org/isdl.php).

```bat
build_windows.bat
```

Output in `dist\`:

| File | Purpose |
|---|---|
| `EDHUD-portable\EDHUD.exe` | Single-file portable |
| `EDHUD-portable.zip` | Same, zipped |
| `EDHUD\` | Folder build (installer input) |
| `EDHUD-Setup-<ver>.exe` | Windows installer |

Target PC does **not** need Python. Autostart without installer: shortcut to
`EDHUD.exe` in `shell:startup`.

## Routes

```bash
python run.py lock
python run.py unlock
python run.py import-route route.csv
python run.py plot "Sol" "Colonia" --range 60 --efficiency 60
python run.py export-route route.json
```

Locked/plotted routes live in `route_locked.json` and override the game route.
`plot` uses `https://spansh.co.uk/api/route`.

## Architecture

```
Journal*.log / Status.json / NavRoute.json
        │  edhud/journal.py
        ▼
edhud/model.py   GameState
        │        ├── bio / values / remote / eddn / galaxy / codex / regions / store
        ▼
edhud/hudmodel.py  HudView (no UI)
        ├── edhud/overlay.py  (+ winapi.py)
        └── edhud/tui.py
```

Uploads: `edhud/edsm_upload.py`, `edhud/eddn_upload.py`, `edhud/inara_upload.py`
(wired from `edhud/app.py` on each live journal event).

EDDN subscribe check: `python run.py eddn --seconds 20`.

## Tests

```bash
python -m unittest discover -s tests
python tools/inspect_bio.py
python tools/eddn_probe.py
```

## Data, licenses, credits

* `data/bio-criteria/*.json` — [SrvSurvey](https://github.com/njthomson/SrvSurvey) (GPL-3.0)
* `data/galaxy_regions.json` — [EliteDangerousRegionMap](https://github.com/klightspeed/EliteDangerousRegionMap) (MIT)
* `data/codex_ref.json` — Canonn / SrvSurvey codex extract
* Exploration value formulae — Frontier forums thread
* System data — EDSM, Spansh, live EDDN
* Journal ideas — EDMarketConnector, EDDiscovery, Exploration Buddy

Code is **GPL-3.0** (because of the criteria data); see `LICENSE`.

Rebuild vendored data: `sh tools/fetch_reference.sh && python tools/vendor_data.py`.

## Not included (yet)

* Built-in galaxy map (opens Spansh/EDSM in the browser)
* EDEB-style Surroundings / History tabs
* Automated hotspot overlaps (game does not publish hotspot coordinates)
* Full Spansh dump is optional and large — enable in Settings when needed

## Links

* Releases: https://github.com/PTah/edhub/releases
* Source: https://github.com/PTah/edhub
* Russian README: [README.ru.md](README.ru.md)
* Data uploads (EDSM / EDDN / INARA): [docs/data-uploads.md](docs/data-uploads.md)
