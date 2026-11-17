# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

VERSION = "1.8.1"

NOTES = """**1.8.1: колонка «Тела» маршрута берёт данные из вашего кэша; исправлен сбой на каждом прыжке**

- **Route → «Тела»**: для систем, где вы уже были, состав (звёзды/планеты)
  теперь берётся из вашего локального кэша систем и журнала, а не только из
  запроса EDSM «до визита». Раньше у ваших открытий оставалось устаревшее
  «нет в EDSM», пока кто-то не загрузит данные в EDSM.
- Флаг «открыл я» теперь сохраняется в кэше системы и переживает перезапуск.
- **Исправлено**: после каждого FSDJump/Location в журнале приложения писался
  `NameError: name 'event' is not defined` — хвост обработчика события по ошибке
  попал в загрузку Canonn. Из-за этого не срабатывали сохранение системы по
  флагу и копирование следующей системы в буфер («Маршрут по шару»).
- **EDDN-отправка**: ответ 400/413/426 больше не вешает очередь на повторы
  каждые 60 секунд — сообщение отбрасывается, как требует EDDN.
- Заметка: INARA сейчас отвечает «This application has no access allowed» —
  для отправки travel-лога приложение EDHUD должно быть зарегистрировано на INARA.

Версия 1.8.1. Тесты: 341 passed."""

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
