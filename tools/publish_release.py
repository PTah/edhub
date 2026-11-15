# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

NOTES = """**Добыча 1.7.0: база Spansh, качество камня, выработка и сбыт с учётом расстояния**

- **База хотспотов из дампа Spansh** (`edhud/spanshdb.py`): в настройках новая
  галочка «База хотспотов колец из дампа Spansh» — **по умолчанию выключена**.
  Включили, выбрали дамп (`galaxy_1day` ≈1.1 ГБ, `galaxy_7days` ≈2.7 ГБ,
  `galaxy_1month` ≈5.4 ГБ, `galaxy_populated` ≈4.5 ГБ) и нажали «Обновить базу»:
  качается в фоне, в SQLite `spansh.db` кладутся только кольца с хотспотами
  (система, координаты, тип, плотность, запас, состав). «Мои кольца» потом ищет
  по этой базе офлайн — без API-лимитов и без сети.
- **ProspectedAsteroid**: процент целевого минерала в последнем камне, средний и
  лучший за сессию, число камней и материнских жил. Строка «добыча:» в верхнем
  HUD (рядом с кольцом) и в статусе вкладки. Целевой минерал — выбранный в
  «Добыче»; если не выбран, берётся самый дорогой в камне.
- **Выработка**: `MiningRefined` → тонны и тонны в час; `Cargo` → трюм и оценка
  партии по своему индексу цен; `MarketSell` → что и на сколько продано.
  Всё это по каждой сессии и суммарно в настройках → «Статистика».
- **Станции сбыта с учётом расстояния**: индекс цен теперь хранит до 5 станций
  на товар и `StarPos`; ранг считается как «цена с штрафом за прыжки»
  (`Loadout.MaxJumpRange`). В статусе: станция, система, cr/t, ly и число прыжков.
- README: обновлены разделы «Добыча», «Настройки», «Что уже взято».

Версия 1.7.0. Тесты: 284 passed."""

ASSETS = [
    r"dist\EDHUD-portable-1.7.0.zip",
    r"dist\EDHUD-1.7.0-windows.zip",
    r"dist\EDHUD-Setup-1.7.0.exe",
]

cmd = ["gh", "release", "create", "v1.7.0", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.7.0", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
