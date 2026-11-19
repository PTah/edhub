# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

VERSION = "1.8.21"

NOTES = """**1.8.21: hide BIO on STAR and gas giants**

- STAR line no longer shows BIO (stars have no biological signals)
- Gas giants (Sudarsky / helium-rich / …) also hide BIO on the body line

Version 1.8.21."""

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
