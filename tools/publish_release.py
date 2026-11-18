# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

VERSION = "1.8.18"

NOTES = """**1.8.18: star lock and liftoff restore full system bio list**

- Locking the star (Destination.Body = 0) shows all bio signals on the left again
- Liftoff / LeaveBody / SC entry ignore a sticky planet Destination until a new planet is locked
- Soft atmosphere/lat presence no longer keeps a single-planet card after takeoff

Version 1.8.18."""

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
