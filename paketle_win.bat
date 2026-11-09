@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [1/3] Bagimliliklar kuruluyor...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || goto :hata

echo [2/3] Derleniyor...
python -m PyInstaller --noconfirm --clean KozmoStok.spec || goto :hata

echo [3/3] Paketleniyor...
if exist "KozmoStok-win.zip" del /q "KozmoStok-win.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\KozmoStok\*' -DestinationPath 'KozmoStok-win.zip' -Force" || goto :hata

echo.
echo Tamam: dist\KozmoStok\KozmoStok.exe
echo Zip  : KozmoStok-win.zip
exit /b 0

:hata
echo.
echo DERLEME BASARISIZ. Yukaridaki hatalari kontrol edin.
exit /b 1
