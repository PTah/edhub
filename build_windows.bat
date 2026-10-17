@echo off
rem Сборка EDHUD для Windows 10/11.
rem Нужен Python 3.10+ (python.org, с tcl/tk).
rem Результат:
rem   dist\EDHUD-portable\EDHUD.exe     — один файл, копируешь и запускаешь
rem   dist\EDHUD-portable.zip           — то же в архиве
rem   dist\EDHUD\EDHUD.exe              — папка (быстрее старт; для установщика)
rem   dist\EDHUD-Setup-<ver>.exe        — установщик (если установлен Inno Setup 6)
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "VERSION=1.2.0"
for /f "usebackq tokens=*" %%V in (`python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])" 2^>nul`) do set "VERSION=%%V"

echo === EDHUD %VERSION% — сборка Windows ===
echo.

python -m pip install --upgrade --quiet pyinstaller || goto :err

if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist EDHUD.spec del /q EDHUD.spec
if exist EDHUD-portable.spec del /q EDHUD-portable.spec

rem Абсолютный путь: иначе --specpath/workpath ломают относительный data
set "DATA_SRC=%CD%\data"

rem --- 1) Portable: один exe (onefile) ---
echo [1/3] Portable standalone (onefile)...
python -m PyInstaller --noconfirm --clean --windowed --onefile --name EDHUD-portable ^
  --distpath dist\EDHUD-portable ^
  --workpath build\portable ^
  --specpath build ^
  --add-data "%DATA_SRC%;data" ^
  --hidden-import tkinter ^
  --exclude-module numpy ^
  --exclude-module pytest ^
  run.pyw || goto :err

if exist "dist\EDHUD-portable\EDHUD-portable.exe" (
  ren "dist\EDHUD-portable\EDHUD-portable.exe" EDHUD.exe
)

echo.
echo [2/3] Каталог для установщика (onedir)...
python -m PyInstaller --noconfirm --clean --windowed --onedir --name EDHUD ^
  --distpath dist ^
  --workpath build\onedir ^
  --specpath build ^
  --add-data "%DATA_SRC%;data" ^
  --hidden-import tkinter ^
  --exclude-module numpy ^
  --exclude-module pytest ^
  run.pyw || goto :err

echo.
echo Упаковка portable ZIP...
powershell -NoProfile -Command ^
  "Compress-Archive -Path 'dist\EDHUD-portable\*' -DestinationPath 'dist\EDHUD-portable-%VERSION%.zip' -Force" || goto :err
copy /y "dist\EDHUD-portable-%VERSION%.zip" "dist\EDHUD-portable.zip" >nul

echo.
echo [3/3] Установщик Inno Setup...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
where iscc >nul 2>&1 && for /f "delims=" %%I in ('where iscc') do set "ISCC=%%I"

if defined ISCC (
  "%ISCC%" "/DMyAppVersion=%VERSION%" "installer\edhud.iss" || goto :err
) else (
  echo Inno Setup 6 не найден — установщик .exe пропущен.
  echo Установите: https://jrsoftware.org/isdl.php
  echo Затем снова запустите build_windows.bat
  echo Или: winget install --id JRSoftware.InnoSetup -e
)

echo.
echo ========== Готово ==========
echo Portable:   "%CD%\dist\EDHUD-portable\EDHUD.exe"
echo ZIP:        "%CD%\dist\EDHUD-portable.zip"
echo Onedir:     "%CD%\dist\EDHUD\EDHUD.exe"
if exist "dist\EDHUD-Setup-%VERSION%.exe" (
  echo Installer:  "%CD%\dist\EDHUD-Setup-%VERSION%.exe"
)
echo.
echo На другом ПК Python не нужен. Журналы ED ищутся сами.
echo Настройки/кэш: %%LOCALAPPDATA%%\EliteDangerousHUD
goto :eof

:err
echo.
echo Сборка не удалась. Нужен Python с tkinter (python.org, галочка tcl/tk).
exit /b 1
