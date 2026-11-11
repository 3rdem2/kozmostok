# -*- coding: utf-8 -*-
"""Islem gunlugu + vardiya oturumlari.

Kim ne zaman ne yapti: program acilis/kapanis, giris, ek kullanici
girisi, cikis, satis, iade, urun girisi. Vardiya oturumlari gunluk
giris/cikis saatlerini tutar.
"""

from __future__ import annotations

import threading
from datetime import datetime

from core.database import PG_MOD, get_connection
from core.logger import log_error

_kilit = threading.Lock()
_hazir = False

ISIMLER = {
    "acilis": "Program acilisi",
    "giris": "Giris",
    "ek_giris": "Ek kullanici girisi",
    "cikis": "Kullanici cikisi",
    "kapanis": "Program kapanisi",
    "satis": "Satis",
    "iade": "Iade",
    "urun_giris": "Yeni urun girisi",
    "stok_giris": "Stok girisi",
    "yedek": "Yedek",
}

_oturumlar: set = set()


def tablolari_hazirla() -> None:
    global _hazir
    with _kilit:
        if _hazir:
            return
        try:
            pk = "SERIAL PRIMARY KEY" if PG_MOD else "INTEGER PRIMARY KEY AUTOINCREMENT"
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS islem_gunlugu (
                    id              {pk},
                    kullanici       TEXT,
                    kullanici_id    INTEGER,
                    islem           TEXT NOT NULL,
                    detay           TEXT,
                    tarih           TEXT,
                    saat            TEXT
                )
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS vardiya_oturumlari (
                    id              {pk},
                    kullanici       TEXT,
                    kullanici_id    INTEGER,
                    giris_tarihi    TEXT,
                    giris_saati     TEXT,
                    cikis_tarihi    TEXT,
                    cikis_saati     TEXT
                )
            """)
            for sql in (
                "CREATE INDEX IF NOT EXISTS ix_islem_gunlugu_tarih ON islem_gunlugu (tarih)",
                "CREATE INDEX IF NOT EXISTS ix_vardiya_giris_tarih ON vardiya_oturumlari (giris_tarihi)",
            ):
                try:
                    cur.execute(sql)
                except Exception:
                    pass
            conn.commit()
            conn.close()
            _hazir = True
        except Exception as e:
            log_error("Islem gunlugu tablolari", e, __file__, "tablolari_hazirla")


def _simdi() -> tuple:
    n = datetime.now()
    return n.strftime("%Y-%m-%d"), n.strftime("%H:%M:%S")


def islem_kaydet(kullanici: str, islem: str, detay: str = "", kullanici_id=None) -> None:
    try:
        tablolari_hazirla()
        t, s = _simdi()
        conn = get_connection()
        conn.cursor().execute(
            "INSERT INTO islem_gunlugu (kullanici, kullanici_id, islem, detay, tarih, saat) "
            "VALUES (?,?,?,?,?,?)",
            ((kullanici or "-").strip(), kullanici_id, islem, (detay or "")[:400], t, s),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log_error("Islem kaydet", e, __file__, "islem_kaydet")


def vardiya_ac(kullanici: str, kullanici_id=None):
    try:
        tablolari_hazirla()
        t, s = _simdi()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO vardiya_oturumlari (kullanici, kullanici_id, giris_tarihi, giris_saati) "
            "VALUES (?,?,?,?)",
            ((kullanici or "-").strip(), kullanici_id, t, s),
        )
        oturum_id = cur.lastrowid
        conn.commit()
        conn.close()
        if oturum_id:
            with _kilit:
                _oturumlar.add(int(oturum_id))
        return int(oturum_id) if oturum_id else None
    except Exception as e:
        log_error("Vardiya ac", e, __file__, "vardiya_ac")
        return None


def vardiya_kapat_id(oturum_id) -> bool:
    if not oturum_id:
        return False
    try:
        tablolari_hazirla()
        t, s = _simdi()
        conn = get_connection()
        conn.cursor().execute(
            "UPDATE vardiya_oturumlari SET cikis_tarihi=?, cikis_saati=? "
            "WHERE id=? AND cikis_saati IS NULL",
            (t, s, int(oturum_id)),
        )
        conn.commit()
        conn.close()
        with _kilit:
            _oturumlar.discard(int(oturum_id))
        return True
    except Exception as e:
        log_error("Vardiya kapat", e, __file__, "vardiya_kapat_id")
        return False


def vardiya_kapat_adi(kullanici: str) -> bool:
    try:
        tablolari_hazirla()
        t, s = _simdi()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM vardiya_oturumlari WHERE kullanici=? AND cikis_saati IS NULL "
            "ORDER BY id DESC",
            ((kullanici or "").strip(),),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return False
        oturum_id = row["id"]
        cur.execute(
            "UPDATE vardiya_oturumlari SET cikis_tarihi=?, cikis_saati=? WHERE id=?",
            (t, s, oturum_id),
        )
        conn.commit()
        conn.close()
        with _kilit:
            _oturumlar.discard(int(oturum_id))
        return True
    except Exception as e:
        log_error("Vardiya kapat", e, __file__, "vardiya_kapat_adi")
        return False


def aktif_kullanicilar(sadece_kasiyer: bool = False) -> list:
    try:
        tablolari_hazirla()
        conn = get_connection()
        cur = conn.cursor()
        sql = (
            "SELECT kullanici, giris_tarihi, giris_saati FROM vardiya_oturumlari "
            "WHERE cikis_saati IS NULL"
        )
        if sadece_kasiyer:
            sql += (
                " AND EXISTS (SELECT 1 FROM kullanicilar k "
                "WHERE k.kullanici_adi = vardiya_oturumlari.kullanici "
                "AND k.rol = 'kasiyer')"
            )
        sql += " ORDER BY id"
        cur.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error("Aktif kullanicilar", e, __file__, "aktif_kullanicilar")
        return []


def vardiya_listesi(gun: str) -> list:
    try:
        tablolari_hazirla()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT kullanici, giris_tarihi, giris_saati, cikis_tarihi, cikis_saati "
            "FROM vardiya_oturumlari WHERE giris_tarihi=? OR cikis_tarihi=? ORDER BY id",
            (gun, gun),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error("Vardiya listesi", e, __file__, "vardiya_listesi")
        return []


def hareketler(baslangic: str, bitis: str) -> list:
    try:
        tablolari_hazirla()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT tarih, saat, kullanici, islem, detay FROM islem_gunlugu "
            "WHERE tarih>=? AND tarih<=? ORDER BY id",
            (baslangic, bitis),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error("Hareketler", e, __file__, "hareketler")
        return []


def program_oturumlarini_kapat() -> None:
    with _kilit:
        ids = list(_oturumlar)
    for i in ids:
        vardiya_kapat_id(i)
