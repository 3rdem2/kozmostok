# -*- coding: utf-8 -*-
"""Veritabani ve rapor yedegi"""

import shutil
from datetime import datetime
from pathlib import Path
from core.database import BASE_DIR, DB_PATH
from core.logger import log_error, log_info

YEDEK_DIR = BASE_DIR / "yedekler"


def yedek_al(etiket: str = "manuel") -> tuple[bool, str]:
    try:
        from core.database import PG_MOD
        if PG_MOD:
            return False, (
                "PostgreSQL modunda dosya yedegi devre disi.\n"
                "Yedek icin: pg_dump -U postgres -d kozmostok -f yedek.sql"
            )
        YEDEK_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        klasor = YEDEK_DIR / f"{ts}_{etiket}"
        klasor.mkdir(parents=True, exist_ok=True)
        if DB_PATH.exists():
            shutil.copy2(DB_PATH, klasor / "kozmostok.db")
        # raporlar ozeti kopyalanmaz (buyuk olabilir); sadece db
        log_info(f"Yedek: {klasor}")
        return True, str(klasor)
    except Exception as e:
        log_error("Yedek hatasi", e, __file__, "yedek_al")
        return False, str(e)


def son_yedekler(limit: int = 10) -> list:
    try:
        if not YEDEK_DIR.exists():
            return []
        dirs = sorted([p for p in YEDEK_DIR.iterdir() if p.is_dir()], reverse=True)
        return [str(p) for p in dirs[:limit]]
    except Exception:
        return []
