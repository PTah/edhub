# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

NOTES = """**1.7.9: настройки оверлея переехали в «Окна» → «Верхний оверлей»**

- Блок «Оверлей» с вкладки «Общее» (галочки «Показывать маршрут и статистику»,
  сквозные клики, метки поясов, чужое био, ширина) теперь внутри блока
  **«Верхний оверлей»** на вкладке «Окна» — рядом с его положением X/Y и
  прозрачностью. Всё про одну панель в одном месте.
- На вкладке «Общее» остались журналы, сеть, EDSM/Spansh/EDDN, ключи и голос.
- Поведение галочек не изменилось: значения те же, `config.json` читается как
  раньше, «Показывать маршрут и статистику» по-прежнему включена по умолчанию.
- README обновлён.

Версия 1.7.9. Тесты: 321 passed."""

ASSETS = [
    r"dist\EDHUD-portable-1.7.9.zip",
    r"dist\EDHUD-1.7.9-windows.zip",
    r"dist\EDHUD-Setup-1.7.9.exe",
]

cmd = ["gh", "release", "create", "v1.7.9", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.7.9", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
