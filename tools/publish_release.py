# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

VERSION = "1.8.2"

NOTES = """**1.8.2: расстояние до карриера после прыжка показывается всегда**

- После прыжка карриера в журнале нет координат новой системы, и они искались
  в EDSM/Spansh. Если туда никто не долетал, в шапке вечно висело «ищем ly…».
- Теперь расстояние показывается сразу — как **«≈ N ly»**: координаты берутся из
  самого адреса системы (id64 кодирует положение; точность до размера «коробки»,
  для масс-кода b — около ±17 ly). Как только EDSM/Spansh/журнал дадут точные
  координаты, «≈» пропадает и число уточняется.
- Приблизительное расстояние работает и без сети.

Версия 1.8.2. Тесты: 343 passed."""

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
