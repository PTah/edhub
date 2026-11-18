# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

VERSION = "1.8.5"

NOTES = """**1.8.5: UI language switcher**

- Settings → Appearance and localization: Russian / English
- Language applies to HUD, menus, voice and Summary tabs without restart
- Overlay context menu uses the same translations

Version 1.8.5."""

ASSETS = [
    rf"dist\EDHUD-portable-{VERSION}.zip",
    rf"dist\EDHUD-{VERSION}-windows.zip",
    rf"dist\EDHUD-Setup-{VERSION}.exe",
]

cmd = ["gh", "release", "create", f"v{VERSION}", *ASSETS, "--repo", "PTah/edhub",
       "--title", f"EDHUD {VERSION}", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
