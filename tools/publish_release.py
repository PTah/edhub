# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

VERSION = "1.8.0"

NOTES = """**1.8.0: «Маршрут по шару» — обход всех систем в радиусе и загрузка его в маршрут**

- Новая вкладка **«Маршрут по шару»**: система (вручную или двойным кликом по
  названию в шапке окна) + расстояние в ly → **«Рассчитать»**. Берутся все
  системы EDSM в шаре этого радиуса, строится замкнутый обход: каждая система
  один раз, затем возврат в старт (ближайший сосед + 2-opt, приближённо).
- Кнопка **«В маршрут»**: обход попадает в залоченный маршрут (вкладка Route и
  верхний HUD с прогрессом), следующая система сразу копируется в буфер, после
  каждого прыжка — следующая. В игру маршрут не прокладывается: цель вставляют
  в поиск карты галактики.
- Возврат в старт в конце обхода распознаётся как финиш, а не как начало.
- В верхнем оверлее на строке «ЗВЕЗДА … · тел N» — золотая ✔, если систему
  открыли вы.

Версия 1.8.0. Тесты: 324 passed."""

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
