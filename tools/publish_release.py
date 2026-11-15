# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

NOTES = """**Копание в кольцах: справочник по типу кольца, плотность, способ добычи и лучший сбыт**

- На вкладке «Добыча» по каждому кольцу теперь видно **способ добычи** минерала
  (ядро / лазер) и **плотность кольца** по формуле edtools
  `M/π(Rout² − Rin²)` — из журнального `Scan`, так что кольца можно сравнивать
  между собой (колонка «Плотн.», сортировка по клику).
- Подсказка под таблицей: «Icy · Pristine · плотн. 10.01 — ядро: Void Opals,
  Alexandrite, Grandidierite; лазер: Low Temperature Diamonds, Tritium,
  Bromellite» — справочник по типу кольца (Icy / Metallic / Metal-Rich / Rocky).
- **Лучший сбыт**: по выбранному минералу показывается станция, система и cr/t
  из своего индекса цен (`Market` + EDDN, без ключей и чужих API).
- Плотность и запас кольца сохраняются в `hotspots.json`, поэтому поиск
  «Мои кольца» тоже показывает их у найденных колец.
- В README: раздел «Что уже взято (1.6.0)» — что именно изучено в пяти чужих
  проектах (EliteMining: справочник колец и формула плотности; ed-hotspot-mining:
  приоритет двойных/тройных хотспотов и подбор станции сбыта; EDMC Mining
  Analytics и Mining Analyser: метрики выработки на будущее). Исходники лежат в
  `reference/mining/` и в репозиторий не попадают (`.gitignore`).

Версия 1.6.0. Тесты: 259 passed."""

ASSETS = [
    r"dist\EDHUD-portable-1.6.0.zip",
    r"dist\EDHUD-1.6.0-windows.zip",
    r"dist\EDHUD-Setup-1.6.0.exe",
]

cmd = ["gh", "release", "create", "v1.6.0", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.6.0", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
