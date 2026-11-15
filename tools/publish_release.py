# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 15:28:45
import subprocess
import sys

NOTES = """**Прозрачность на станции и авианосце**

- Сели на станцию или авианосец — верхний HUD уходит в полную прозрачность,
  боковое окно с биоматериалами скрывается. На станции и на авианосце они
  только мешают.
- Снятие с дока возвращает обычную прозрачность из настроек; «планетное»
  приглушение в атмосфере продолжает работать как раньше.
- Скрытая панель не перехватывает клики.

Версия 1.5.2. Тесты: 223 passed."""

ASSETS = [
    r"dist\EDHUD-portable-1.5.2.zip",
    r"dist\EDHUD-1.5.2-windows.zip",
    r"dist\EDHUD-Setup-1.5.2.exe",
]

cmd = ["gh", "release", "create", "v1.5.2", *ASSETS, "--repo", "PTah/edhub",
       "--title", "EDHUD 1.5.2", "--notes", NOTES]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit:", result.returncode)
print(result.stdout.strip())
print(result.stderr.strip())
sys.exit(result.returncode)
