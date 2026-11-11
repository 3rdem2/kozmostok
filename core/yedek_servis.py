# -*- coding: utf-8 -*-
"""Veritabani yedegi — gun klasorlu.

yedekler/YYYY-MM-DD/ klasorune gunde birden fazla yedek dosya olarak
birikir; her yedek icin yeni klasor olusmaz.
  SQLite  -> kozmostok_HHMMSS_etiket.db  (sqlite3 backup API, WAL guvenli)
  Postgre -> kozmostok_HHMMSS_etiket.json (tum tablolar JSON)
"""

import json
import shutil
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from core.database import BASE_DIR, DB_PATH, PG_MOD, get_connection
from core.log_servis import islem_kaydet
from core.logger import log_error, log_info

YEDEK_DIR = BASE_DIR / "yedekler"


def _gun_klasoru() -> Path:
    klasor = YEDEK_DIR / datetime.now().strftime("%Y-%m-%d")
    klasor.mkdir(parents=True, exist_ok=True)
    return klasor


def _dosya_adi(ts: str, etiket: str, uzanti: str) -> str:
    return f"kozmostok_{ts}_{etiket}.{uzanti}"


def _sqlite_yedek(hedef: Path) -> None:
    src = sqlite3.connect(str(DB_PATH))
    dst = sqlite3.connect(str(hedef))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _pg_yedek(hedef: Path) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
        )
        tablolar = [r["table_name"] for r in cur.fetchall()]
        dump = {}
        for t in tablolar:
            try:
                cur.execute(f"SELECT * FROM {t}")
                dump[t] = cur.fetchall()
            except Exception as e:
                log_error(f"Yedek tablo: {t}", e, __file__, "_pg_yedek")
                dump[t] = []
        with open(hedef, "w", encoding="utf-8") as f:
            json.dump(dump, f, default=str, ensure_ascii=False)
    finally:
        conn.close()


def yedek_al(etiket: str = "manuel") -> tuple:
    try:
        klasor = _gun_klasoru()
        ts = datetime.now().strftime("%H%M%S")
        if PG_MOD:
            hedef = klasor / _dosya_adi(ts, etiket, "json")
            _pg_yedek(hedef)
        else:
            if not DB_PATH.exists():
                return False, f"DB yok: {DB_PATH}"
            hedef = klasor / _dosya_adi(ts, etiket, "db")
            try:
                _sqlite_yedek(hedef)
            except Exception:
                shutil.copy2(DB_PATH, hedef)
        log_info(f"Yedek: {hedef}")
        islem_kaydet("-", "yedek", str(hedef.name))
        return True, str(hedef)
    except Exception as e:
        log_error("Yedek hatasi", e, __file__, "yedek_al")
        return False, str(e)


def yedek_arkaplan(etiket: str = "otomatik") -> None:
    """UI kilitlemeden arka planda yedek alir."""
    threading.Thread(target=yedek_al, args=(etiket,), daemon=True).start()


def son_yedekler(limit: int = 14) -> list:
    try:
        if not YEDEK_DIR.exists():
            return []
        dosyalar = sorted(
            [p for p in YEDEK_DIR.glob("*/*") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return [str(p) for p in dosyalar[:limit]]
    except Exception:
        return []
