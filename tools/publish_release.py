# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

VERSION = "1.8.22"

NOTES = """**1.8.22: exact bio totals after sampling; FF no longer stuck open**

- Planet/system bio totals use exact payouts of analysed organisms instead of prediction ranges
- When all bio signals are taken, speculative «?» species and first-footfall ×5 range are hidden
- Own samples mark first footfall as taken (FF), even if WasFootfalled has not updated yet

Version 1.8.22."""

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
    "PTah/edhub",
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
