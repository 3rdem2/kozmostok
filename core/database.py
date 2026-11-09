# -*- coding: utf-8 -*-
"""
Veritabani yonetimi — SQLite (varsayilan) veya PostgreSQL (DB_MODE=postgres).
Hangi motorun kullanilacagi core/db_config.py ve DB_MODE ortam degiskeni ile secilir.
"""

import re
import sqlite3
import threading
from pathlib import Path
from datetime import datetime
from core.db_config import DB_MODE, POSTGRES
from core.logger import log_error, log_info, BASE_DIR

DB_PATH = BASE_DIR / "db" / "kozmostok.db"
PG_MOD = str(DB_MODE or "sqlite").lower().startswith("postgres")

# Sema surumu: DDL degistikce artirilir. Ayni surumde acilis DDL'i atlanir.
SEMA_SURUM = "4"

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:  # psycopg2 kurulu degilse SQLite modu calismaya devam eder
    psycopg2 = None
    RealDictCursor = None


def get_connection(timeout: float = 30.0):
    """
    Veritabani baglantisi.
    DB_MODE=postgres -> PostgreSQL baglantisi, aksi halde SQLite (WAL).
    timeout: kilitte bekleme (sn)
    """
    if PG_MOD:
        return _pg_baglanti(timeout)
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(DB_PATH),
            timeout=timeout,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)}")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA temp_store = MEMORY")
        return conn
    except Exception as e:
        log_error("Veritabani baglantisi kurulamadi", e, __file__, "get_connection")
        raise


def db_baglanti_ayarla():
    """Acilista baglantiyi dogrular (WAL / SELECT 1)."""
    try:
        conn = get_connection()
        if PG_MOD:
            conn.cursor().execute("SELECT 1").fetchone()
            conn.close()
            log_info(f"DB hazir (PostgreSQL): {POSTGRES.get('dbname')}@{POSTGRES.get('host')}")
        else:
            jm = conn.execute("PRAGMA journal_mode").fetchone()
            conn.close()
            log_info(f"DB hazir (SQLite WAL): {DB_PATH} journal={jm[0] if jm else '?'}")
        return True
    except Exception as e:
        log_error("DB ayar", e, __file__, "db_baglanti_ayarla")
        return False


def _sema_hazir(conn) -> bool:
    """ayarlar.sema_surum guncel surumle ayni mi?"""
    try:
        cur = conn.cursor()
        cur.execute("SELECT deger FROM ayarlar WHERE anahtar = 'sema_surum'")
        row = cur.fetchone()
        if not row:
            return False
        deger = row.get("deger") if isinstance(row, dict) else row[0]
        return str(deger) == SEMA_SURUM
    except Exception:
        return False


def _sema_isaretle(conn) -> None:
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM ayarlar WHERE anahtar = 'sema_surum'")
        cur.execute(
            "INSERT INTO ayarlar (anahtar, deger) VALUES ('sema_surum', ?)",
            (SEMA_SURUM,),
        )
    except Exception as e:
        log_error("Sema surum isareti", e, __file__, "_sema_isaretle")


def _indeksler(conn) -> None:
    """Sik kullanilan sorgular icin indeksler (varsa atlanir)."""
    for sql in (
        "CREATE INDEX IF NOT EXISTS ix_urunler_stok_kodu ON urunler (stok_kodu)",
        "CREATE INDEX IF NOT EXISTS ix_urunler_barkod ON urunler (barkod)",
        "CREATE INDEX IF NOT EXISTS ix_satislar_tarih ON satislar (satis_tarihi)",
        "CREATE INDEX IF NOT EXISTS ix_hareket_urun ON stok_hareketleri (urun_id)",
        "CREATE INDEX IF NOT EXISTS ix_sayim_satir_oturum ON sayim_satir (oturum_id)",
        "CREATE INDEX IF NOT EXISTS ix_sayim_satir_urun ON sayim_satir (urun_id)",
    ):
        try:
            conn.cursor().execute(sql)
        except Exception:
            pass


def init_database():
    """Tum tablolari olusturur (SQLite veya PostgreSQL)."""
    if PG_MOD:
        return _init_postgres()
    try:
        conn = get_connection()
        if _sema_hazir(conn):
            conn.close()
            return True
        cur = conn.cursor()

        # Ayarlar
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ayarlar (
                anahtar TEXT PRIMARY KEY,
                deger   TEXT NOT NULL
            )
        """)

        # Varsayilan PIN
        cur.execute("""
            INSERT OR IGNORE INTO ayarlar (anahtar, deger)
            VALUES ('yonetim_pin', '2468')
        """)
        cur.execute("""
            INSERT OR IGNORE INTO ayarlar (anahtar, deger)
            VALUES ('magaza_adi', 'KOZMOSIZE')
        """)
        cur.execute("""
            INSERT OR IGNORE INTO ayarlar (anahtar, deger)
            VALUES ('son_stok_sira', '0')
        """)

        # Kategoriler
        cur.execute("""
            CREATE TABLE IF NOT EXISTS kategoriler (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ad          TEXT NOT NULL UNIQUE,
                slug        TEXT,
                olusturma   TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # Urunler
        cur.execute("""
            CREATE TABLE IF NOT EXISTS urunler (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                stok_kodu       TEXT NOT NULL UNIQUE,   -- Wix SKU veya otomatik
                barkod          TEXT UNIQUE,             -- KZM-AAYYSSS formati
                ad              TEXT NOT NULL,
                kategori_id     INTEGER,
                marka           TEXT,
                beden           TEXT,
                renk            TEXT,
                alis_fiyati     REAL DEFAULT 0,
                satis_fiyati    REAL DEFAULT 0,
                stok_adedi      INTEGER DEFAULT 0,
                kritik_stok     INTEGER DEFAULT 3,
                aciklama        TEXT,
                aktif           INTEGER DEFAULT 1,
                olusturma       TEXT DEFAULT (datetime('now','localtime')),
                guncelleme      TEXT,
                FOREIGN KEY (kategori_id) REFERENCES kategoriler(id)
            )
        """)

        # Satislar
        cur.execute("""
            CREATE TABLE IF NOT EXISTS satislar (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                urun_id         INTEGER NOT NULL,
                adet            INTEGER NOT NULL,
                birim_fiyat     REAL NOT NULL,
                indirim         REAL DEFAULT 0,
                odeme_tipi      TEXT NOT NULL,          -- nakit / kart
                toplam          REAL NOT NULL,
                satis_tarihi    TEXT DEFAULT (date('now','localtime')),
                satis_saati     TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (urun_id) REFERENCES urunler(id)
            )
        """)

        # Masraflar
        cur.execute("""
            CREATE TABLE IF NOT EXISTS masraflar (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tutar           REAL NOT NULL,
                aciklama        TEXT NOT NULL,
                masraf_tarihi   TEXT DEFAULT (date('now','localtime')),
                olusturma       TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # Stok hareketleri (giris / cikis / duzeltme)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stok_hareketleri (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                urun_id         INTEGER NOT NULL,
                hareket_tipi    TEXT NOT NULL,          -- giris / cikis / duzeltme / satis
                adet            INTEGER NOT NULL,
                aciklama        TEXT,
                tarih           TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (urun_id) REFERENCES urunler(id)
            )
        """)

        # Kanal stoklari (Etsy / Trendyol) - API sonrasi senkron icin
        for col in ("etsy_stok", "trendyol_stok", "wix_stok"):
            try:
                cur.execute(f"ALTER TABLE urunler ADD COLUMN {col} INTEGER DEFAULT 0")
            except Exception:
                pass  # kolon zaten var

        # Urun gorseli
        try:
            cur.execute("ALTER TABLE urunler ADD COLUMN gorsel_yolu TEXT")
        except Exception:
            pass

        # Kanal vitrin: adet 0 olsa bile kanalda listede kalsin (yayin=1)
        for col in ("wix_yayin", "etsy_yayin", "trendyol_yayin"):
            try:
                cur.execute(f"ALTER TABLE urunler ADD COLUMN {col} INTEGER DEFAULT 0")
            except Exception:
                pass

        # Varyant baglantisi
        try:
            cur.execute("ALTER TABLE urunler ADD COLUMN parent_id INTEGER")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE urunler ADD COLUMN kod_hazir INTEGER DEFAULT 1")
        except Exception:
            pass
        # Mevcut kanal adedi > 0 olanlari yayinda isaretle
        try:
            cur.execute("UPDATE urunler SET wix_yayin = 1 WHERE COALESCE(wix_stok,0) > 0")
            cur.execute("UPDATE urunler SET etsy_yayin = 1 WHERE COALESCE(etsy_stok,0) > 0")
            cur.execute("UPDATE urunler SET trendyol_yayin = 1 WHERE COALESCE(trendyol_stok,0) > 0")
        except Exception:
            pass

        # Satis fisi (tek musteri birden fazla urun)
        try:
            cur.execute("ALTER TABLE satislar ADD COLUMN fis_no TEXT")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE satislar ADD COLUMN banka TEXT")
        except Exception:
            pass

        # Kullanicilar (yetki)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS kullanicilar (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                kullanici_adi   TEXT NOT NULL UNIQUE,
                sifre_hash      TEXT NOT NULL,
                rol             TEXT NOT NULL DEFAULT 'kasiyer',  -- kasiyer | yonetici
                aktif           INTEGER DEFAULT 1,
                olusturma       TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        # Varsayilan yonetici: admin / 2468  (PBKDF2 hash ile saklanir)
        cur.execute("SELECT COUNT(*) AS n FROM kullanicilar")
        if cur.fetchone()["n"] == 0:
            from core.guvenlik import sifre_hashle
            cur.execute(
                "INSERT INTO kullanicilar (kullanici_adi, sifre_hash, rol) VALUES (?, ?, ?)",
                ("admin", sifre_hashle("2468"), "yonetici"),
            )
            cur.execute(
                "INSERT INTO kullanicilar (kullanici_adi, sifre_hash, rol) VALUES (?, ?, ?)",
                ("kasa", sifre_hashle("1234"), "kasiyer"),
            )

        try:
            cur.execute("ALTER TABLE kullanicilar ADD COLUMN email TEXT")
        except Exception:
            pass

        # Kurtarma kodu + SMTP (manuel)
        cur.execute("""
            INSERT OR IGNORE INTO ayarlar (anahtar, deger)
            VALUES ('kurtarma_kodu', 'KOZMO-2026-RESET')
        """)
        for k, v in [
            ('smtp_host', ''),
            ('smtp_port', '587'),
            ('smtp_user', ''),
            ('smtp_pass', ''),
            ('smtp_from', ''),
        ]:
            cur.execute("INSERT OR IGNORE INTO ayarlar (anahtar, deger) VALUES (?, ?)", (k, v))

        # Sayim oturumlari
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sayim_oturum (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ad          TEXT,
                durum       TEXT DEFAULT 'acik',  -- acik | kapali
                olusturma   TEXT DEFAULT (datetime('now','localtime')),
                kapanis     TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sayim_satir (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                oturum_id       INTEGER NOT NULL,
                urun_id         INTEGER NOT NULL,
                sistem_stok     INTEGER NOT NULL,
                sayilan_stok    INTEGER,
                fark            INTEGER,
                FOREIGN KEY (oturum_id) REFERENCES sayim_oturum(id),
                FOREIGN KEY (urun_id) REFERENCES urunler(id)
            )
        """)

        _indeksler(conn)
        _sema_isaretle(conn)
        conn.commit()
        conn.close()
        log_info("Veritabani basariyla olusturuldu / kontrol edildi.")
        return True

    except Exception as e:
        log_error("Veritabani olusturma hatasi", e, __file__, "init_database")
        return False


def get_ayar(anahtar: str, varsayilan: str = "") -> str:
    """Ayar degerini okur."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT deger FROM ayarlar WHERE anahtar = ?", (anahtar,))
        row = cur.fetchone()
        conn.close()
        return row["deger"] if row else varsayilan
    except Exception as e:
        log_error(f"Ayar okunamadi: {anahtar}", e, __file__, "get_ayar")
        return varsayilan


def set_ayar(anahtar: str, deger: str) -> bool:
    """Ayar degerini kaydeder."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ayarlar (anahtar, deger) VALUES (?, ?)
            ON CONFLICT(anahtar) DO UPDATE SET deger = excluded.deger
        """, (anahtar, deger))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log_error(f"Ayar kaydedilemedi: {anahtar}", e, __file__, "set_ayar")
        return False


def sonraki_stok_sira() -> int:
    """Otomatik stok sira numarasini artirip dondurur (once bos kod havuzu)."""
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT stok_kodu FROM kod_havuzu ORDER BY stok_kodu LIMIT 1")
            r = cur.fetchone()
            if r:
                cur.execute("DELETE FROM kod_havuzu WHERE stok_kodu = ?", (r["stok_kodu"],))
                conn.commit()
                return int(str(r["stok_kodu"]).split("-", 1)[1])
        except Exception:
            pass
        finally:
            conn.close()
    except Exception:
        pass
    try:
        sira = int(get_ayar("son_stok_sira", "0")) + 1
        set_ayar("son_stok_sira", str(sira))
        return sira
    except Exception as e:
        log_error("Stok sira numarasi alinamadi", e, __file__, "sonraki_stok_sira")
        return 1


def stok_kodundan_sayi(stok_kodu: str) -> str:
    """KZM-1425L -> 1425 (sadece rakamlar, varyant harfi haric)."""
    import re
    s = (stok_kodu or "").strip().upper()
    if "-" in s:
        s = s.split("-", 1)[1]
    # L/XL son ekleri ayikla: 1425L -> 1425, 1445L/XL -> 1445
    s = s.split("/")[0]
    digits = re.sub(r"[^0-9]", "", s)
    return digits or "0000"


def barkod_normalize(deger: str) -> str:
    """Barkod karsilastirmasi icin 'KZM-' onegini ve bosluklari temizler."""
    s = (deger or "").strip()
    if s[:4].upper() == "KZM-":
        s = s[4:]
    return s.strip()


def barkod_varyant(stok_kodu: str, varyant_no: int = 0) -> str:
    """
    YYMM{stok}{vv}  (onek yok)
    Ornek: stok KZM-1422, varyant 0 -> 2610142200
           stok KZM-1422, varyant 1 -> 2610142201
    """
    try:
        from datetime import datetime
        simdi = datetime.now()
        yy = simdi.strftime("%y")
        mm = simdi.strftime("%m")
        sayi = stok_kodundan_sayi(stok_kodu)
        vv = max(0, int(varyant_no)) % 100
        return f"{yy}{mm}{sayi}{vv:02d}"
    except Exception as e:
        log_error("Barkod varyant uretilemedi", e, __file__, "barkod_varyant")
        return f"{stok_kodundan_sayi(stok_kodu)}{int(varyant_no) % 100:02d}"


def barkod_stoktan(stok_kodu: str, varyant_no: int = 0) -> str:
    """Geriye uyum: barkod_varyant ile ayni."""
    return barkod_varyant(stok_kodu, varyant_no)


def barkod_varyant_ek(stok_kodu: str, ek: str = "", varyant_no: int = 0) -> str:
    """YYMM{stok}{EK}  Ornek: 1455 + L -> 26111455L. Ek bos ise vv=01,02.."""
    try:
        import re
        sayi = stok_kodundan_sayi(stok_kodu)
        e = re.sub(r"[^A-Z0-9]", "", (ek or "").upper())
        if not e:
            e = f"{max(0, int(varyant_no)) % 100:02d}"
        from datetime import datetime
        simdi = datetime.now()
        return f"{simdi.strftime('%y')}{simdi.strftime('%m')}{sayi}{e}"
    except Exception as e:
        log_error("Barkod varyant ek uretilemedi", e, __file__, "barkod_varyant_ek")
        return f"{stok_kodundan_sayi(stok_kodu)}"


def barkod_uret(stok_kodu: str | None = None, varyant_no: int = 0) -> str:
    """Stok kodu + varyant no ile YYMM{stok}{vv} (onek yok)."""
    try:
        if stok_kodu:
            return barkod_varyant(stok_kodu, varyant_no)
        simdi = datetime.now()
        yy = simdi.strftime("%y")
        mm = simdi.strftime("%m")
        sira = sonraki_stok_sira()
        return f"{yy}{mm}{sira:04d}{int(varyant_no) % 100:02d}"
    except Exception as e:
        log_error("Barkod uretilemedi", e, __file__, "barkod_uret")
        return "0000000000"


# ---------------------------------------------------------------------------
# PostgreSQL destegi (DB_MODE=postgres)
# ---------------------------------------------------------------------------

def _cevir(sql: str) -> str:
    """SQLite diyalektini PostgreSQL'e cevirir. PRAGMA -> '' (atlanir)."""
    s = sql
    if s.lstrip().upper().startswith("PRAGMA"):
        return ""
    s = s.replace(
        "datetime('now','localtime')",
        "to_char(now(), 'YYYY-MM-DD HH24:MI:SS')",
    )
    s = s.replace("date('now','localtime')", "to_char(now(), 'YYYY-MM-DD')")
    or_ignore = bool(re.search(r"INSERT\s+OR\s+IGNORE\s+INTO", s, re.I))
    s = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", s, flags=re.I)
    if or_ignore and "ON CONFLICT" not in s.upper():
        s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    s = re.sub(r"\bLIKE\b", "ILIKE", s, flags=re.I)
    s = s.replace("?", "%s")
    return s


class _PGCursor:
    """sqlite3 uyumlu ince sarmalayici: ?, lastrowid, dict satirlar."""

    def __init__(self, cur, conn):
        self._cur = cur
        self._conn = conn
        self._sql = ""
        self._table = ""

    def execute(self, sql, params=None):
        self._sql = ""
        self._table = ""
        pg = _cevir(sql)
        if not pg:
            return self
        self._sql = pg
        m = re.match(r"\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", pg, re.I)
        if m:
            self._table = m.group(1)
        self._cur.execute(pg, params or None)
        return self

    def fetchone(self):
        r = self._cur.fetchone()
        return dict(r) if r is not None else None

    def fetchall(self):
        return [dict(r) for r in self._cur.fetchall()]

    @property
    def lastrowid(self):
        if not self._table:
            return None
        try:
            self._cur.execute("SAVEPOINT _lr")
            try:
                self._cur.execute(
                    "SELECT currval(pg_get_serial_sequence(%s, 'id')) AS kid",
                    (self._table,),
                )
                row = self._cur.fetchone()
                deger = dict(row).get("kid") if row else None
            except Exception:
                self._cur.execute("ROLLBACK TO SAVEPOINT _lr")
                deger = None
            self._cur.execute("RELEASE SAVEPOINT _lr")
            return deger
        except Exception:
            return None

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass


_PG_HAVUZ: list = []
_PG_HAVUZ_KILIT = threading.Lock()
_PG_HAVUZ_MAX = 8
_PG_HAVUZ_TAZE = 60.0  # sn: bu sureden yeni baglanti dogrulanmadan verilir


def _pg_ham_al():
    """Havuzdan saglam bir ham psycopg2 baglantisi alir, yoksa yenisini acar."""
    import time as _time

    while True:
        with _PG_HAVUZ_KILIT:
            if not _PG_HAVUZ:
                break
            ham, birakma = _PG_HAVUZ.pop()
        try:
            if getattr(ham, "closed", 1):
                continue
            if _time.time() - birakma > _PG_HAVUZ_TAZE:
                ham.cursor().execute("SELECT 1")
            return ham
        except Exception:
            try:
                ham.close()
            except Exception:
                pass
    return psycopg2.connect(
        host=POSTGRES.get("host", "127.0.0.1"),
        port=int(POSTGRES.get("port", 5432)),
        dbname=POSTGRES.get("dbname", "kozmostok"),
        user=POSTGRES.get("user", "postgres"),
        password=POSTGRES.get("password", ""),
        connect_timeout=10,
        application_name="KozmoStok",
    )


def _pg_ham_birak(ham) -> None:
    """Baglantiyi havuza geri koyar; havuz doluysa kapatir."""
    import time as _time

    try:
        if getattr(ham, "closed", 1):
            return
        ham.rollback()
    except Exception:
        try:
            ham.close()
        except Exception:
            pass
        return
    with _PG_HAVUZ_KILIT:
        if len(_PG_HAVUZ) < _PG_HAVUZ_MAX:
            _PG_HAVUZ.append((ham, _time.time()))
            return
    try:
        ham.close()
    except Exception:
        pass


def havuz_bosalt() -> None:
    """Bekleyen baglantilari kapatir (cikista cagrilir)."""
    with _PG_HAVUZ_KILIT:
        bekleyen = list(_PG_HAVUZ)
        _PG_HAVUZ.clear()
    for ham, _ in bekleyen:
        try:
            ham.close()
        except Exception:
            pass


class _PGConnection:
    """sqlite3.Connection uyumlu ince sarmalayici."""

    def __init__(self):
        if psycopg2 is None:
            raise RuntimeError(
                "psycopg2 kurulu degil. Kurulum: pip install psycopg2-binary"
            )
        self._conn = _pg_ham_al()

    def cursor(self):
        if self._conn is None:
            raise RuntimeError("Baglanti kapatilmis")
        return _PGCursor(self._conn.cursor(cursor_factory=RealDictCursor), self)

    def execute(self, sql, params=None):
        c = self.cursor()
        return c.execute(sql, params)

    def commit(self):
        if self._conn is not None:
            self._conn.commit()

    def rollback(self):
        try:
            if self._conn is not None:
                self._conn.rollback()
        except Exception:
            pass

    def close(self):
        ham, self._conn = self._conn, None
        if ham is not None:
            _pg_ham_birak(ham)


def _pg_baglanti(timeout: float = 30.0):
    try:
        return _PGConnection()
    except Exception as e:
        log_error("PostgreSQL baglantisi kurulamadi", e, __file__, "_pg_baglanti")
        raise


_PG_TS = "to_char(now(), 'YYYY-MM-DD HH24:MI:SS')"
_PG_D = "to_char(now(), 'YYYY-MM-DD')"


def _init_postgres():
    """PostgreSQL tablolari + varsayilan kayitlar."""
    try:
        conn = _PGConnection()
        if _sema_hazir(conn):
            conn.close()
            return True
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ayarlar (
                anahtar TEXT PRIMARY KEY,
                deger   TEXT NOT NULL
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS kategoriler (
                id          SERIAL PRIMARY KEY,
                ad          TEXT NOT NULL UNIQUE,
                slug        TEXT,
                olusturma   TEXT DEFAULT {_PG_TS}
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS urunler (
                id              SERIAL PRIMARY KEY,
                stok_kodu       TEXT NOT NULL UNIQUE,
                barkod          TEXT UNIQUE,
                ad              TEXT NOT NULL,
                kategori_id     INTEGER REFERENCES kategoriler(id),
                marka           TEXT,
                beden           TEXT,
                renk            TEXT,
                alis_fiyati     DOUBLE PRECISION DEFAULT 0,
                satis_fiyati    DOUBLE PRECISION DEFAULT 0,
                stok_adedi      INTEGER DEFAULT 0,
                kritik_stok     INTEGER DEFAULT 3,
                aciklama        TEXT,
                aktif           INTEGER DEFAULT 1,
                olusturma       TEXT DEFAULT {_PG_TS},
                guncelleme      TEXT,
                etsy_stok       INTEGER DEFAULT 0,
                trendyol_stok   INTEGER DEFAULT 0,
                wix_stok        INTEGER DEFAULT 0,
                gorsel_yolu     TEXT,
                wix_yayin       INTEGER DEFAULT 0,
                etsy_yayin      INTEGER DEFAULT 0,
                trendyol_yayin  INTEGER DEFAULT 0,
                parent_id       INTEGER,
                kod_hazir       INTEGER DEFAULT 1
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS satislar (
                id              SERIAL PRIMARY KEY,
                urun_id         INTEGER NOT NULL REFERENCES urunler(id),
                adet            INTEGER NOT NULL,
                birim_fiyat     DOUBLE PRECISION NOT NULL,
                indirim         DOUBLE PRECISION DEFAULT 0,
                odeme_tipi      TEXT NOT NULL,
                toplam          DOUBLE PRECISION NOT NULL,
                satis_tarihi    TEXT DEFAULT {_PG_D},
                satis_saati     TEXT DEFAULT {_PG_TS},
                fis_no          TEXT,
                banka           TEXT
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS masraflar (
                id              SERIAL PRIMARY KEY,
                tutar           DOUBLE PRECISION NOT NULL,
                aciklama        TEXT NOT NULL,
                masraf_tarihi   TEXT DEFAULT {_PG_D},
                olusturma       TEXT DEFAULT {_PG_TS}
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS stok_hareketleri (
                id              SERIAL PRIMARY KEY,
                urun_id         INTEGER NOT NULL REFERENCES urunler(id),
                hareket_tipi    TEXT NOT NULL,
                adet            INTEGER NOT NULL,
                aciklama        TEXT,
                tarih           TEXT DEFAULT {_PG_TS}
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS kullanicilar (
                id              SERIAL PRIMARY KEY,
                kullanici_adi   TEXT NOT NULL UNIQUE,
                sifre_hash      TEXT NOT NULL,
                rol             TEXT NOT NULL DEFAULT 'kasiyer',
                aktif           INTEGER DEFAULT 1,
                olusturma       TEXT DEFAULT {_PG_TS},
                email           TEXT
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS sayim_oturum (
                id          SERIAL PRIMARY KEY,
                ad          TEXT,
                durum       TEXT DEFAULT 'acik',
                olusturma   TEXT DEFAULT {_PG_TS},
                kapanis     TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sayim_satir (
                id              SERIAL PRIMARY KEY,
                oturum_id       INTEGER NOT NULL REFERENCES sayim_oturum(id),
                urun_id         INTEGER NOT NULL REFERENCES urunler(id),
                sistem_stok     INTEGER NOT NULL,
                sayilan_stok    INTEGER,
                fark            INTEGER
            )
        """)
        for k, v in [
            ("yonetim_pin", "2468"),
            ("magaza_adi", "KOZMOSIZE"),
            ("son_stok_sira", "0"),
            ("kurtarma_kodu", "KOZMO-2026-RESET"),
            ("smtp_host", ""),
            ("smtp_port", "587"),
            ("smtp_user", ""),
            ("smtp_pass", ""),
            ("smtp_from", ""),
        ]:
            cur.execute(
                "INSERT INTO ayarlar (anahtar, deger) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (k, v),
            )
        cur.execute("SELECT COUNT(*) AS n FROM kullanicilar")
        if int(cur.fetchone()["n"] or 0) == 0:
            from core.guvenlik import sifre_hashle
            cur.execute(
                "INSERT INTO kullanicilar (kullanici_adi, sifre_hash, rol) VALUES (%s, %s, %s)",
                ("admin", sifre_hashle("2468"), "yonetici"),
            )
            cur.execute(
                "INSERT INTO kullanicilar (kullanici_adi, sifre_hash, rol) VALUES (%s, %s, %s)",
                ("kasa", sifre_hashle("1234"), "kasiyer"),
            )
        _indeksler(conn)
        _sema_isaretle(conn)
        conn.commit()
        conn.close()
        log_info("PostgreSQL veritabani hazir (tablolar olusturuldu/kontrol edildi).")
        return True
    except Exception as e:
        log_error("PostgreSQL kurulum hatasi", e, __file__, "_init_postgres")
        return False
