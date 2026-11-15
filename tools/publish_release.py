# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

NOTES = """**1.7.3: на старте прыжка блок «био в системе» убирается из дашборда**

- Как только FSD заряжается в другую систему (или прыжок уже идёт), список
  «био в системе» исчезает из верхнего дашборда — во время прыжка он только
  занимает место. Прыжок отменили — список вернулся.
- Работает по `Status.json` (`FsdCharging` + `Destination`), поэтому
  срабатывает сразу, ещё до события `FSDJump`, и не зависит от журнала.
- Зарядка FSD в суперкруизе внутри той же системы список не трогает.
- Тесты: 298 passed (три случая: обычный полёт, прыжок, отмена прыжка).

Версия 1.7.3."""

ASSETS = [
    r"dist\EDHUD-portable-1.7.3.zip",
    r"dist\EDHUD-1.7.3-windows.zip",
    r"dist\EDHUD-Setup-1.7.3.exe",
]

cmd = ["gh", "release", "create", "v1.7.3", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.7.3", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
