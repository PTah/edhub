# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

NOTES = """**1.7.7: галочка «Показывать маршрут и статистику» для верхнего HUD**

- Настройки → «Окна» → оверлей: новый чекбокс **«Показывать маршрут и
  статистику»**. По умолчанию включён — дашборд выглядит как сейчас (маршрут,
  карриер, система + блок скана и сессии).
- Выключили — в дашборде остаются только маршрут с карриером и текущая
  система/тело: без образцов, стоимости скана, био, предсказания, строки системы
  и сессии. Удобно, когда нужен компактный «навигационный» оверлей.
- Переключается без перезапуска (Сохранить в настройках — и следующий кадр уже
  с новым видом), настройка живёт в `config.json` (`hud_show_stats`).
- Тесты: 317 passed (вид по умолчанию и компактный режим).

Версия 1.7.7."""

ASSETS = [
    r"dist\EDHUD-portable-1.7.7.zip",
    r"dist\EDHUD-1.7.7-windows.zip",
    r"dist\EDHUD-Setup-1.7.7.exe",
]

cmd = ["gh", "release", "create", "v1.7.7", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.7.7", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
