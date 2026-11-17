# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

VERSION = "1.8.3"

NOTES = """**1.8.3: предупреждение об exclusive fullscreen**

- Точный детект exclusive DirectX через `SHQueryUserNotificationState`
  (Borderless больше не даёт ложную подсказку).
- Один раз за сессию exclusive: balloon в трее + голос (если включён) —
  переключить Graphics → Display Mode → Borderless / Alt+Enter.
- Чекбокс предупреждения в настройках оверлея.

Версия 1.8.3."""

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
