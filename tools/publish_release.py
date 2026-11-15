# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

NOTES = """**1.7.8: в окне «Биосигналы» видно, был ли первый шаг**

- По каждой планете в списке появилась метка первого шага (first footfall):
  **FF+** зелёным — на планету ещё никто не ступал, бонус за first footfall
  реально получить; **FF** серым — уже ступали, бонуса не будет.
- Берётся из журнального `Scan` → `WasFootfalled`, без чужих API.
- Метка есть и у строки тела в общем списке, и в заголовке карточки выбранного
  тела (FSS/SAA). Под списком — короткая сноска, что означают FF+/FF.
- Подсказки «с первым шагом» внизу панели остались: они считают деньги с
  множителем 5×, метка отвечает на вопрос «а он вообще свободен?».
- Тесты: 321 passed (свободен / уже был / газовый гигант без метки / карточка
  тела в FSS).

Версия 1.7.8."""

ASSETS = [
    r"dist\EDHUD-portable-1.7.8.zip",
    r"dist\EDHUD-1.7.8-windows.zip",
    r"dist\EDHUD-Setup-1.7.8.exe",
]

cmd = ["gh", "release", "create", "v1.7.8", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.7.8", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
