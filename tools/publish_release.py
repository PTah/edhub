# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

NOTES = """**1.7.5: во время прыжка из дашборда убирается ВСЯ био-часть, а не только список**

- В 1.7.3 прятался лишь блок «био в системе», а карточка текущего тела
  («БИО 7 (Aleoida Coronamus — Emerald, …)»), список организмов с ценами и
  строка «предсказание» продолжали висеть во время прыжка. Теперь при зарядке
  FSD в другую систему (и в самом прыжке) убирается всё перечисленное, а также
  «био ≈…» из строки сессии.
- Остальные данные никуда не деваются: маршрут, тело, расстояния, стоимость
  сканов/DSS, геология, DSS-статус, сводка сессии.
- Прыжок отменили — био-часть возвращается сразу.
- Тесты: 308 passed (скрытие карточки тела при зарядке, возврат при отмене,
  скрытие списка системы).

Версия 1.7.5."""

ASSETS = [
    r"dist\EDHUD-portable-1.7.5.zip",
    r"dist\EDHUD-1.7.5-windows.zip",
    r"dist\EDHUD-Setup-1.7.5.exe",
]

cmd = ["gh", "release", "create", "v1.7.5", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.7.5", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
