# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 12:16:37
import subprocess
import sys

NOTES = """**Новая вкладка «Добыча»** — где копать: планетарные точки добычи и кольца.

- Тела текущей системы: материал поверхности и его доля, геология, кольца с
  хотспотами, расстояния в системе и до системы, цена за тонну. Сортировка
  кликом по колонке, двойной клик копирует систему.
- «Искать у Spansh»: тела в радиусе N св. лет от текущей системы,
  отсортированные по доле выбранного материала (по умолчанию редкие).
- «В Пояса» сохраняет выбранное кольцо в локальную базу.
- Цены — свой индекс: рынок станции из журнала (`Market`) плюс поток EDDN
  `commodity` по добываемым товарам. Если рынок ещё не видели, показывается
  средняя цена с пометкой «≈».

Версия 1.5.0. Тесты: 221 passed."""

ASSETS = [
    r"dist\EDHUD-portable-1.5.0.zip",
    r"dist\EDHUD-1.5.0-windows.zip",
    r"dist\EDHUD-Setup-1.5.0.exe",
]

cmd = ["gh", "release", "create", "v1.5.0", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.5.0", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
