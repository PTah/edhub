# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

NOTES = """**Панели уходят в прозрачность под меню игры**

- Открыли меню в игре — карту галактики/системы, орререри, сервисы станции,
  управление авианосцем (Carrier Management), панель связи, роль-панель —
  верхний дашборд и окно с биосигналами становятся почти невидимыми (alpha 0.10):
  карту и менюшки игры больше ничего не загораживает.
- Вернулись в полёт — прозрачность возвращается к значениям из настроек.
- Исключение: FSS и DSS/SAA. Там карточка био и радар как раз нужны на экране,
  эти панели не приглушаются.
- Приглушение работает вместе с прежним поведением: на станции/авианосце
  HUD полностью прозрачен, а окно био скрыто.

Версия 1.5.3. Тесты: 227 passed."""

ASSETS = [
    r"dist\EDHUD-portable-1.5.3.zip",
    r"dist\EDHUD-1.5.3-windows.zip",
    r"dist\EDHUD-Setup-1.5.3.exe",
]

cmd = ["gh", "release", "create", "v1.5.3", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.5.3", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
