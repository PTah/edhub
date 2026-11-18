# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

VERSION = "1.8.6"

NOTES = """**1.8.6: EDSM/INARA setting tooltips**

- Hover tips on EDSM and INARA fields: what is uploaded and how to stop
- Visible INARA hint under the API key fields

Version 1.8.6."""

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
