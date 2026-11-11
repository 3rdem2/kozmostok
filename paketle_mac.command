#!/bin/bash
# KozmoStok - macOS paketleme. Finder'da cift tiklayarak calistirilir.
# Terminal acilir; derleme bitince dist klasoru Finder'da acilir.
set -u
cd "$(dirname "$0")" || exit 1

echo "=============================================="
echo " KozmoStok - macOS paketleme"
echo " Klasor: $(pwd)"
echo "=============================================="
echo

# Indirilen zip'lerde takilmamasi icin karantina isaretini temizle.
xattr -dr com.apple.quarantine "$(pwd)" 2>/dev/null || true

if ! command -v python3 >/dev/null 2>&1; then
  echo "HATA: python3 bulunamadi."
  echo
  echo "1) https://www.python.org/downloads/macos/ adresinden Python 3.12 kurun"
  echo "2) Bu pencereyi kapatip dosyaya yeniden cift tiklayin"
  echo
  read -n 1 -s -r -p "Kapatmak icin bir tusa basin..."
  exit 1
fi

echo "Python: $(python3 --version 2>&1)"
echo

if [ ! -d ".venv-mac" ]; then
  echo "[1/4] Sanal ortam olusturuluyor..."
  python3 -m venv .venv-mac || {
    echo "HATA: sanal ortam olusturulamadi."
    read -n 1 -s -r -p "Kapatmak icin bir tusa basin..."
    exit 1
  }
else
  echo "[1/4] Sanal ortam hazir (.venv-mac)"
fi
# shellcheck disable=SC1091
. .venv-mac/bin/activate

echo "[2/4] Bagimliliklar kuruluyor (ilk calistirmada 2-4 dakika)..."
python -m pip install --upgrade pip >/dev/null 2>&1 || true
python -m pip install -r requirements.txt pyinstaller || {
  echo "HATA: bagimliliklar kurulamadi. Internet baglantisini kontrol edin."
  read -n 1 -s -r -p "Kapatmak icin bir tusa basin..."
  exit 1
}

echo "[3/4] Derleniyor..."
rm -rf build dist
python -m PyInstaller --noconfirm --clean KozmoStok.spec || {
  echo "HATA: derleme basarisiz. Yukaridaki satirlari gelistiriciye gonderin."
  read -n 1 -s -r -p "Kapatmak icin bir tusa basin..."
  exit 1
}

if [ ! -d "dist/KozmoStok.app" ]; then
  echo "HATA: dist/KozmoStok.app olusmadi."
  read -n 1 -s -r -p "Kapatmak icin bir tusa basin..."
  exit 1
fi

echo "[4/4] Imzalaniyor ve paketleniyor..."
codesign --force --deep --sign - dist/KozmoStok.app || true
codesign --verify --deep --strict dist/KozmoStok.app 2>/dev/null && echo "Imza dogrulandi." || echo "UYARI: imza dogrulanamadi (ad-hoc)."

cd dist || exit 1
rm -f KozmoStok-mac.zip KozmoStok-mac.zip.sha256 KozmoStok-mac.dmg KozmoStok-mac.dmg.sha256
ditto -c -k --sequesterRsrc --keepParent KozmoStok.app KozmoStok-mac.zip
shasum -a 256 KozmoStok-mac.zip > KozmoStok-mac.zip.sha256
hdiutil create -volname KozmoStok -srcfolder KozmoStok.app -ov -format UDZO KozmoStok-mac.dmg >/dev/null
shasum -a 256 KozmoStok-mac.dmg > KozmoStok-mac.dmg.sha256
cd ..

echo
echo "=============================================="
echo " TAMAM"
echo " Uygulama : dist/KozmoStok.app"
echo " Zip      : dist/KozmoStok-mac.zip"
echo " DMG      : dist/KozmoStok-mac.dmg"
echo "=============================================="
cat dist/KozmoStok-mac.zip.sha256 dist/KozmoStok-mac.dmg.sha256
echo
echo "Kurulum: DMG'yi acin, KozmoStok.app'i Applications'a surukleyin."
echo "Ilk acilis: uygulamaya sag tik -> Ac -> Ac."
echo
open dist 2>/dev/null || true
read -n 1 -s -r -p "Kapatmak icin bir tusa basin..."
