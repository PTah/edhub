# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

VERSION = "1.8.19"

NOTES = """**1.8.19: new in-game route replaces finished sphere tour; route label clarified**

- A route plotted in the galaxy map after loading a sphere tour (destination outside the tour) replaces it in Route
- HUD label "[залочен]" renamed to "[маршрут зафиксирован]" / "[route pinned]"

Version 1.8.19."""

ASSETS = [
    rf"dist\EDHUD-portable-{VERSION}.zip",
    rf"dist\EDHUD-{VERSION}-windows.zip",
    rf"dist\EDHUD-Setup-{VERSION}.exe",
]

cmd = [
    "gh",
    "release",
    "create",
    f"v{VERSION}",
    *ASSETS,
    "--repo",
    "PTah/edhud",
    "--title",
    f"EDHUD {VERSION}",
    "--notes",
    NOTES,
]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
