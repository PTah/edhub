# Install and run (Windows)

## What you get

Top-screen exploration overlay for Elite Dangerous, tray icon, optional uploads
to EDSM / EDDN / INARA. Config and caches:
`%LOCALAPPDATA%\EliteDangerousHUD\`.

## Prerequisites

* Windows 10/11
* Either:
  * **Release build** (recommended): no Python needed, or
  * **From source**: Python 3.10+ from python.org with **tcl/tk** enabled

## Path A — release (one installer / portable)

1. Open https://github.com/PTah/edhub/releases
2. Download `EDHUD-Setup-<ver>.exe` **or** `EDHUD-portable.zip`
3. Run the setup, or unpack the zip and start `EDHUD.exe`
4. Start Elite Dangerous (Borderless / Windowed — exclusive fullscreen hides overlays)
5. Confirm the tray icon appears; open **Settings** if the journal folder was not found

**Check:** overlay shows the current system after you are in-game in space.

## Path B — from source

```bat
cd edhub
python run.py
```

Or double-click `run.pyw` (no console window).

Optional:

```bat
python run.py run --journal-dir "%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous"
python run.py run --offline
```

**Check:** same as Path A; or `python run.py dump` prints one HUD frame.

## Build locally

```bat
build_windows.bat
```

Needs Inno Setup 6 for the Setup.exe. Artifacts land in `dist\`.

## If it does not work

| Symptom | Likely cause | What to do |
|---|---|---|
| No overlay in game | Exclusive fullscreen | Graphics → Display Mode → Borderless |
| Empty / wrong system | Journal folder wrong | Settings → journal path; see `edhud.log` |
| No EDSM/EDDN/INARA | Network / keys / checkbox | See [data-uploads.md](data-uploads.md) |
| INARA `no access allowed` | App not whitelisted | INARA must allow `appName` `EDHUD` |
