# -*- coding: utf-8 -*-
"""
Cevrimdisi-ilk senkron motoru.

Program HER ZAMAN yerel SQLite ile calisir; PostgreSQL (Supabase) yalnizca
merkez senkron merkezi olarak kullanilir. Kurallar:

- Yerel degisiklikler SQLite trigger'lariyla `sync_kuyruk` tablosuna yazilir;
  kayit ekleyen/guncelleyen HICBIR kod degistirmeden yakalanir.
- Senkron sirasi: once sunucuya GONDER, sonra sunucudan CEK. Boylece
  yerelde silinen satir cekme asamasinda sunucudan geri canlanmaz; ayni
  satir iki tarafta da degismisse SUNUCU versiyonu kazanir.
- Satir kimligi `sync_id` (rastgele 32 haneli metin) ile tasinir; makina
  id'leri farkli olsa bile ayni satir taninir.
- Iliski kolonlari (urun_id gibi) makina-yerel oldugu icin gonderimde
  `urun_sync_id` gibi es kolonlar doldurulur, cekerken geri cozulur.
- Silinen satirlar mezar tasi (yerelde `sync_silinen`, sunucuda
  `sync_silinenler`) ile tasinir ve diger makinalardan da silinir.
- Ilk kurulumda (sync_kurulum ayari yokken) baglanti varsa veri tablolari
  temizlenip sunucudan yuklenir; oncesinde yerel db yedegi alinir.
  kullanicilar tablosu temizlenmez, birlestirilir.

Butun adimlar baglanti yoksa sessizce atlanir; program yerel olarak
calismaya devam eder.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta

from core.database import get_connection, get_ayar, set_ayar
from core.db_config import POSTGRES, makine_adi
from core.logger import log_error, log_info

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:  # psycopg2 yoksa SQLite modu calismaya devam eder
    psycopg2 = None
    RealDictCursor = None

# Senkron plani surumu: DDL degisince artir (geri doldurma yeniden kosar).
SYNC_SURUM = "1"

_BASLANGIC = "2000-01-01 00:00:00"
_PG_TS = "to_char(now(), 'YYYY-MM-DD HH24:MI:SS')"

# Senkron edilacak tablolar (bagimlilik sirasiyla: once ust kayit).
# fk: {kolon: referans_tablo} — gonderimde kolon_adX_sync_id es kolonu doldurulur.
TABLOLAR = [
    {"tablo": "kullanicilar",
     "kolonlar": ("kullanici_adi", "sifre_hash", "rol", "aktif", "olusturma", "email"),
     "fk": {}},
    {"tablo": "kategoriler",
     "kolonlar": ("ad", "slug", "olusturma"),
     "fk": {}},
    {"tablo": "urunler",
     "kolonlar": ("stok_kodu", "barkod", "ad", "kategori_id", "marka", "beden", "renk",
                  "alis_fiyati", "satis_fiyati", "stok_adedi", "kritik_stok", "aciklama",
                  "aktif", "olusturma", "guncelleme", "etsy_stok", "trendyol_stok",
                  "wix_stok", "gorsel_yolu", "wix_yayin", "etsy_yayin", "trendyol_yayin",
                  "parent_id", "kod_hazir"),
     "fk": {"kategori_id": "kategoriler", "parent_id": "urunler"}},
    {"tablo": "satislar",
     "kolonlar": ("urun_id", "adet", "birim_fiyat", "indirim", "odeme_tipi", "toplam",
                  "satis_tarihi", "satis_saati", "fis_no", "banka"),
     "fk": {"urun_id": "urunler"}},
    {"tablo": "masraflar",
     "kolonlar": ("tutar", "aciklama", "masraf_tarihi", "olusturma"),
     "fk": {}},
    {"tablo": "stok_hareketleri",
     "kolonlar": ("urun_id", "hareket_tipi", "adet", "aciklama", "tarih"),
     "fk": {"urun_id": "urunler"}},
    {"tablo": "sayim_oturum",
     "kolonlar": ("ad", "durum", "olusturma", "kapanis"),
     "fk": {}},
    {"tablo": "sayim_satir",
     "kolonlar": ("oturum_id", "urun_id", "sistem_stok", "sayilan_stok", "fark"),
     "fk": {"oturum_id": "sayim_oturum", "urun_id": "urunler"}},
    {"tablo": "gun_sonu",
     "kolonlar": ("tarih", "kullanici", "kullanici_id", "ciro", "nakit_satis",
                  "kart_satis", "diger_satis", "masraf", "onceki_devir",
                  "beklenen_nakit", "sayilan_nakit", "fark", "devir", "notlar",
                  "excel_yolu", "excel_b64", "olusturma"),
     "fk": {}},
    {"tablo": "gun_sonu_kalem",
     "kolonlar": ("gun_sonu_id", "ad", "tur", "tutar", "adet", "aciklama"),
     "fk": {"gun_sonu_id": "gun_sonu"}},
    {"tablo": "vardiya_oturumlari",
     "kolonlar": ("kullanici", "kullanici_id", "giris_tarihi", "giris_saati",
                  "cikis_tarihi", "cikis_saati"),
     "fk": {}},
    {"tablo": "islem_gunlugu",
     "kolonlar": ("kullanici", "kullanici_id", "islem", "detay", "tarih", "saat"),
     "fk": {}},
]

_SIRA = [t["tablo"] for t in TABLOLAR]
# Temizlemede kullanicilar haric (giris lokal kalsin), bagimlilik tersi sira.
_SILA_SIRASI = [t for t in reversed(_SIRA) if t != "kullanicilar"]

# Sunucuda (PostgreSQL) tablo tanimlari — cogu database.py ile ayni,
# gun_sonu / vardiya / gunluk tablolari servislerdeki tanimlarin PG hali.
_PG_TABLOLAR = {
    "kullanicilar": """
        CREATE TABLE IF NOT EXISTS kullanicilar (
            id              SERIAL PRIMARY KEY,
            kullanici_adi   TEXT NOT NULL UNIQUE,
            sifre_hash      TEXT NOT NULL,
            rol             TEXT NOT NULL DEFAULT 'kasiyer',
            aktif           INTEGER DEFAULT 1,
            olusturma       TEXT DEFAULT {_ts},
            email           TEXT
        )""",
    "kategoriler": """
        CREATE TABLE IF NOT EXISTS kategoriler (
            id          SERIAL PRIMARY KEY,
            ad          TEXT NOT NULL UNIQUE,
            slug        TEXT,
            olusturma   TEXT DEFAULT {_ts}
        )""",
    "urunler": """
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
            olusturma       TEXT DEFAULT {_ts},
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
        )""",
    "satislar": """
        CREATE TABLE IF NOT EXISTS satislar (
            id              SERIAL PRIMARY KEY,
            urun_id         INTEGER NOT NULL REFERENCES urunler(id),
            adet            INTEGER NOT NULL,
            birim_fiyat     DOUBLE PRECISION NOT NULL,
            indirim         DOUBLE PRECISION DEFAULT 0,
            odeme_tipi      TEXT NOT NULL,
            toplam          DOUBLE PRECISION NOT NULL,
            satis_tarihi    TEXT DEFAULT to_char(now(), 'YYYY-MM-DD'),
            satis_saati     TEXT DEFAULT {_ts},
            fis_no          TEXT,
            banka           TEXT
        )""",
    "masraflar": """
        CREATE TABLE IF NOT EXISTS masraflar (
            id              SERIAL PRIMARY KEY,
            tutar           DOUBLE PRECISION NOT NULL,
            aciklama        TEXT NOT NULL,
            masraf_tarihi   TEXT DEFAULT to_char(now(), 'YYYY-MM-DD'),
            olusturma       TEXT DEFAULT {_ts}
        )""",
    "stok_hareketleri": """
        CREATE TABLE IF NOT EXISTS stok_hareketleri (
            id              SERIAL PRIMARY KEY,
            urun_id         INTEGER NOT NULL REFERENCES urunler(id),
            hareket_tipi    TEXT NOT NULL,
            adet            INTEGER NOT NULL,
            aciklama        TEXT,
            tarih           TEXT DEFAULT {_ts}
        )""",
    "sayim_oturum": """
        CREATE TABLE IF NOT EXISTS sayim_oturum (
            id          SERIAL PRIMARY KEY,
            ad          TEXT,
            durum       TEXT DEFAULT 'acik',
            olusturma   TEXT DEFAULT {_ts},
            kapanis     TEXT
        )""",
    "sayim_satir": """
        CREATE TABLE IF NOT EXISTS sayim_satir (
            id              SERIAL PRIMARY KEY,
            oturum_id       INTEGER NOT NULL REFERENCES sayim_oturum(id),
            urun_id         INTEGER NOT NULL REFERENCES urunler(id),
            sistem_stok     INTEGER NOT NULL,
            sayilan_stok    INTEGER,
            fark            INTEGER
        )""",
    "gun_sonu": """
        CREATE TABLE IF NOT EXISTS gun_sonu (
            id              SERIAL PRIMARY KEY,
            tarih           TEXT NOT NULL,
            kullanici       TEXT,
            kullanici_id    INTEGER,
            ciro            DOUBLE PRECISION DEFAULT 0,
            nakit_satis     DOUBLE PRECISION DEFAULT 0,
            kart_satis      DOUBLE PRECISION DEFAULT 0,
            diger_satis     DOUBLE PRECISION DEFAULT 0,
            masraf          DOUBLE PRECISION DEFAULT 0,
            onceki_devir    DOUBLE PRECISION DEFAULT 0,
            beklenen_nakit  DOUBLE PRECISION DEFAULT 0,
            sayilan_nakit   DOUBLE PRECISION DEFAULT 0,
            fark            DOUBLE PRECISION DEFAULT 0,
            devir           DOUBLE PRECISION DEFAULT 0,
            notlar          TEXT,
            excel_yolu      TEXT,
            excel_b64       TEXT,
            olusturma       TEXT
        )""",
    "gun_sonu_kalem": """
        CREATE TABLE IF NOT EXISTS gun_sonu_kalem (
            id          SERIAL PRIMARY KEY,
            gun_sonu_id INTEGER NOT NULL,
            ad          TEXT,
            tur         TEXT,
            tutar       DOUBLE PRECISION DEFAULT 0,
            adet        DOUBLE PRECISION DEFAULT 0,
            aciklama    TEXT
        )""",
    "vardiya_oturumlari": """
        CREATE TABLE IF NOT EXISTS vardiya_oturumlari (
            id              SERIAL PRIMARY KEY,
            kullanici       TEXT,
            kullanici_id    INTEGER,
            giris_tarihi    TEXT,
            giris_saati     TEXT,
            cikis_tarihi    TEXT,
            cikis_saati     TEXT
        )""",
    "islem_gunlugu": """
        CREATE TABLE IF NOT EXISTS islem_gunlugu (
            id              SERIAL PRIMARY KEY,
            kullanici       TEXT,
            kullanici_id    INTEGER,
            islem           TEXT NOT NULL,
            detay           TEXT,
            tarih           TEXT,
            saat            TEXT
        )""",
}


class _Ertele(Exception):
    """Satir su an uygulanamaz (bagli kayit henuz cekilmedi) — sonra denenir."""


def _sync_kolon(fk_kolon: str) -> str:
    """urun_id -> urun_sync_id gibi es kolon adi."""
    if fk_kolon.endswith("_id"):
        return fk_kolon[:-3] + "_sync_id"
    return fk_kolon + "_sync_id"


def _eski_mi(zaman: str | None, gun: int = 7) -> bool:
    """Zaman damgasi `gun` gunden daha eski mi (cozulemeyen satiri birak)."""
    try:
        t = datetime.strptime(str(zaman or "")[:19], "%Y-%m-%d %H:%M:%S")
        return t < datetime.now() - timedelta(days=gun)
    except Exception:
        return False


def _ayni(a, b) -> bool:
    """Icerik karsilastirmasi (tip farkliliklarina toleransli)."""
    if a == b:
        return True
    return str(a if a is not None else "") == str(b if b is not None else "")


# ---------------------------------------------------------------------------
# Yerel (SQLite) hazirlik
# ---------------------------------------------------------------------------

_YEREL_EK_TABLOLAR = (
    """
    CREATE TABLE IF NOT EXISTS gun_sonu (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih           TEXT NOT NULL,
        kullanici       TEXT,
        kullanici_id    INTEGER,
        ciro            REAL DEFAULT 0,
        nakit_satis     REAL DEFAULT 0,
        kart_satis      REAL DEFAULT 0,
        diger_satis     REAL DEFAULT 0,
        masraf          REAL DEFAULT 0,
        onceki_devir    REAL DEFAULT 0,
        beklenen_nakit  REAL DEFAULT 0,
        sayilan_nakit   REAL DEFAULT 0,
        fark            REAL DEFAULT 0,
        devir           REAL DEFAULT 0,
        notlar          TEXT,
        excel_yolu      TEXT,
        excel_b64       TEXT,
        olusturma       TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gun_sonu_kalem (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        gun_sonu_id INTEGER NOT NULL,
        ad          TEXT,
        tur         TEXT,
        tutar       REAL DEFAULT 0,
        adet        REAL DEFAULT 0,
        aciklama    TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vardiya_oturumlari (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        kullanici       TEXT,
        kullanici_id    INTEGER,
        giris_tarihi    TEXT,
        giris_saati     TEXT,
        cikis_tarihi    TEXT,
        cikis_saati     TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS islem_gunlugu (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        kullanici       TEXT,
        kullanici_id    INTEGER,
        islem           TEXT NOT NULL,
        detay           TEXT,
        tarih           TEXT,
        saat            TEXT
    )
    """,
)


def _trigger_sql(t: str) -> tuple[str, str, str]:
    """Bir tablo icin ekle/guncelle/sil yakalama trigger'lari.

    - INSERT'te sync_id yoksa uretilir ve kuyruga yazilir.
    - UPDATE'te (mevcut, sync_id'li satir) kuyruga yazilir. Ceken tarafin
      guncellemeleri de duser ama icerik ayniysa gonderimde atlanir.
    - DELETE'te mezar tasi birakilir (baska makinalardan da silinsin).
    """
    return (
        f"CREATE TRIGGER IF NOT EXISTS trg_{t}_sync_ins AFTER INSERT ON {t} "
        f"WHEN NEW.sync_id IS NULL BEGIN "
        f"UPDATE {t} SET sync_id = lower(hex(randomblob(16))) WHERE id = NEW.id; "
        f"INSERT INTO sync_kuyruk (tablo, lokal_id) VALUES ('{t}', NEW.id); END",

        f"CREATE TRIGGER IF NOT EXISTS trg_{t}_sync_upd AFTER UPDATE ON {t} "
        f"WHEN OLD.sync_id IS NOT NULL BEGIN "
        f"INSERT INTO sync_kuyruk (tablo, lokal_id) VALUES ('{t}', NEW.id); END",

        f"CREATE TRIGGER IF NOT EXISTS trg_{t}_sync_del AFTER DELETE ON {t} "
        f"WHEN OLD.sync_id IS NOT NULL BEGIN "
        f"INSERT INTO sync_silinen (tablo, sync_id) VALUES ('{t}', OLD.sync_id); END",
    )


def yerel_hazirla() -> bool:
    """Yerel SQLite'a sync kolonlari, trigger'lari ve kuyruk tablolarini ekler.

    Her senkron oncesi cagrilir; sync_id'siz eski satirlar geri doldurulup
    kuyruga yazilir (boylece trigger'lardan once yapilan degisiklikler de
    bir sonraki gonderimle sunucuya gider).
    """
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            for sql in _YEREL_EK_TABLOLAR:
                cur.execute(sql)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sync_kuyruk (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    tablo    TEXT NOT NULL,
                    lokal_id INTEGER NOT NULL,
                    zaman    TEXT DEFAULT (datetime('now','localtime'))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sync_silinen (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    tablo   TEXT NOT NULL,
                    sync_id TEXT NOT NULL,
                    zaman   TEXT DEFAULT (datetime('now','localtime'))
                )
            """)
            for spec in TABLOLAR:
                t = spec["tablo"]
                try:
                    cur.execute(f"ALTER TABLE {t} ADD COLUMN sync_id TEXT")
                except Exception:
                    pass
                for kolon in spec["fk"]:
                    try:
                        cur.execute(f"ALTER TABLE {t} ADD COLUMN {_sync_kolon(kolon)} TEXT")
                    except Exception:
                        pass
                for sql in _trigger_sql(t):
                    cur.execute(sql)
                # Trigger'lardan ONCE olusturulmus satirlar: sync_id ver + kuyruga yaz
                for r in cur.execute(
                    f"SELECT id FROM {t} WHERE sync_id IS NULL"
                ).fetchall():
                    cur.execute(
                        f"UPDATE {t} SET sync_id = lower(hex(randomblob(16))) "
                        f"WHERE id = ?",
                        (r["id"],),
                    )
                    cur.execute(
                        "INSERT INTO sync_kuyruk (tablo, lokal_id) VALUES (?, ?)",
                        (t, r["id"]),
                    )
                cur.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{t}_sync ON {t} (sync_id)")
            cur.execute(
                "INSERT INTO ayarlar (anahtar, deger) VALUES ('sync_surum', ?) "
                "ON CONFLICT(anahtar) DO UPDATE SET deger = excluded.deger",
                (SYNC_SURUM,),
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as e:
        log_error("Yerel sync hazirligi", e, __file__, "yerel_hazirla")
        return False


# ---------------------------------------------------------------------------
# Sunucu (PostgreSQL) hazirlik
# ---------------------------------------------------------------------------

def _pg_baglan(bekleme: float = 12.0):
    if psycopg2 is None:
        raise RuntimeError("psycopg2 kurulu degil (pip install psycopg2-binary)")
    p = POSTGRES
    pg = psycopg2.connect(
        host=p.get("host"),
        port=p.get("port", 5432),
        dbname=p.get("dbname"),
        user=p.get("user"),
        password=p.get("password"),
        connect_timeout=max(2, int(bekleme)),
        cursor_factory=RealDictCursor,
    )
    # Uygulama oturumlari islemlerini uzun sure acik tutabiliyor; bizim
    # ifademiz kilit beklerken sonsuza kadar asili kalmasin — hizli
    # vazgecip tekrar deneyelim (senkronize 1 kez tekrar eder).
    try:
        cur = pg.cursor()
        cur.execute("SET statement_timeout = '8s'")
        cur.close()
        pg.commit()
    except Exception:
        try:
            pg.rollback()
        except Exception:
            pass
    return pg


def sunucu_uygun_mi(bekleme: float = 4.0) -> bool:
    """Sunucu su an ulasilabilir mi? (Arayuz uyarisi icin hizli test.)"""
    if psycopg2 is None:
        return False
    pg = None
    try:
        pg = _pg_baglan(bekleme)
        cur = pg.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        return True
    except Exception:
        return False
    finally:
        try:
            if pg is not None:
                pg.close()
        except Exception:
            pass


def sunucu_hazirla(pg) -> bool:
    """Sunucu tablolarina sync kolonlarini/indekslerini ekler (tek seferlik isler)."""
    cur = pg.cursor()
    # Hizli yol: surum zaten kurulmussa hic DDL calistirmayiz — ALTER TABLE
    # kolon varsa bile AccessExclusiveLock alir, diger oturumlarla kilitlenir.
    try:
        s = cur.execute("SELECT deger FROM sync_durum WHERE anahtar = 'surum'").fetchone()
        if s is not None and str(s["deger"]) == SYNC_SURUM:
            pg.commit()
            return True
    except Exception:
        pg.rollback()  # tablo henüz yok; tam yola gir
    for spec in TABLOLAR:
        t = spec["tablo"]
        try:
            cur.execute(_PG_TABLOLAR[t].replace("{_ts}", _PG_TS))
            cur.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS sync_id TEXT")
            cur.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS sync_zaman TEXT")
            cur.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS makine TEXT")
            for kolon in spec["fk"]:
                cur.execute(
                    f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS {_sync_kolon(kolon)} TEXT"
                )
        except Exception as e:
            # DDL baska bir oturumun kilidine takilirsa senkronu bloklamasin:
            # sema zaten kurulmus olabilir, sadece kaydolamamisiz.
            log_error(f"Sunucu sema adiimi atlandi ({t})", e, __file__, "sunucu_hazirla")
            pg.rollback()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sync_silinenler (
            id      SERIAL PRIMARY KEY,
            tablo   TEXT NOT NULL,
            sync_id TEXT NOT NULL,
            zaman   TEXT DEFAULT {_ts},
            makine  TEXT
        )""".replace("{_ts}", _PG_TS))
    # Geri doldurma: eski sunucu kayitlarina kimlik ver (sunucuda bir kez kosar).
    cur.execute(
        "CREATE TABLE IF NOT EXISTS sync_durum (anahtar TEXT PRIMARY KEY, deger TEXT)"
    )
    cur.execute("SELECT deger FROM sync_durum WHERE anahtar = 'surum'")
    surum_satiri = cur.fetchone()
    if surum_satiri is None or str(surum_satiri["deger"]) != SYNC_SURUM:
        for spec in TABLOLAR:
            t = spec["tablo"]
            cur.execute(f"UPDATE {t} SET sync_id = 'srv-' || id WHERE sync_id IS NULL")
            cur.execute(f"UPDATE {t} SET sync_zaman = {_PG_TS} WHERE sync_zaman IS NULL")
            for kolon, ref in spec["fk"].items():
                sk = _sync_kolon(kolon)
                cur.execute(
                    f"UPDATE {t} SET {sk} = (SELECT r.sync_id FROM {ref} r "
                    f"WHERE r.id = {t}.{kolon}) "
                    f"WHERE {sk} IS NULL AND {kolon} IS NOT NULL"
                )
        cur.execute("INSERT INTO sync_durum (anahtar, deger) VALUES ('surum', %s) "
                    "ON CONFLICT (anahtar) DO UPDATE SET deger = EXCLUDED.deger",
                    (SYNC_SURUM,))
    for spec in TABLOLAR:
        try:
            cur.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{spec['tablo']}_sync "
                f"ON {spec['tablo']} (sync_id)"
            )
        except Exception as e:
            log_error(f"Indeks atlandi ({spec['tablo']})", e, __file__, "sunucu_hazirla")
            pg.rollback()
    try:
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_sync_silinenler "
            "ON sync_silinenler (tablo, sync_id)"
        )
    except Exception as e:
        log_error("Indeks atlandi (sync_silinenler)", e, __file__, "sunucu_hazirla")
        pg.rollback()
    pg.commit()
    return True


# ---------------------------------------------------------------------------
# Cekme (sunucu -> yerel)
# ---------------------------------------------------------------------------

def _satir_cek(conn, spec, r: dict) -> None:
    """Sunucu satirini yerel SQLite'a tasir (yoksa ekle, varsa guncelle)."""
    t = spec["tablo"]
    sid = r.get("sync_id")
    if not sid:
        return
    degerler = {c: r.get(c) for c in spec["kolonlar"]}
    for kolon, ref in spec["fk"].items():
        rsid = r.get(_sync_kolon(kolon))
        if not rsid:
            continue  # es kolon yoksa degeri oldugu gibi birak (eski kayit)
        rr = conn.execute(f"SELECT id FROM {ref} WHERE sync_id=?", (rsid,)).fetchone()
        if rr is not None:
            degerler[kolon] = rr["id"]
        elif _eski_mi(r.get("sync_zaman")):
            log_info(f"Cekilemedi (bagli kayit yok, atlandi): {t}#{r.get('id')}")
            return
        else:
            raise _Ertele(f"{t}: bagli kayit {ref}#{rsid} henuz yerelde yok")
    kolonlar = list(degerler.keys())
    mevcut = conn.execute(f"SELECT id FROM {t} WHERE sync_id=?", (sid,)).fetchone()
    if mevcut is not None:
        # Icerik ayniysa dokunma (trigger eko'sunu ve donguyu engeller).
        yerel = conn.execute(
            f"SELECT {', '.join(kolonlar)} FROM {t} WHERE id=?", (mevcut["id"],)
        ).fetchone()
        if yerel is not None and all(
            _ayni(yerel[c], degerler[c]) for c in kolonlar
        ):
            return
        cur = conn.cursor()
        cur.execute(
            f"UPDATE {t} SET {', '.join(f'{c}=?' for c in kolonlar)} WHERE id=?",
            (*[degerler[c] for c in kolonlar], mevcut["id"]),
        )
    else:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO {t} (sync_id, {', '.join(kolonlar)}) "
            f"VALUES (?{', ?' * len(kolonlar)})",
            (sid, *[degerler[c] for c in kolonlar]),
        )


def _cek(conn, pg, makine: str) -> int:
    """Sunucudaki yeni/degisen kayitlari ve silmeleri yerele tasir."""
    alinan = 0
    cur = pg.cursor()

    # 1) Mezar taslari: baska makina sildiysen buradan da sil.
    son_mezar = get_ayar("sync_son_mezar", _BASLANGIC)
    cur.execute(
        "SELECT tablo, sync_id, zaman FROM sync_silinenler "
        "WHERE zaman > %s ORDER BY zaman LIMIT 5000",
        (son_mezar,),
    )
    son_yeni = son_mezar
    for r in cur.fetchall():
        t = r["tablo"]
        sid = r["sync_id"]
        try:
            conn.execute(f"UPDATE {t} SET sync_id = NULL WHERE sync_id = ?", (sid,))
            conn.execute(f"DELETE FROM {t} WHERE sync_id = ?", (sid,))
            if str(r["zaman"]) > son_yeni:
                son_yeni = str(r["zaman"])
            alinan += 1
        except Exception as e:
            log_error(f"Mezar tasi uygulanamadi: {t}#{sid}", e, __file__, "_cek")
    conn.commit()
    set_ayar("sync_son_mezar", son_yeni)

    # 2) Yeni / degisen satirlar (bagimlilik sirasiyla).
    for spec in TABLOLAR:
        t = spec["tablo"]
        son = get_ayar(f"sync_son_cekme_{t}", _BASLANGIC)
        cur.execute(
            f"SELECT * FROM {t} WHERE sync_zaman > %s ORDER BY sync_zaman LIMIT 5000",
            (son,),
        )
        son_iyi = son
        islenen = 0
        for r in cur.fetchall():
            try:
                _satir_cek(conn, spec, r)
                son_iyi = r["sync_zaman"]
                alinan += 1
            except _Ertele:
                break  # su tabloda ileri gidemez; sonraki senkronda tekrar denenir
            except Exception as e:
                log_error(f"Satir cekilemedi ({t}#{r.get('id')})", e, __file__, "_cek")
            islenen += 1
            if islenen % 500 == 0:
                # Uzun yaz kilidi tutmayalim (ayni anda ayar/ başka baglanti
                # yazmasin diye arada birbiriyoruz).
                conn.commit()
        conn.commit()
        set_ayar(f"sync_son_cekme_{t}", son_iyi)
        conn.commit()
    return alinan


# ---------------------------------------------------------------------------
# Gonderme (yerel -> sunucu)
# ---------------------------------------------------------------------------

def _satir_gonder(cur_pg, conn, spec, satir, makine: str) -> bool:
    """Bir yerel satiri sunucuya tasir. Icerik sunucudakiyle ayniysa atlar."""
    t = spec["tablo"]
    sid = satir["sync_id"]
    if not sid:
        sid = uuid.uuid4().hex
        conn.execute(f"UPDATE {t} SET sync_id=? WHERE id=?", (sid, satir["id"]))

    # Iliskileri coz: yerel id -> (sunucu id, sync_id).
    fk_cozum: dict = {}
    for kolon, ref in spec["fk"].items():
        deger = satir[kolon]
        if deger is None:
            fk_cozum[kolon] = (None, None)
            continue
        rr = conn.execute(f"SELECT sync_id FROM {ref} WHERE id=?", (deger,)).fetchone()
        ref_sid = rr["sync_id"] if rr else None
        if not ref_sid:
            raise _Ertele(f"{t}#{satir['id']}: bagli {kolon} gonderilmedi")
        cur_pg.execute(
            f"SELECT id FROM {ref} WHERE sync_id=%s", (ref_sid,)
        )
        sr = cur_pg.fetchone()
        if sr is None:
            raise _Ertele(f"{t}#{satir['id']}: sunucuda {ref}#{ref_sid} yok")
        fk_cozum[kolon] = (sr["id"], ref_sid)

    # Sunucuda ayni icerik varsa gonderme (echo dongusunu keser).
    sec = ["sync_id", "makine"] + list(spec["kolonlar"]) + [
        _sync_kolon(c) for c in spec["fk"]
    ]
    cur_pg.execute(
        f"SELECT {', '.join(sec)} FROM {t} WHERE sync_id=%s", (sid,)
    )
    eski = cur_pg.fetchone()
    if eski is not None:
        icerik_ayni = all(
            _ayni(eski[c], satir[c]) for c in spec["kolonlar"] if c not in spec["fk"]
        )
        if icerik_ayni:
            for kolon, (sunucu_id, ref_sid) in fk_cozum.items():
                if not _ayni(eski[kolon], sunucu_id):
                    icerik_ayni = False
                    break
                if not _ayni(eski[_sync_kolon(kolon)], ref_sid):
                    icerik_ayni = False
                    break
        if icerik_ayni:
            return False

    kolon_adlari = ["sync_id", "makine"]
    degerler: list = [sid, makine]
    for kolon in spec["kolonlar"]:
        if kolon in spec["fk"]:
            sunucu_id, ref_sid = fk_cozum[kolon]
            kolon_adlari.append(kolon)
            degerler.append(sunucu_id)
            kolon_adlari.append(_sync_kolon(kolon))
            degerler.append(ref_sid)
        else:
            kolon_adlari.append(kolon)
            degerler.append(satir[kolon])

    cur_pg.execute(
        f"INSERT INTO {t} ({', '.join(kolon_adlari)}, sync_zaman) "
        f"VALUES ({', '.join(['%s'] * len(degerler))}, {_PG_TS}) "
        f"ON CONFLICT (sync_id) DO UPDATE SET "
        f"{', '.join(f'{c} = EXCLUDED.{c}' for c in kolon_adlari if c != 'sync_id')}, "
        f"sync_zaman = {_PG_TS}",
        (*degerler,),
    )
    return True


def _gonder(conn, pg, makine: str) -> int:
    """Kuyruktaki ve mezar tasindaki yerel degisiklikleri sunucuya tasir."""
    gonderilen = 0
    cur_pg = pg.cursor()

    # 1) Mezar taslari (silinenler).
    try:
        mezat = conn.execute(
            "SELECT id, tablo, sync_id FROM sync_silinen ORDER BY id LIMIT 5000"
        ).fetchall()
        for r in mezat:
            try:
                cur_pg.execute(
                    f"DELETE FROM {r['tablo']} WHERE sync_id = %s", (r["sync_id"],)
                )
                cur_pg.execute(
                    "INSERT INTO sync_silinenler (tablo, sync_id, makine) "
                    "VALUES (%s, %s, %s) ON CONFLICT (tablo, sync_id) DO NOTHING",
                    (r["tablo"], r["sync_id"], makine),
                )
                conn.execute("DELETE FROM sync_silinen WHERE id = ?", (r["id"],))
                pg.commit()
                conn.commit()
                gonderilen += 1
            except Exception as e:
                try:
                    pg.rollback()
                except Exception:
                    pass
                log_error(
                    f"Mezar tasi gonderilemedi: {r['tablo']}#{r['sync_id']}",
                    e, __file__, "_gonder",
                )
                break
    except Exception as e:
        log_error("Mezar tasi listesi", e, __file__, "_gonder")

    # 2) Kuyruktaki satirlar.
    for spec in TABLOLAR:
        t = spec["tablo"]
        kuyruk = conn.execute(
            "SELECT lokal_id, MIN(id) AS ilk FROM sync_kuyruk WHERE tablo=? "
            "GROUP BY lokal_id ORDER BY ilk LIMIT 4000",
            (t,),
        ).fetchall()
        for k in kuyruk:
            lid = k["lokal_id"]
            satir = conn.execute(f"SELECT * FROM {t} WHERE id=?", (lid,)).fetchone()
            if satir is None:
                # Satir bu arada silindi; mezar tasi zaten gitti/yok.
                conn.execute(
                    "DELETE FROM sync_kuyruk WHERE tablo=? AND lokal_id=?", (t, lid)
                )
                conn.commit()
                continue
            try:
                if _satir_gonder(cur_pg, conn, spec, satir, makine):
                    gonderilen += 1
                conn.execute(
                    "DELETE FROM sync_kuyruk WHERE tablo=? AND lokal_id=?", (t, lid)
                )
                pg.commit()
                conn.commit()
            except _Ertele as e:
                log_info(f"Ertelendi: {e}")
                break  # bu tabloda sunucu hazir degil; sonraki senkronda denenir
            except Exception as e:
                try:
                    pg.rollback()
                except Exception:
                    pass
                if "duplicate key" in str(e):
                    # Iki makina ayni benzersiz degeri (stok kodu vb.) urettiyse
                    # bu satir sunucuya gidemez; yerelde kalir, kuyruktan duser.
                    log_error(
                        f"Benzersiz deger cakismasi, atlandi ({t}#{lid})",
                        e, __file__, "_gonder",
                    )
                    conn.execute(
                        "DELETE FROM sync_kuyruk WHERE tablo=? AND lokal_id=?",
                        (t, lid),
                    )
                    conn.commit()
                    continue
                log_error(f"Satir gonderilemedi ({t}#{lid})", e, __file__, "_gonder")
                break  # ag/erisim sorunu: kalan satirlari birak, tekrar denensin
    return gonderilen


# ---------------------------------------------------------------------------
# Ana akis
# ---------------------------------------------------------------------------

_kilit = threading.Lock()


def _ilk_kurulum(conn, pg) -> bool:
    """sync_kurulum ayari yoksa: yedek al, veri tablolarini temizle, isaretle.

    kullanicilar temizlenmez (lokal giris her zaman calisir), birlestirilir.
    """
    if get_ayar("sync_kurulum", ""):
        return False
    try:
        from core.yedek_servis import yedek_al
        ok, yol = yedek_al("sync-ilk")
        if ok:
            log_info(f"Ilk senkron oncesi yedek: {yol}")
    except Exception as e:
        log_error("Ilk kurulum yedegi alinamadi", e, __file__, "_ilk_kurulum")
    cur = conn.cursor()
    for t in _SILA_SIRASI:
        cur.execute(f"DELETE FROM {t}")
    cur.execute("DELETE FROM sync_kuyruk")
    cur.execute("DELETE FROM sync_silinen")
    conn.commit()
    set_ayar("sync_kurulum", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log_info(
        "Ilk senkron kurulumu: veri tablolari temizlendi, sunucudan yuklenecek "
        "(kullanicilar birlestirilir)."
    )
    return True


def senkronize(bekleme: float = 12.0, sessiz: bool = False) -> dict:
    """Tam senkron: gonder (yerel yenileri) + cek (sunucu kazanir).

    ONCE gonderilir: yoksa yerelde silinen satir, cekme asamasinda
    sunucudan geri canlanir (silme push edilmeden cekme calisir).
    Baglanti yoksa hata alaninda doner; program yerel calismaya devam eder.
    Donus: {"ok": bool, "gonderilen": int, "alinan": int, "hata": str}
    """
    sonuc = {"ok": False, "gonderilen": 0, "alinan": 0, "hata": ""}
    if psycopg2 is None:
        sonuc["hata"] = "psycopg2 kurulu degil"
        return sonuc
    if not _kilit.acquire(blocking=False):
        sonuc["hata"] = "senkron zaten suruyor"
        return sonuc
    GEÇİCİ = ("statement timeout", "deadlock", "could not obtain lock",
              "server closed the connection", "SSL connection", "operasyon iptal")
    deneme = 0
    while deneme < 2:
        deneme += 1
        pg = None
        try:
            if not yerel_hazirla():
                sonuc["hata"] = "yerel hazirlik basarisiz"
                break
            pg = _pg_baglan(bekleme)
            sunucu_hazirla(pg)
            conn = get_connection()
            try:
                yeni_kurulum = _ilk_kurulum(conn, pg)
                sonuc["yeni_kurulum"] = yeni_kurulum
                makine = makine_adi()
                sonuc["gonderilen"] = _gonder(conn, pg, makine)
                sonuc["alinan"] = _cek(conn, pg, makine)
                sonuc["ok"] = True
                if not sessiz:
                    log_info(
                        f"Senkron tamam: +{sonuc['gonderilen']} gonderildi, "
                        f"+{sonuc['alinan']} alindi ({makine})"
                    )
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            break
        except Exception as e:
            mesaj = str(e) or type(e).__name__
            gecici = any(x in mesaj.lower() for x in GEÇİCİ)
            sonuc["hata"] = mesaj
            log_error("Senkron basarisiz (cevrimdisi devam)", e, __file__, "senkronize")
            if gecici and deneme < 2:
                time.sleep(1.5)  # kilit tutsun birakir; bir kez daha dene
                continue
            break
        finally:
            if pg is not None:
                try:
                    pg.close()
                except Exception:
                    pass
    _kilit.release()
    return sonuc
