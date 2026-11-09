# -*- coding: utf-8 -*-
"""Uygulama yollari — kaynak (salt okunur) ve veri (yazilabilir) ayrimi.

Gelistirme modunda her ikisi de proje kokudur.
PyInstaller paketinde:
  KAYNAK_DIR = sys._MEIPASS        (assets, sablonlar, logo — salt okunur)
  BASE_DIR   = %LOCALAPPDATA%\\KozmoStok  (Windows)
               ~/Library/Application Support/KozmoStok (macOS)
               (exe yaninda portable.ini varsa exe klasoru)

KOZMOSTOK_VERI ortam degiskeni veri klasorunu zorlar.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def dondurulmus() -> bool:
    """PyInstaller ile paketlenmis mi?"""
    return bool(getattr(sys, "frozen", False))


if dondurulmus():
    APP_DIR = Path(sys.executable).resolve().parent
    KAYNAK_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)).resolve()
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    KAYNAK_DIR = APP_DIR


def _veri_koku() -> Path:
    ortam = os.getenv("KOZMOSTOK_VERI")
    if ortam:
        return Path(ortam).expanduser().resolve()
    if dondurulmus():
        if (APP_DIR / "portable.ini").exists():
            return APP_DIR
        if os.name == "nt":
            return Path(os.getenv("LOCALAPPDATA") or Path.home()) / "KozmoStok"
        return Path.home() / "Library" / "Application Support" / "KozmoStok"
    return APP_DIR


BASE_DIR = _veri_koku()
VARLIK_DIR = KAYNAK_DIR / "assets"

for _alt in ("logs", "db", "raporlar", "yedekler", "etiketler"):
    try:
        (BASE_DIR / _alt).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def varlik(*parcalar: str) -> Path:
    """Salt okunur kaynak dosyasi (assets/...)."""
    return VARLIK_DIR.joinpath(*parcalar)


def veri(*parcalar: str) -> Path:
    """Yazilabilir veri dosyasi (logs/, raporlar/, ...)."""
    return BASE_DIR.joinpath(*parcalar)
