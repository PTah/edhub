@echo off
rem Сборка EDHUD.exe (Windows 10/11). Нужен Python 3.10+ (python.org, с tcl/tk).
rem Результат: dist\EDHUD.exe — можно положить ярлык в shell:startup.
setlocal
cd /d "%~dp0"

python -m pip install --upgrade --quiet pyinstaller || goto :err

python -m PyInstaller --noconfirm --clean --windowed --name EDHUD ^
  --add-data "data;data" ^
  --hidden-import tkinter ^
  --exclude-module numpy ^
  run.pyw || goto :err

echo.
echo Готово: "%CD%\dist\EDHUD.exe"
echo Для HUD в консоли собирайте без --windowed (см. README).
goto :eof

:err
echo.
echo Сборка не удалась. Проверьте, что установлен Python с tkinter.
exit /b 1
