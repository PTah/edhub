# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

NOTES = """**Carrier Management теперь реально приглушает панели**

- Открытие Carrier Management игра не отмечает в `Status.json` (`GuiFocus`
  остаётся 0), поэтому прошлая версия панели не приглушала — наоборот, они
  возвращались к обычной непрозрачности. Теперь открытые экраны ловятся и по
  треку `Music` из журнала: `FleetCarrier_Managment`, `GalaxyMap`, `SystemMap`,
  `Codex`, `Squadrons`, `GalacticPowers`, `MainMenu`, `Starport`.
- Итог: под Carrier Management, картой галактики/системы, кодексом,
  эскадрильями и сервисами станции верхний HUD и окно с биосигналами уходят в
  alpha 0.10 (почти невидимы). Вернулись в полёт (трек `Supercruise`,
  `Exploration`, `NoTrack`) — прозрачность из настроек возвращается.
- FSS и DSS по-прежнему не приглушаются: там карточка био и радар нужны.
- Трек сбрасывается на `LoadGame`/`Shutdown`, чтобы после выхода из игры панели
  не остались приглушёнными.
- Тесты: 247 passed (добавлены случаи по трекам и сброс состояния).

Версия 1.5.6."""

ASSETS = [
    r"dist\EDHUD-portable-1.5.6.zip",
    r"dist\EDHUD-1.5.6-windows.zip",
    r"dist\EDHUD-Setup-1.5.6.exe",
]

cmd = ["gh", "release", "create", "v1.5.6", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.5.6", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
