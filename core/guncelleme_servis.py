# -*- coding: utf-8 -*-
"""Surum bilgisi ve uygulama ici guncelleme.

Akis:
  1) Sunucudaki manifest JSON indirilir:
     {"surum": "1.0.1", "url": "https://.../KozmoStok-1.0.1-win.zip",
      "sha256": "...", "notlar": "..."}
  2) Surum yeniyse zip indirilir, sha256 dogrulanir, gecici klasore acilir.
  3) Yardimci betik uygulamayi kapatmayi bekler, dosyalari kopyalar, yeniden baslatir.

Manifest adresi: ayarlar.guncelleme_url veya config.ini [guncelleme] url
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from core.database import get_ayar
from core.logger import log_error, log_info
from core.yollar import APP_DIR, KAYNAK_DIR, dondurulmus

VARSAYILAN_SURUM = "1.0.0"
_ZAMAN_ASIMI = 30


def surum() -> str:
    """Paketle gelen surum.json varsa oradan, yoksa sabit surum."""
    for kok in (KAYNAK_DIR, APP_DIR):
        yol = kok / "surum.json"
        try:
            if yol.exists():
                with open(yol, "r", encoding="utf-8") as f:
                    return str(json.load(f).get("surum") or VARSAYILAN_SURUM)
        except Exception:
            continue
    return VARSAYILAN_SURUM


def surum_bilgi() -> dict:
    for kok in (KAYNAK_DIR, APP_DIR):
        yol = kok / "surum.json"
        try:
            if yol.exists():
                with open(yol, "r", encoding="utf-8") as f:
                    veri = json.load(f)
                veri.setdefault("surum", VARSAYILAN_SURUM)
                return veri
        except Exception:
            continue
    return {"surum": VARSAYILAN_SURUM}


def manifest_adresi() -> str:
    try:
        adres = (get_ayar("guncelleme_url", "") or "").strip()
    except Exception:
        adres = ""
    if adres:
        return adres
    try:
        from core.db_config import _ini

        return (_ini.get("guncelleme", "url", fallback="") or "").strip()
    except Exception:
        return ""


def _surum_parca(metin: str) -> tuple:
    parcalar = []
    for p in str(metin or "").replace("-", ".").split("."):
        try:
            parcalar.append(int("".join(ch for ch in p if ch.isdigit()) or 0))
        except Exception:
            parcalar.append(0)
    return tuple(parcalar)


def daha_yeni(yeni: str, mevcut: str) -> bool:
    return _surum_parca(yeni) > _surum_parca(mevcut)


def kontrol(adres: str | None = None) -> tuple[bool, str, dict]:
    """Manifesti okur. (ok, mesaj, bilgi)"""
    adres = (adres or manifest_adresi()).strip()
    if not adres:
        return False, "Guncelleme adresi tanimli degil (Sistem sekmesinden girin).", {}
    try:
        istek = urllib.request.Request(adres, headers={"User-Agent": "KozmoStok"})
        with urllib.request.urlopen(istek, timeout=_ZAMAN_ASIMI) as yanit:
            veri = json.loads(yanit.read().decode("utf-8"))
        if not isinstance(veri, dict) or not veri.get("surum"):
            return False, "Manifest bicimi gecersiz (surum alani yok).", {}
        mevcut = surum()
        veri["mevcut_surum"] = mevcut
        if daha_yeni(str(veri["surum"]), mevcut):
            return True, f"Yeni surum var: {veri['surum']} (kurulu: {mevcut})", veri
        return True, f"Program guncel (surum {mevcut}).", veri
    except Exception as e:
        log_error("Guncelleme kontrolu", e, __file__, "kontrol")
        return False, f"Guncelleme kontrol edilemedi: {e}", {}


def indir(bilgi: dict, hedef_klasor: Path | None = None) -> tuple[bool, str, str]:
    """Zip'i indirir ve sha256 dogrular."""
    url = str(bilgi.get("url") or "").strip()
    if not url:
        return False, "Manifestte indirme adresi (url) yok.", ""
    klasor = Path(hedef_klasor or tempfile.mkdtemp(prefix="kozmostok_guncelle_"))
    klasor.mkdir(parents=True, exist_ok=True)
    ad = url.split("?")[0].rstrip("/").split("/")[-1] or "guncelleme.zip"
    hedef = klasor / ad
    try:
        istek = urllib.request.Request(url, headers={"User-Agent": "KozmoStok"})
        with urllib.request.urlopen(istek, timeout=120) as yanit, open(hedef, "wb") as f:
            shutil.copyfileobj(yanit, f)
        beklenen = str(bilgi.get("sha256") or "").strip().lower()
        if beklenen:
            ozet = hashlib.sha256()
            with open(hedef, "rb") as f:
                for parca in iter(lambda: f.read(1024 * 256), b""):
                    ozet.update(parca)
            if ozet.hexdigest().lower() != beklenen:
                return False, "Indirilen dosyanin ozeti (sha256) uyusmuyor.", ""
        return True, f"Indirildi: {hedef.name}", str(hedef)
    except Exception as e:
        log_error("Guncelleme indirme", e, __file__, "indir")
        return False, f"Indirme basarisiz: {e}", ""


def hazirla(zip_yol: str) -> tuple[bool, str, str]:
    """Zip'i gecici klasore acar; icerik kokunu (tek ust dizin) dondurur."""
    try:
        hedef = Path(tempfile.mkdtemp(prefix="kozmostok_yeni_"))
        with zipfile.ZipFile(zip_yol) as z:
            z.extractall(hedef)
        girdiler = [p for p in hedef.iterdir() if p.name != "__MACOSX"]
        kok = girdiler[0] if len(girdiler) == 1 and girdiler[0].is_dir() else hedef
        return True, f"Arsiv acildi: {kok.name}", str(kok)
    except Exception as e:
        log_error("Guncelleme acma", e, __file__, "hazirla")
        return False, f"Arsiv acilamadi: {e}", ""


def _hedef_klasor() -> Path:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if exe.parent.name == "MacOS" and exe.parent.parent.name == "Contents":
            return exe.parent.parent.parent  # .app paketi
        return exe.parent
    return APP_DIR


def uygula(kaynak_klasor: str) -> tuple[bool, str]:
    """Yardimci betik yazar; uygulama kapaninca dosyalari degistirip yeniden acar."""
    if not dondurulmus():
        return False, "Guncelleme yalnizca paketlenmis surumde uygulanir."
    kaynak = Path(kaynak_klasor)
    if not kaynak.exists():
        return False, "Guncelleme klasoru bulunamadi."
    hedef = _hedef_klasor()
    pid = os.getpid()
    try:
        if os.name == "nt":
            betik = Path(tempfile.gettempdir()) / "kozmostok_guncelle.bat"
            exe = Path(sys.executable).resolve()
            betik.write_text(
                "@echo off\r\n"
                "chcp 65001 >nul\r\n"
                ":bekle\r\n"
                f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul && '
                "(timeout /t 1 /nobreak >nul & goto bekle)\r\n"
                f'robocopy "{kaynak}" "{hedef}" /MIR /NFL /NDL /NJH /NJS /NC /NS >nul\r\n'
                f'start "" "{exe}"\r\n'
                'del "%~f0"\r\n',
                encoding="utf-8",
            )
            subprocess.Popen(
                ["cmd", "/c", str(betik)],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                close_fds=True,
            )
        else:
            betik = Path(tempfile.gettempdir()) / "kozmostok_guncelle.sh"
            betik.write_text(
                "#!/bin/sh\n"
                f"while kill -0 {pid} 2>/dev/null; do sleep 1; done\n"
                f'rsync -a --delete "{kaynak}/" "{hedef}/"\n'
                f'open "{hedef}"\n'
                f'rm -rf "{kaynak}"\n'
                'rm -f "$0"\n',
                encoding="utf-8",
            )
            betik.chmod(0o755)
            subprocess.Popen(["/bin/sh", str(betik)], close_fds=True, start_new_session=True)
        log_info(f"Guncelleme baslatildi: {kaynak} -> {hedef}")
        return True, "Guncelleme uygulanacak. Program yeniden baslatiliyor..."
    except Exception as e:
        log_error("Guncelleme uygulama", e, __file__, "uygula")
        return False, f"Guncelleme baslatilamadi: {e}"
