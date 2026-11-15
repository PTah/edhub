# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 12:23:47
import subprocess
import sys

NOTES = """**Шапка окна**

- Строка носителя при прыжке идёт по порядку: «Карриер готовится прыгать из
  <System> в <System>, старт через <время>, остаток трития: <тритий>». Раньше
  отсчёт и тритий вклинивались между «из» и названием системы.
- «тел 14/42 · био-тел 0» — теперь того же размера, что и строка носителя;
  цвет остался приглушённым.

Версия 1.5.1. Тесты: 221 passed."""

ASSETS = [
    r"dist\EDHUD-portable-1.5.1.zip",
    r"dist\EDHUD-1.5.1-windows.zip",
    r"dist\EDHUD-Setup-1.5.1.exe",
]

cmd = ["gh", "release", "create", "v1.5.1", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.5.1", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
