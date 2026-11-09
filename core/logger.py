# -*- coding: utf-8 -*-
"""
Hata ve olay log sistemi.
Tum hatalar logs/hatalar.log dosyasina yazilir.
"""

import os
import traceback
from datetime import datetime
from pathlib import Path

# Proje kok dizini (pakette yazilabilir veri klasoru)
from core.yollar import BASE_DIR  # noqa: E402

LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "hatalar.log"

# Log klasoru yoksa olustur
LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_error(mesaj: str, exception: Exception | None = None, dosya: str = "", fonksiyon: str = ""):
    """
    Hata loglar.
    :param mesaj: Aciklama
    :param exception: Exception nesnesi (opsiyonel)
    :param dosya: Hatanin olustugu dosya
    :param fonksiyon: Hatanin olustugu fonksiyon
    """
    try:
        zaman = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        satirlar = [
            f"[{zaman}]",
            f"Dosya     : {dosya or 'Bilinmiyor'}",
            f"Fonksiyon : {fonksiyon or 'Bilinmiyor'}",
            f"Mesaj     : {mesaj}",
        ]

        if exception is not None:
            satirlar.append(f"Exception : {type(exception).__name__}: {str(exception)}")
            tb = traceback.format_exc()
            if tb and tb.strip() != "NoneType: None":
                satirlar.append("Traceback :")
                satirlar.append(tb)

        satirlar.append("-" * 60)

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n".join(satirlar) + "\n")

    except Exception as e:
        # Log yazarken bile hata olursa sessizce gec (donguye girmesin)
        print(f"[LOGGER HATA] Log yazilamadi: {e}")


def log_info(mesaj: str):
    """Bilgi amacli log."""
    try:
        zaman = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{zaman}] INFO: {mesaj}\n")
    except Exception:
        pass
