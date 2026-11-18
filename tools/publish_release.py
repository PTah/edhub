# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

VERSION = "1.8.9"

NOTES = """**1.8.9: full EN refresh for Summary tabs**

- Bodies/Route column headers, Belts hint, Mining labels refresh on language change
- Hotspot tooltips, mining HUD metrics and sell-station jumps are translated
- docs/i18n.md: both languages required for every new UI string

Version 1.8.9."""

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
