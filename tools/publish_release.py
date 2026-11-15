# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

NOTES = """**Статистика по сессиям, автопереключение вкладок после прыжка, окно настроек помнит размер**

- В настройках новая вкладка **«Статистика»**: строка на каждый вход в игру
  (= файл журнала) и итог по всем сессиям. Считается: прыжки, пройденные ly,
  новые системы и новые тела, сканы, DSS-картография, био-анализы, продано
  кредитов (картография + биология). История копится в `stats.json`.
- Раньше после ручного выбора вкладки «Добыча» (или «Пояса») автопереключение
  залипало навсегда. Теперь вручную выбранную вкладку никто не отбирает, но
  прыжок в новую систему возвращает окно на Bodies, а зарядка прыжка с
  проложенным маршрутом — на Route.
- Окно настроек больше не открывается сжатым по высоте (680 px по умолчанию),
  а его размер и положение запоминаются в `settings_geometry` — раздвигать
  мышкой каждый раз не нужно.
- В README: разделы про автопереключение, статистику и файлы данных.

Версия 1.5.5. Тесты: 242 passed."""

ASSETS = [
    r"dist\EDHUD-portable-1.5.5.zip",
    r"dist\EDHUD-1.5.5-windows.zip",
    r"dist\EDHUD-Setup-1.5.5.exe",
]

cmd = ["gh", "release", "create", "v1.5.5", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.5.5", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
