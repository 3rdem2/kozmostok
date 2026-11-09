#!/bin/sh
# macOS paketleme — yalnizca macOS uzerinde calisir (PyInstaller capraz derleme yapmaz).
set -e
cd "$(dirname "$0")"

echo "[1/3] Bagimliliklar kuruluyor..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt pyinstaller

echo "[2/3] Derleniyor..."
python3 -m PyInstaller --noconfirm --clean KozmoStok.spec

echo "[3/3] Imzalaniyor ve paketleniyor..."
codesign --force --deep --sign - dist/KozmoStok.app
cd dist
rm -f KozmoStok-mac.zip KozmoStok-mac.dmg
ditto -c -k --sequesterRsrc --keepParent KozmoStok.app KozmoStok-mac.zip
shasum -a 256 KozmoStok-mac.zip > KozmoStok-mac.zip.sha256
hdiutil create -volname KozmoStok -srcfolder KozmoStok.app -ov -format UDZO KozmoStok-mac.dmg
shasum -a 256 KozmoStok-mac.dmg > KozmoStok-mac.dmg.sha256

echo
echo "Tamam: dist/KozmoStok.app"
echo "Zip  : dist/KozmoStok-mac.zip"
echo "DMG  : dist/KozmoStok-mac.dmg"
