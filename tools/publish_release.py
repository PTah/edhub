# Created by nc.ai 1.2.15 on Papasha 2026-11-15 11:23:52
import subprocess
import sys

NOTES = """**Панель биосигналов**

- На планете показываются сигналы только того тела, где стоит командир (пешком, в SRV или на площадке) — раньше могла висеть сводка всей системы. Стоя на теле без биологии, панель скрывается.
- Цена теперь у каждого сигнала, под строками — «итого по планете»; общий итог системы и футфол остались в подвале.
- Хвост-цена в текстовом виде отделяется от имени (TUI, логи).

**Память и стабильность**

- Поиск носителя по координатам больше не поднимает поток с сетевым запросом каждые 200 мс при пустом ответе EDSM: ошибка ловится, повтор через 45 с.
- Версия сборки и версия программы сверяются при сборке — расхождение больше не ломает автообновление молча."""

ASSETS = [
    r"dist\EDHUD-portable-1.4.2.zip",
    r"dist\EDHUD-1.4.2-windows.zip",
    r"dist\EDHUD-Setup-1.4.2.exe",
]

cmd = ["gh", "release", "create", "v1.4.2", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.4.2", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
