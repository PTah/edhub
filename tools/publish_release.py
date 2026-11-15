# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

NOTES = """**Хотспоты колец: скан сразу виден в «Добыче», плюс своя база и фильтр по минералу**

- Просканировали кольцо DSS — таблица «Добыча» обновляется сама (раньше её надо
  было перечитывать вручную, из-за этого скан был виден только в Bodies).
- В строке кольца теперь полный состав хотспотов (`Alexandrite ×2, Tritium ×3`),
  тип кольца (`Icy`/`Metallic`/…) и запас из скана (`Pristine`/`Major`/…).
- Выпадающий «материал» стал настоящим фильтром: показываются только тела/кольца,
  где этот минерал реально есть, и цена считается по нему.
- Новая кнопка **«Мои кольца»** ищет по своей базе `hotspots.json`: минерал +
  радиус от текущей системы, сначала ближайшие. База копится автоматически из
  всех ваших сканов колец и переживает перезапуск.
- «Искать у Spansh» по-прежнему ищет тела в радиусе, но состав колец у Spansh
  отсутствует в API (только тип/масса/радиус) — колонка «Минералы» там пустая,
  это честно подписано в статусной строке.
- README: раздел «Добыча в кольцах: что есть у других» — обзор 5 проектов
  (EliteMining, ED Hotspots Finder, ed-hotspot-mining, EDMC Mining Analytics,
  Mining Analyser) и 6 веб-сервисов с тем, что стоит оттуда взять.

Версия 1.5.4. Тесты: 234 passed."""

ASSETS = [
    r"dist\EDHUD-portable-1.5.4.zip",
    r"dist\EDHUD-1.5.4-windows.zip",
    r"dist\EDHUD-Setup-1.5.4.exe",
]

cmd = ["gh", "release", "create", "v1.5.4", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.5.4", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
