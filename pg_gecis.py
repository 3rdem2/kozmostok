# -*- coding: utf-8 -*-
"""
SQLite verisini PostgreSQL'e tasir (tek gecis, id degerleri korunur).

Kullanim:
    1) PostgreSQL kurulu ve calisiyor olmali (varsayilan: localhost:5432)
    2) Baglanti bilgileri ortam degiskenlerinden veya core/db_config.py okunur:
       PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASS
    3) python pg_gecis.py

Betik su islemleri yapar:
    - PostgreSQL'de tablolari olusturur (yoksa)
    - Mevcut PostgreSQL verilerini siler (TRUNCATE) ve SQLite verisini kopyalar
    - id sayacilarini (sequence) kaynak verinin en buyuk id'sine ayarlar
"""
import os
import sqlite3
import sys

os.environ["DB_MODE"] = "postgres"

from pathlib import Path

import psycopg2

from core.db_config import POSTGRES
from core.database import init_database
from core.logger import log_error, log_info

SQLITE_YOL = Path(__file__).parent / "db" / "kozmostok.db"

TABLOLAR = [
    ("ayarlar", ["anahtar", "deger"]),
    ("kategoriler", ["id", "ad", "slug", "olusturma"]),
    ("urunler", [
        "id", "stok_kodu", "barkod", "ad", "kategori_id", "marka", "beden", "renk",
        "alis_fiyati", "satis_fiyati", "stok_adedi", "kritik_stok", "aciklama",
        "aktif", "olusturma", "guncelleme", "etsy_stok", "trendyol_stok", "wix_stok",
        "gorsel_yolu", "wix_yayin", "etsy_yayin", "trendyol_yayin", "parent_id", "kod_hazir",
    ]),
    ("satislar", [
        "id", "urun_id", "adet", "birim_fiyat", "indirim", "odeme_tipi", "toplam",
        "satis_tarihi", "satis_saati", "fis_no", "banka",
    ]),
    ("masraflar", ["id", "tutar", "aciklama", "masraf_tarihi", "olusturma"]),
    ("stok_hareketleri", ["id", "urun_id", "hareket_tipi", "adet", "aciklama", "tarih"]),
    ("kullanicilar", ["id", "kullanici_adi", "sifre_hash", "rol", "aktif", "olusturma", "email"]),
    ("sayim_oturum", ["id", "ad", "durum", "olusturma", "kapanis"]),
    ("sayim_satir", ["id", "oturum_id", "urun_id", "sistem_stok", "sayilan_stok", "fark"]),
]

SERIAL_TABLOLAR = [
    "kategoriler", "urunler", "satislar", "masraflar",
    "stok_hareketleri", "kullanicilar", "sayim_oturum", "sayim_satir",
]


def sqlite_baglan():
    if not SQLITE_YOL.exists():
        raise SystemExit(f"SQLite dosyasi bulunamadi: {SQLITE_YOL}")
    conn = sqlite3.connect(str(SQLITE_YOL))
    conn.row_factory = sqlite3.Row
    return conn


def pg_baglan():
    return psycopg2.connect(
        host=POSTGRES.get("host", "127.0.0.1"),
        port=int(POSTGRES.get("port", 5432)),
        dbname=POSTGRES.get("dbname", "kozmostok"),
        user=POSTGRES.get("user", "postgres"),
        password=POSTGRES.get("password", ""),
        connect_timeout=10,
    )


def pg_db_olustur():
    """kozmostok veritabani yoksa olusturur (bakim db'si 'postgres' uzerinden)."""
    conn = psycopg2.connect(
        host=POSTGRES.get("host", "127.0.0.1"),
        port=int(POSTGRES.get("port", 5432)),
        dbname="postgres",
        user=POSTGRES.get("user", "postgres"),
        password=POSTGRES.get("password", ""),
        connect_timeout=10,
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (POSTGRES.get("dbname"),))
    if not cur.fetchone():
        cur.execute(f'CREATE DATABASE "{POSTGRES.get("dbname")}" ENCODING \'UTF8\'')
        print(f"   Veritabani olusturuldu: {POSTGRES.get('dbname')}")
    cur.close()
    conn.close()


def aktarma():
    if not SQLITE_YOL.exists():
        raise SystemExit(f"SQLite dosyasi bulunamadi: {SQLITE_YOL}")
    print("0/4 Veritabani kontrol ediliyor...")
    try:
        pg_db_olustur()
    except psycopg2.OperationalError as e:
        raise SystemExit(
            "PostgreSQL baglantisi kurulamadi. Sunucu kurulu ve calisiyor mu?\n"
            f"Hata: {e}"
        )
    print("1/4 Tablolar olusturuluyor (PostgreSQL)...")
    if not init_database():
        raise SystemExit("PostgreSQL tablolari olusturulamadi. Baglanti bilgilerini kontrol edin.")

    sq = sqlite_baglan()
    pg = pg_baglan()
    pcur = pg.cursor()

    print("2/4 Hedef tablolar bosaltiliyor...")
    for ad, _ in reversed(TABLOLAR):
        pcur.execute(f"TRUNCATE TABLE {ad} RESTART IDENTITY CASCADE")

    print("3/4 Veriler kopyalaniyor...")
    ozet = {}
    for ad, kolonlar in TABLOLAR:
        info = sq.execute(f"PRAGMA table_info({ad})").fetchall()
        kaynak_kolonlar = [r[1] for r in info]
        kullan = [k for k in kolonlar if k in kaynak_kolonlar]
        rows = sq.execute(f"SELECT {', '.join(kullan)} FROM {ad}").fetchall()
        if rows:
            yer_tut = ", ".join(["%s"] * len(kullan))
            sql = f"INSERT INTO {ad} ({', '.join(kullan)}) VALUES ({yer_tut})"
            pcur.executemany(sql, [tuple(r) for r in rows])
        ozet[ad] = len(rows)
        print(f"   {ad}: {len(rows)} satir")

    print("4/4 id sayacilari ayarlaniyor...")
    for ad in SERIAL_TABLOLAR:
        pcur.execute(
            "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
            "COALESCE((SELECT MAX(id) FROM " + ad + "), 0) + 1, false)",
            (ad,),
        )

    pg.commit()
    pcur.close()
    pg.close()
    sq.close()

    print("\nGecis tamamlandi:")
    for ad, n in ozet.items():
        print(f"   {ad}: {n} satir")
    print("\nArtik programi 'baslat_kozmostok.cmd' ile (DB_MODE=postgres) calistirin.")
    log_info(f"SQLite -> PostgreSQL gecisi tamam: {ozet}")


if __name__ == "__main__":
    try:
        aktarma()
    except psycopg2.OperationalError as e:
        print("\nPostgreSQL baglantisi kurulamadi:", e)
        print("pg_gecis.py yerine: PostgreSQL kurulu mu? PG_HOST/PG_PORT/PG_DB/PG_USER/PG_PASS dogru mu?")
        sys.exit(1)
    except Exception as e:
        log_error("PG gecis", e, __file__, "aktarma")
        print("\nGecis hatasi:", e)
        sys.exit(1)
