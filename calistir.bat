@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title bt-tray

REM Smart App Control imzasiz exe leri engelledigi icin bt-tray i
REM dogrudan Python ile calistiran yardimci betik.

set "PY="
py -3 --version >/dev/null 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >/dev/null 2>&1 && set "PY=python"
)
if not defined PY (
    echo [HATA] Python bulunamadi.
    echo.
    echo Microsoft Store dan Python kur, sonra bu dosyayi tekrar calistir.
    echo Store imzali paket sundugu icin Smart App Control engellemez.
    start "" "ms-windows-store://search?query=Python"
    pause
    exit /b 1
)

echo Python bulundu: %PY%
echo Bagimliliklar kuruluyor (pystray, pillow)...
%PY% -m pip install --quiet --upgrade --user pystray pillow
if errorlevel 1 (
    echo [HATA] pip kurulumu basarisiz oldu.
    pause
    exit /b 1
)

REM Konsol penceresi acilmasin diye pythonw.exe yolunu Python a sorduruyoruz.
set "PYW="
for /f "usebackq delims=" %%i in (`%PY% -c "import os,sys; p=os.path.join(os.path.dirname(sys.executable),'pythonw.exe'); print(p if os.path.exists(p) else sys.executable)"`) do set "PYW=%%i"
if not defined PYW set "PYW=%PY%"

echo bt-tray baslatiliyor. Yonetici izni istenecek.
start "" "%PYW%" "%~dp0bt_tray.py"
exit /b 0
