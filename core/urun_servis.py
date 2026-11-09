# -*- coding: utf-8 -*-
"""
Urun ve kategori islemleri + Wix CSV ice aktarma
"""

import csv
import re
from pathlib import Path
from datetime import datetime

from core.database import get_connection, barkod_uret, barkod_stoktan, barkod_varyant, barkod_varyant_ek, barkod_normalize, stok_kodundan_sayi, sonraki_stok_sira
import time
import sqlite3


def _db_retry(fn, retries: int = 8, delay: float = 0.15):
    """database is locked icin kisa tekrar dene."""
    son = None
    for i in range(retries):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            son = e
            if "locked" in str(e).lower() and i < retries - 1:
                time.sleep(delay * (i + 1))
                continue
            raise
    if son:
        raise son

from core.logger import log_error, log_info


def kategori_getir_veya_olustur(ad: str, slug: str = "") -> int | None:
    """Kategori yoksa olusturur, id dondurur."""
    if not ad or not ad.strip():
        return None
    ad = ad.strip()
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM kategoriler WHERE ad = ?", (ad,))
        row = cur.fetchone()
        if row:
            kid = row["id"]
            conn.close()
            return kid
        cur.execute(
            "INSERT INTO kategoriler (ad, slug) VALUES (?, ?)",
            (ad, slug or ad.lower().replace(" ", "-"))
        )
        conn.commit()
        kid = cur.lastrowid
        conn.close()
        return kid
    except Exception as e:
        log_error(f"Kategori olusturulamadi: {ad}", e, __file__, "kategori_getir_veya_olustur")
        return None


def kategorileri_listele() -> list:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, ad, slug FROM kategoriler ORDER BY ad")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error("Kategoriler listelenemedi", e, __file__, "kategorileri_listele")
        return []


_ESKI_KOLON = None


def _eski_kolon_var(cur) -> bool:
    global _ESKI_KOLON
    if not _ESKI_KOLON:
        cur.execute("SELECT * FROM urunler LIMIT 0")
        desc = getattr(cur, "description", None) or getattr(getattr(cur, "_cur", None), "description", None) or []
        _ESKI_KOLON = {"eski_barkod", "eski_stok_kodu"} <= {d[0] for d in desc}
    return _ESKI_KOLON


def _birlesik_hedefler(cur, kosul: str, params: list) -> list:
    cur.execute(f"SELECT aciklama FROM urunler WHERE aktif = 0 AND ({kosul})", params)
    hedef = set()
    for r in cur.fetchall():
        m = re.search(r"\[BIRLESTIRILDI\].*\(id (\d+)\)", r["aciklama"] or "")
        if m:
            hedef.add(int(m.group(1)))
    if not hedef:
        return []
    yer = ",".join("?" * len(hedef))
    cur.execute(f"SELECT id, parent_id FROM urunler WHERE aktif = 1 AND id IN ({yer})", sorted(hedef))
    return cur.fetchall()


def eski_kodla_bul(cur, deger: str) -> int | None:
    """Standartlastirma/birlestirme oncesi barkod veya stok koduyla aktif urun id'si."""
    deger = (deger or "").strip()
    if not deger or not _eski_kolon_var(cur):
        return None
    cur.execute(
        "SELECT id FROM urunler WHERE aktif = 1 AND (eski_barkod = ? OR eski_stok_kodu = ?) "
        "ORDER BY CASE WHEN eski_barkod = ? THEN 0 ELSE 1 END LIMIT 1",
        (deger, deger, deger),
    )
    r = cur.fetchone()
    if r:
        return int(r["id"])
    rows = _birlesik_hedefler(cur, "eski_barkod = ? OR eski_stok_kodu = ?", [deger, deger])
    return int(rows[0]["id"]) if rows else None


def _arama_ailesi(cur, arama: str) -> list:
    q = f"%{arama}%"
    kosul = "u.ad LIKE ? OR u.stok_kodu LIKE ? OR u.barkod LIKE ?"
    params = [q, q, q]
    eski = _eski_kolon_var(cur)
    if eski:
        kosul += " OR u.eski_barkod LIKE ? OR u.eski_stok_kodu LIKE ?"
        params.extend([q, q])
    cur.execute(f"SELECT u.id, u.parent_id FROM urunler u WHERE u.aktif = 1 AND ({kosul})", params)
    rows = cur.fetchall()
    if eski:
        rows += _birlesik_hedefler(cur, "eski_barkod LIKE ? OR eski_stok_kodu LIKE ?", [q, q])
    ids = set()
    for r in rows:
        ids.add(int(r["id"]))
        if r["parent_id"]:
            ids.add(int(r["parent_id"]))
    return sorted(ids)


def urunleri_listele(arama: str = "", kategori_id: int | None = None) -> list:
    try:
        conn = get_connection()
        cur = conn.cursor()
        sql = """
            SELECT u.*, k.ad AS kategori_adi
            FROM urunler u
            LEFT JOIN kategoriler k ON k.id = u.kategori_id
            WHERE u.aktif = 1
        """
        params = []
        if arama:
            aile = _arama_ailesi(cur, arama)
            if not aile:
                conn.close()
                return []
            yer = ",".join("?" * len(aile))
            sql += f" AND (u.id IN ({yer}) OR u.parent_id IN ({yer}))"
            params.extend(aile + aile)
        if kategori_id:
            sql += " AND u.kategori_id = ?"
            params.append(kategori_id)
        sql += " ORDER BY u.ad"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error("Urunler listelenemedi", e, __file__, "urunleri_listele")
        return []


def urun_ekle(
    stok_kodu: str,
    ad: str,
    barkod: str | None = None,
    kategori_id: int | None = None,
    marka: str = "",
    beden: str = "",
    renk: str = "",
    alis_fiyati: float = 0,
    satis_fiyati: float = 0,
    stok_adedi: int = 0,
    kritik_stok: int = 3,
    aciklama: str = "",
    kod_paylas: bool = False,
) -> tuple[bool, str]:
    """
    Yeni urun ekler.
    barkod None ise otomatik uretir.
    Donus: (basarili_mi, mesaj)
    """
    try:
        if not ad or not ad.strip():
            return False, "Urun adi bos olamaz"
        ad = ad.strip()

        if not stok_kodu or not stok_kodu.strip():
            # Otomatik stok kodu
            sira = sonraki_stok_sira()
            stok_kodu = f"KZM-{sira:04d}"
        else:
            stok_kodu = stok_kodu.strip()

        if not barkod:
            barkod = barkod_benzersiz(barkod_uret(stok_kodu))

        conn = get_connection()
        cur = conn.cursor()

        # Cakisma kontrolu
        if not kod_paylas:
            cur.execute("SELECT id FROM urunler WHERE stok_kodu = ?", (stok_kodu,))
            if cur.fetchone():
                conn.close()
                return False, f"Stok kodu zaten var: {stok_kodu}"

        cur.execute("SELECT id FROM urunler WHERE barkod = ?", (barkod,))
        if cur.fetchone():
            # Barkod cakisti, yenisini uret
            barkod = barkod_benzersiz(barkod_uret(stok_kodu))

        barkod = barkod_benzersiz(str(barkod).strip() if barkod else barkod_uret(stok_kodu))
        # Barkod UNIQUE — cakisirsa sonuna id benzeri ek
        if barkod:
            base_b = barkod
            n = 0
            while True:
                cur.execute("SELECT id FROM urunler WHERE barkod = ?", (barkod,))
                if not cur.fetchone():
                    break
                n += 1
                barkod = f"{base_b}-{n}"
                if n > 50:
                    barkod = f"{base_b}-{sonraki_stok_sira()}"
                    break

        for _try in range(6):
            try:
                cur.execute("""
                    INSERT INTO urunler (
                        stok_kodu, barkod, ad, kategori_id, marka, beden, renk,
                        alis_fiyati, satis_fiyati, stok_adedi, kritik_stok, aciklama
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    stok_kodu, barkod, ad, kategori_id, marka or None, beden or None,
                    renk or None, float(alis_fiyati or 0), float(satis_fiyati or 0),
                    int(stok_adedi or 0), int(kritik_stok or 3), aciklama or None
                ))
                conn.commit()
                conn.close()
                return True, f"Urun eklendi: {stok_kodu} / {barkod}"
            except sqlite3.IntegrityError as ie:
                msg = str(ie).lower()
                if "barkod" in msg:
                    barkod = barkod_benzersiz(f"{barkod}-r{_try}")
                    continue
                conn.close()
                if "stok_kodu" in msg:
                    return False, f"Stok kodu zaten var: {stok_kodu}"
                return False, str(ie)
        try:
            conn.close()
        except Exception:
            pass
        return False, "Barkod UNIQUE — tekrar deneyin"
    except Exception as e:
        log_error(f"Urun eklenemedi: {ad}", e, __file__, "urun_ekle")
        return False, str(e)


def _temizle_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fiyat_parse(val) -> float:
    if val is None or val == "":
        return 0.0
    try:
        s = str(val).replace(",", ".").strip()
        return float(s)
    except Exception:
        return 0.0


def _stok_parse(val) -> int:
    if val is None or val == "":
        return 0
    s = str(val).strip().upper()
    if s in ("IN_STOCK", "INSTOCK", "TRUE", "YES"):
        return 1
    if s in ("OUT_OF_STOCK", "OUTOFSTOCK", "FALSE", "NO"):
        return 0
    try:
        return max(0, int(float(s.replace(",", "."))))
    except Exception:
        return 0


def wix_csv_aktar(csv_yolu: str | Path) -> dict:
    """
    Wix catalog CSV dosyasini ice aktarir.
    - fieldType == PRODUCT olan satirlari ana urun olarak alir
    - VARIANT satirlari beden/fiyat/stok icin kullanilir
    - Mevcut SKU stok_kodu olur
    - SKU yoksa KZM-XXXX atanir
    - Tum urunlere KZM-AAYYSSS barkod uretilir

    Donus: {ok, eklenen, atlanan, hata, mesaj}
    """
    sonuc = {"ok": False, "eklenen": 0, "atlanan": 0, "hata": 0, "mesaj": ""}
    csv_yolu = Path(csv_yolu)

    if not csv_yolu.exists():
        sonuc["mesaj"] = f"Dosya bulunamadi: {csv_yolu}"
        return sonuc

    try:
        # Once PRODUCT satirlari, sonra VARIANT
        products = {}  # handle -> product dict
        variants = []  # list of variant dicts

        with open(csv_yolu, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                reader.fieldnames = [(fn or "").lstrip("\ufeff") for fn in reader.fieldnames]

            for row in reader:
                # BOM ve bos anahtar temizligi
                row = {((k or "").lstrip("\ufeff")): v for k, v in row.items()}

                ftype = (row.get("fieldType") or "").strip().upper()
                handle = (row.get("handle") or "").strip()
                if not handle:
                    continue

                if ftype == "PRODUCT":
                    name = (row.get("name") or "").strip()
                    if not name:
                        continue
                    cats = (row.get("categorySlugs") or row.get("primaryCategorySlug") or "").strip()
                    cat_ad = cats.split(";")[0].strip() if cats else "Genel"
                    products[handle] = {
                        "handle": handle,
                        "ad": name,
                        "aciklama": _temizle_html(row.get("plainDescription") or ""),
                        "kategori": cat_ad or "Genel",
                        "marka": (row.get("brand") or "KOZMOSIZE").strip() or "KOZMOSIZE",
                        "sku": (row.get("sku") or "").strip(),
                        "fiyat": _fiyat_parse(row.get("price")),
                        "stok": _stok_parse(row.get("inventory")),
                        "beden": "",
                        "renk": "",
                    }
                elif ftype == "VARIANT":
                    variants.append({
                        "handle": handle,
                        "sku": (row.get("sku") or "").strip(),
                        "fiyat": _fiyat_parse(row.get("price")),
                        "stok": _stok_parse(row.get("inventory")),
                        "beden": (row.get("productOptionChoices1") or "").strip(),
                        "renk": (row.get("productOptionChoices2") or "").strip(),
                    })

        # VARIANT bilgilerini ana urune isle (basit: ilk varyanti veya urun seviyesini kullan)
        # Her varyant ayri urun olarak da eklenebilir; simdilik ana urun + beden bilgisi
        for v in variants:
            h = v["handle"]
            if h not in products:
                continue
            p = products[h]
            # SKU varyantta varsa onu tercih et
            if v["sku"] and not p["sku"]:
                p["sku"] = v["sku"]
            if v["fiyat"] > 0:
                p["fiyat"] = v["fiyat"]
            if v["stok"] > 0:
                p["stok"] = v["stok"]
            if v["beden"]:
                p["beden"] = v["beden"]
            if v["renk"]:
                p["renk"] = v["renk"]

        # Toplu kayit - tek baglanti, sira numarasi bellekte
        from datetime import datetime as _dt
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT stok_kodu, barkod FROM urunler")
        rows = cur.fetchall()
        mevcut_kodlar = {r[0] for r in rows}
        mevcut_barkodlar = {r[1] for r in rows if r[1]}

        cur.execute("SELECT deger FROM ayarlar WHERE anahtar = 'son_stok_sira'")
        row = cur.fetchone()
        sira = int(row[0]) if row else 0

        simdi = _dt.now()
        ay = simdi.strftime("%m")
        yil = simdi.strftime("%y")

        kat_cache = {}
        cur.execute("SELECT id, ad FROM kategoriler")
        for r in cur.fetchall():
            kat_cache[r[1]] = r[0]

        for handle, p in products.items():
            try:
                ad = p["ad"]
                stok_kodu = (p["sku"] or "").strip()
                if not stok_kodu:
                    sira += 1
                    stok_kodu = f"KZM-{sira:04d}"

                eski_id = None if stok_kodu in mevcut_kodlar else eski_kodla_bul(cur, stok_kodu)
                if eski_id:
                    cur.execute(
                        """UPDATE urunler SET wix_stok=?, satis_fiyati=COALESCE(NULLIF(?,0), satis_fiyati),
                           guncelleme=datetime('now','localtime')
                           WHERE id=?""",
                        (int(p.get("stok") or 0), float(p.get("fiyat") or 0), eski_id),
                    )
                    sonuc["atlanan"] += 1
                    continue

                if stok_kodu in mevcut_kodlar:
                    # Mevcut urunu Wix stok/fiyat ile guncelle
                    try:
                        cur.execute(
                            """UPDATE urunler SET wix_stok=?, satis_fiyati=COALESCE(NULLIF(?,0), satis_fiyati),
                               guncelleme=datetime('now','localtime')
                               WHERE stok_kodu=?""",
                            (int(p.get("stok") or 0), float(p.get("fiyat") or 0), stok_kodu),
                        )
                        sonuc["atlanan"] += 1  # guncellenen mevcut
                    except Exception:
                        sonuc["atlanan"] += 1
                    continue

                kat_ad = p["kategori"] or "Genel"
                if kat_ad not in kat_cache:
                    cur.execute(
                        "INSERT INTO kategoriler (ad, slug) VALUES (?, ?)",
                        (kat_ad, kat_ad.lower().replace(" ", "-"))
                    )
                    kat_cache[kat_ad] = cur.lastrowid
                kat_id = kat_cache[kat_ad]

                # Benzersiz barkod
                sira += 1
                barkod = f"KZM-{ay}{yil}{sira:03d}"
                while barkod in mevcut_barkodlar:
                    sira += 1
                    barkod = f"KZM-{ay}{yil}{sira:03d}"

                cur.execute("""
                    INSERT INTO urunler (
                        stok_kodu, barkod, ad, kategori_id, marka, beden, renk,
                        alis_fiyati, satis_fiyati, stok_adedi, wix_stok, kritik_stok, aciklama
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, 3, ?)
                """, (
                    stok_kodu, barkod, ad, kat_id,
                    p.get("marka") or "KOZMOSIZE",
                    p.get("beden") or None,
                    p.get("renk") or None,
                    float(p.get("fiyat") or 0),
                    int(p.get("stok") or 0),
                    int(p.get("stok") or 0),
                    (p.get("aciklama") or "")[:500] or None,
                ))
                mevcut_kodlar.add(stok_kodu)
                mevcut_barkodlar.add(barkod)
                sonuc["eklenen"] += 1
            except Exception as e:
                sonuc["hata"] += 1
                log_error(f"Aktarim satir hatasi: {p.get('ad')}", e, __file__, "wix_csv_aktar")

        cur.execute(
            "INSERT INTO ayarlar (anahtar, deger) VALUES ('son_stok_sira', ?) "
            "ON CONFLICT(anahtar) DO UPDATE SET deger = excluded.deger",
            (str(sira),)
        )
        conn.commit()
        conn.close()

        sonuc["ok"] = True
        sonuc["mesaj"] = (
            f"Aktarim bitti. Eklenen: {sonuc['eklenen']}, "
            f"Atlanan (mevcut): {sonuc['atlanan']}, Hata: {sonuc['hata']}"
        )
        log_info(sonuc["mesaj"])
        return sonuc

    except Exception as e:
        log_error("Wix CSV aktarimi basarisiz", e, __file__, "wix_csv_aktar")
        sonuc["mesaj"] = str(e)
        return sonuc


def urun_sayisi() -> int:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM urunler WHERE aktif = 1")
        n = cur.fetchone()["n"]
        conn.close()
        return n
    except Exception:
        return 0


def urun_getir(urun_id: int) -> dict | None:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.*, k.ad AS kategori_adi
            FROM urunler u
            LEFT JOIN kategoriler k ON k.id = u.kategori_id
            WHERE u.id = ?
        """, (urun_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        log_error(f"Urun getirilemedi: {urun_id}", e, __file__, "urun_getir")
        return None


def urun_guncelle(urun_id: int, **kwargs) -> tuple[bool, str]:
    """Urun alanlarini gunceller. Izinli alanlar: ad, stok_kodu, barkod, kategori_id,
    marka, beden, renk, alis_fiyati, satis_fiyati, kritik_stok, aciklama, etsy_stok, trendyol_stok."""
    izinli = {
        "ad", "stok_kodu", "barkod", "kategori_id", "marka", "beden", "renk",
        "alis_fiyati", "satis_fiyati", "kritik_stok", "aciklama",
        "etsy_stok", "trendyol_stok", "wix_stok", "aktif", "gorsel_yolu", "parent_id", "kod_hazir",
    }
    try:
        alanlar = {k: v for k, v in kwargs.items() if k in izinli}
        for zorunlu in ("stok_kodu", "barkod"):
            if zorunlu in alanlar and not str(alanlar[zorunlu] or "").strip():
                del alanlar[zorunlu]
        if not alanlar:
            return False, "Guncellenecek alan yok"
        if "ad" in alanlar and not str(alanlar["ad"]).strip():
            return False, "Urun adi bos olamaz"

        set_parts = []
        vals = []
        for k, v in alanlar.items():
            set_parts.append(f"{k} = ?")
            vals.append(v)
        set_parts.append("guncelleme = datetime('now','localtime')")
        vals.append(urun_id)
        sql = f"UPDATE urunler SET {', '.join(set_parts)} WHERE id = ?"

        def _yaz():
            conn = get_connection()
            try:
                cur = conn.cursor()
                cur.execute(sql, vals)
                conn.commit()
            finally:
                conn.close()

        _db_retry(_yaz)
        return True, "Urun guncellendi"
    except Exception as e:
        log_error(f"Urun guncelleme hatasi: {urun_id}", e, __file__, "urun_guncelle")
        return False, str(e)



def urun_sil(urun_id: int, kalici: bool = False) -> tuple[bool, str]:
    """
    Urun silme.
    kalici=False: soft delete (aktif=0) — satis gecmisi korunur.
    kalici=True: kaydi tamamen siler (FK varsa basarisiz olabilir).
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, ad, stok_kodu, COALESCE(parent_id, 0) AS pid FROM urunler WHERE id = ?",
            (urun_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return False, "Urun bulunamadi"
        cocuk_n = 0
        if kalici:
            cur.execute("DELETE FROM urunler WHERE id = ?", (urun_id,))
        else:
            cur.execute(
                "UPDATE urunler SET aktif = 0, guncelleme = datetime('now','localtime') WHERE id = ?",
                (urun_id,),
            )
            cur.execute(
                "SELECT COUNT(*) AS n FROM urunler WHERE parent_id = ? AND aktif = 1",
                (urun_id,),
            )
            cocuk_n = int(cur.fetchone()["n"] or 0)
            if cocuk_n:
                cur.execute(
                    "UPDATE urunler SET aktif = 0, guncelleme = datetime('now','localtime') WHERE parent_id = ?",
                    (urun_id,),
                )
        conn.commit()
        conn.close()
        log_info(f"Urun silindi ({'kalici' if kalici else 'pasif'}): {row['stok_kodu']} {row['ad']}")
        if not kalici and int(row["pid"] or 0):
            try:
                _bagli_ana_stogu_tazele(int(row["pid"]))
            except Exception:
                pass
        if kalici:
            return True, "Urun silindi"
        mesaj = "Urun listeden cikarildi (pasif)"
        if cocuk_n > 0:
            mesaj += f" ({cocuk_n} varyant da cikarildi)"
        return True, mesaj
    except Exception as e:
        log_error(f"Urun silme hatasi: {urun_id}", e, __file__, "urun_sil")
        return False, str(e)


def urun_gorsel_ata(urun_id: int, kaynak_yol: str) -> tuple[bool, str]:
    """Secilen dosyayi assets/urun_gorselleri icine kopyalar ve gorsel_yolu gunceller."""
    try:
        from pathlib import Path as P
        import shutil
        from core.gorsel_servis import gorsel_klasoru

        src = P(kaynak_yol)
        if not src.is_file():
            return False, "Dosya bulunamadi"
        uz = src.suffix.lower()
        if uz not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
            return False, "Desteklenmeyen dosya turu"

        u = urun_getir(urun_id)
        if not u:
            return False, "Urun bulunamadi"

        hedef_dir = gorsel_klasoru()
        hedef_dir.mkdir(parents=True, exist_ok=True)
        kod = (u.get("stok_kodu") or f"id{urun_id}").replace("/", "-").replace("\\", "-")
        hedef = hedef_dir / f"{kod}{uz}"
        # ayni isim varsa ustune yaz
        shutil.copy2(str(src), str(hedef))

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE urunler SET gorsel_yolu = ?, guncelleme = datetime('now','localtime') WHERE id = ?",
            (str(hedef), urun_id),
        )
        conn.commit()
        conn.close()
        log_info(f"Gorsel atandi: {kod} -> {hedef.name}")
        return True, str(hedef)
    except Exception as e:
        log_error(f"Gorsel atama hatasi: {urun_id}", e, __file__, "urun_gorsel_ata")
        return False, str(e)


def varyant_ana_stok_toplam_yaz(cur, parent_id: int) -> None:
    """Acik cursor uzerinde ana stok_adedi = aktif varyant toplami (mutlak)."""
    cur.execute(
        """
        UPDATE urunler SET
            stok_adedi = (
                SELECT COALESCE(SUM(v.stok_adedi), 0)
                FROM urunler v WHERE v.parent_id = ? AND v.aktif = 1
            ),
            guncelleme = datetime('now','localtime')
        WHERE id = ?
          AND EXISTS (
                SELECT 1 FROM urunler c
                WHERE c.parent_id = urunler.id AND c.aktif = 1
          )
        """,
        (int(parent_id), int(parent_id)),
    )


def varyant_ana_stok_guncelle(parent_id: int) -> None:
    """
    Varyant magaza stoklarini ana urune topla:
    ana urunun stok_adedi = SUM(aktif varyantlarin stok_adedi).
    Urunun aktif cocugu yoksa dokunmaz (tekil urun stogu korunur).
    """
    try:
        pid = int(parent_id)
        if pid <= 0:
            return
        conn = get_connection()
        cur = conn.cursor()
        varyant_ana_stok_toplam_yaz(cur, pid)
        conn.commit()
        conn.close()
    except Exception as e:
        log_error("Varyant ana stok senkron", e, __file__, "varyant_ana_stok_guncelle")


def _bagli_ana_stogu_tazele(urun_id: int) -> None:
    """Degisen urunin bagli oldugu ana urunun (varsa) stogunu varyant toplamina ceker."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(parent_id, 0) AS p FROM urunler WHERE id = ?", (urun_id,))
        r = cur.fetchone()
        conn.close()
        if not r:
            return
        p = int(r["p"] or 0)
        varyant_ana_stok_guncelle(p if p else urun_id)
    except Exception as e:
        log_error("Bagli ana stok tazele", e, __file__, "_bagli_ana_stogu_tazele")


def stok_duzelt(
    urun_id: int,
    yeni_stok: int | None = None,
    fark: int | None = None,
    aciklama: str = "",
    kanal: str = "magaza",
) -> tuple[bool, str]:
    """
    Stok girisi / duzeltme.
    yeni_stok: mutlak deger atanir
    fark: +giris / -cikis
    kanal: magaza | etsy | trendyol
    """
    try:
        conn = get_connection()
        cur = conn.cursor()

        if kanal == "etsy":
            kolon = "etsy_stok"
        elif kanal == "trendyol":
            kolon = "trendyol_stok"
        elif kanal == "wix":
            kolon = "wix_stok"
        else:
            kolon = "stok_adedi"

        cur.execute(
            f"SELECT id, ad, {kolon} AS stok, COALESCE(parent_id, 0) AS pid FROM urunler WHERE id = ?",
            (urun_id,),
        )
        u = cur.fetchone()
        if not u:
            conn.close()
            return False, "Urun bulunamadi"

        if kolon == "stok_adedi":
            cur.execute(
                "SELECT COUNT(*) AS n FROM urunler WHERE parent_id = ? AND aktif = 1",
                (urun_id,),
            )
            if int(cur.fetchone()["n"] or 0) > 0:
                conn.close()
                return False, (
                    "Bu urunun varyantlari var: ana adet varyant toplamindan otomatik hesaplanir. "
                    "Adedi varyant satirlarina girin."
                )

        eski = int(u["stok"] or 0)
        pid = int(u["pid"] or 0)
        if yeni_stok is not None:
            hedef = max(0, int(yeni_stok))
            delta = hedef - eski
        elif fark is not None:
            delta = int(fark)
            hedef = max(0, eski + delta)
            delta = hedef - eski
        else:
            conn.close()
            return False, "yeni_stok veya fark gerekli"

        cur.execute(
            f"UPDATE urunler SET {kolon} = ?, guncelleme = datetime('now','localtime') WHERE id = ?",
            (hedef, urun_id)
        )
        cur.execute("""
            INSERT INTO stok_hareketleri (urun_id, hareket_tipi, adet, aciklama)
            VALUES (?, ?, ?, ?)
        """, (
            urun_id,
            "duzeltme" if yeni_stok is not None else ("giris" if delta >= 0 else "cikis"),
            delta,
            f"[{kanal}] {aciklama or 'Stok duzeltme'} (eski:{eski} -> {hedef})",
        ))
        if kolon == "stok_adedi" and pid and pid != int(urun_id):
            varyant_ana_stok_toplam_yaz(cur, pid)
        conn.commit()
        conn.close()
        log_info(f"Stok duzeltme [{kanal}] {u['ad']}: {eski} -> {hedef}")
        ekstra = ""
        if kanal == "magaza" and eski <= 0 and hedef > 0:
            ok_kod, msg_kod = stok_girisinde_kod_ata(urun_id)
            if ok_kod and "Kod atandi" in msg_kod:
                ekstra = f" | {msg_kod}"
        return True, f"{u['ad']}: {eski} → {hedef}{ekstra}"
    except Exception as e:
        log_error("Stok duzeltme hatasi", e, __file__, "stok_duzelt")
        return False, str(e)


def kritik_stok_listesi() -> list:
    """Stok adedi kritik_stok seviyesinde veya altinda olan urunler."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.stok_kodu, u.barkod, u.ad, u.stok_adedi, u.kritik_stok,
                   k.ad AS kategori_adi
            FROM urunler u
            LEFT JOIN kategoriler k ON k.id = u.kategori_id
            WHERE u.aktif = 1 AND u.stok_adedi <= COALESCE(u.kritik_stok, 3)
            ORDER BY u.stok_adedi ASC, u.ad
        """)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error("Kritik stok listesi hatasi", e, __file__, "kritik_stok_listesi")
        return []


# ---------------------------------------------------------------------------
# Varyant + barkod/stok uyumu
# ---------------------------------------------------------------------------

def stok_kodu_varyant(ana_kod: str, varyant_eki: str) -> str:
    """KZM-1445 + L -> KZM-1445L. Ek bos ise ana kod aynen."""
    ana = (ana_kod or "").strip().upper()
    ek = (varyant_eki or "").strip().upper().replace(" ", "")
    if not ek:
        return ana
    if ana.endswith(ek):
        return ana
    return f"{ana}{ek}"


def barkod_benzersiz(aday: str, haric_id: int | None = None) -> str:
    """UNIQUE barkod garantisi — cakisirsa sonek + zaman damgasi.

    Karsilastirma 'KZM-' onegi yok sayilarak yapilir; eski onekli kayitlarla
    ayni barkodun iki kez uretilmesini engeller.
    """
    import time
    aday = (aday or "").strip()
    if not aday:
        aday = barkod_uret()
    conn = get_connection()
    try:
        cur = conn.cursor()
        deneme = aday
        for n in range(0, 80):
            if n > 0:
                deneme = f"{aday}-{n}"
            duz = barkod_normalize(deneme)
            onekli = f"KZM-{duz}"
            if haric_id is not None:
                cur.execute(
                    "SELECT id FROM urunler WHERE (barkod = ? OR barkod = ? OR barkod = ?) AND id != ?",
                    (deneme, duz, onekli, haric_id),
                )
            else:
                cur.execute(
                    "SELECT id FROM urunler WHERE barkod = ? OR barkod = ? OR barkod = ?",
                    (deneme, duz, onekli),
                )
            if not cur.fetchone():
                return deneme
        return f"{aday}-{int(time.time()) % 1000000}"
    finally:
        conn.close()


def barkod_stok_uyumlu_mu(stok_kodu: str, barkod: str) -> bool:
    """KZM-YYMM{stok}{vv} formati: stok sayisi barkodda gecmeli."""
    sayi = stok_kodundan_sayi(stok_kodu)
    b = (barkod or "").upper().replace(" ", "")
    if not sayi or not b:
        return False
    return b.startswith("KZM-") and sayi in b and len(b) >= 10


def urun_cogalt(urun_id: int, beden: str = "", renk: str = "", varyant_eki: str = "") -> tuple[bool, str]:
    """
    Urunu kopyalar (stok=0).
    varyant_eki bos ise varsayilan L/XL/M EKLENMEZ; yeni benzersiz stok kodu uretilir.
    Ek doluysa: KZM-1445 + L -> KZM-1445L (rakamdan sonra olcu).
    """
    try:
        u = urun_getir(urun_id)
        if not u:
            return False, "Urun bulunamadi"
        ana_kod = (u.get("stok_kodu") or "").strip()
        # Sadece kullanicinin yazdigi ek — bos ise beden varsayilani kullanma
        ek = (varyant_eki or "").strip().upper()
        if not ek and beden:
            ek = beden.strip().upper()
        if ek:
            yeni_kod = stok_kodu_varyant(ana_kod, ek)
        else:
            # varsayilan olcu yok — yeni sira kodu
            sira = sonraki_stok_sira()
            yeni_kod = f"KZM-{sira:04d}"
        # cakisma
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM urunler WHERE stok_kodu = ?", (yeni_kod,))
        if cur.fetchone():
            conn.close()
            return False, f"Stok kodu zaten var: {yeni_kod}"
        conn.close()

        parent = u.get("parent_id") or urun_id
        ok, msg = urun_ekle(
            stok_kodu=yeni_kod,
            ad=u.get("ad") or "",
            barkod=barkod_benzersiz(barkod_stoktan(yeni_kod)),
            kategori_id=u.get("kategori_id"),
            marka=u.get("marka") or "",
            beden=beden or u.get("beden") or ek,
            renk=renk or u.get("renk") or "",
            alis_fiyati=float(u.get("alis_fiyati") or 0),
            satis_fiyati=float(u.get("satis_fiyati") or 0),
            stok_adedi=0,
            kritik_stok=int(u.get("kritik_stok") or 3),
            aciklama=u.get("aciklama") or "",
        )
        if not ok:
            return False, msg
        # parent_id bagla
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE urunler SET parent_id = ?, kod_hazir = 1, gorsel_yolu = ? WHERE stok_kodu = ?",
            (parent, u.get("gorsel_yolu"), yeni_kod),
        )
        conn.commit()
        conn.close()
        return True, f"Cogaltildi: {yeni_kod} (stok 0)"
    except Exception as e:
        log_error("Urun cogalt", e, __file__, "urun_cogalt")
        return False, str(e)



def sonraki_varyant_no(parent_id: int) -> int:
    """Ana urun altindaki sonraki varyant sira no (0,1,2...)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) AS n FROM urunler WHERE aktif=1 AND parent_id = ?",
            (parent_id,),
        )
        n = int(cur.fetchone()["n"] or 0)
        conn.close()
        return n
    except Exception:
        return 0


def varyant_ekle(
    parent_id: int,
    beden: str,
    renk: str = "",
    stok_adedi: int = 0,
    varyant_eki: str | None = None,
) -> tuple[bool, str]:
    """
    Ana urun altina varyant.
    Barkod: KZM-YYMM{stok}{vv} (vv = 00,01,...)
    Stok kodu ana urunun stok numarasi ile ayni kalabilir; satis barkod ile yapilir.
    """
    try:
        parent = urun_getir(parent_id)
        if not parent:
            return False, "Ana urun yok"
        beden = (beden or "").strip().upper()
        ana_kod = (parent.get("stok_kodu") or "").strip()
        if not ana_kod:
            return False, "Ana urunde stok kodu yok"
        vv = sonraki_varyant_no(parent_id)
        stok_adedi = int(stok_adedi or 0)
        barkod = barkod_benzersiz(barkod_varyant_ek(ana_kod, beden or (varyant_eki or ""), vv))
        from core.denetci_servis import cocuk_stok_kodu, kod_paylasilabilir
        yeni_kod = cocuk_stok_kodu(ana_kod, vv)
        paylas = kod_paylasilabilir()
        if not paylas:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM urunler WHERE stok_kodu = ?", (yeni_kod,))
            if cur.fetchone():
                conn.close()
                return False, f"Kod cakismasi: {yeni_kod}"
            conn.close()

        ok, msg = urun_ekle(
            stok_kodu=yeni_kod,
            ad=parent.get("ad") or "",
            barkod=barkod,
            kategori_id=parent.get("kategori_id"),
            marka=parent.get("marka") or "",
            beden=beden or (varyant_eki or ""),
            renk=renk or "",
            alis_fiyati=float(parent.get("alis_fiyati") or 0),
            satis_fiyati=float(parent.get("satis_fiyati") or 0),
            stok_adedi=stok_adedi,
            kritik_stok=int(parent.get("kritik_stok") or 3),
            aciklama=parent.get("aciklama") or "",
            kod_paylas=paylas,
        )
        if not ok:
            return False, msg
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE urunler SET parent_id = ?, kod_hazir = 1, gorsel_yolu = ? WHERE barkod = ?",
            (parent_id, parent.get("gorsel_yolu"), barkod),
        )
        conn.commit()
        conn.close()
        varyant_ana_stok_guncelle(parent_id)
        return True, f"Varyant eklendi: {barkod} (beden={beden or '-'}, stok={stok_adedi})"
    except Exception as e:
        log_error("Varyant ekle", e, __file__, "varyant_ekle")
        return False, str(e)


def varyantlari_listele(parent_id: int) -> list:
    """Ana urun + alt varyantlar (barkod, beden, adet)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM urunler
            WHERE aktif = 1 AND (id = ? OR parent_id = ?)
            ORDER BY
              CASE WHEN id = ? THEN 0 ELSE 1 END,
              beden, barkod
        """, (parent_id, parent_id, parent_id))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error("Varyant liste", e, __file__, "varyantlari_listele")
        return []


def varyant_sil(varyant_id: int, parent_id: int | None = None) -> tuple[bool, str]:
    """Varyanti pasife alir (soft delete). Ana urunu silmez, satis gecmisi korunur."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, ad, stok_kodu, parent_id FROM urunler WHERE id = ?",
            (varyant_id,)
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return False, "Varyant bulunamadi"
        if parent_id is not None and row["parent_id"] != parent_id:
            conn.close()
            return False, "Varyant bu urune ait degil"
        cur.execute(
            "UPDATE urunler SET aktif = 0, guncelleme = datetime('now','localtime') WHERE id = ?",
            (varyant_id,),
        )
        conn.commit()
        conn.close()
        log_info(f"Varyant silindi (pasif): {row['stok_kodu']} {row['ad']}")
        return True, "Varyant listeden cikarildi"
    except Exception as e:
        log_error(f"Varyant sil hatasi: {varyant_id}", e, __file__, "varyant_sil")
        return False, str(e)


def ana_urunleri_listele(arama: str = "", kategori_id=None) -> list:
    """Sadece ana urunler (parent_id IS NULL) — magaza arama."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        sql = """
            SELECT u.*, k.ad AS kategori_adi,
              COUNT(v.id) AS varyant_sayisi
            FROM urunler u
            LEFT JOIN kategoriler k ON k.id = u.kategori_id
            LEFT JOIN urunler v ON v.parent_id = u.id AND v.aktif = 1
            WHERE u.aktif = 1 AND (u.parent_id IS NULL OR u.parent_id = 0)
        """
        params = []
        if arama:
            q = f"%{arama}%"
            sql += " AND (u.ad LIKE ? OR u.stok_kodu LIKE ? OR u.barkod LIKE ?)"
            params.extend([q, q, q])
        if kategori_id:
            sql += " AND u.kategori_id = ?"
            params.append(kategori_id)
        sql += " GROUP BY u.id, k.id"
        sql += " ORDER BY u.ad LIMIT 40"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error("Ana urun liste", e, __file__, "ana_urunleri_listele")
        return []


def barkodlari_yeni_formata_cevir() -> dict:
    """
    Tum aktif urunlerin barkodlarini KZM-YYMM{stok}{vv} formatina cevirir.
    Ana urun: vv=00, alt varyantlar sira ile 01,02...
    """
    sonuc = {"ok": False, "guncellenen": 0, "hata": 0, "mesaj": ""}
    try:
        conn = get_connection()
        cur = conn.cursor()
        # Ana urunler
        cur.execute("""
            SELECT id, stok_kodu FROM urunler
            WHERE aktif=1 AND (parent_id IS NULL OR parent_id = 0)
            ORDER BY id
        """)
        analar = [dict(r) for r in cur.fetchall()]
        n = 0
        for ana in analar:
            aid = ana["id"]
            sk = ana["stok_kodu"] or ""
            # ana barkod vv=00
            b0 = barkod_benzersiz(barkod_varyant(sk, 0), haric_id=aid)
            cur.execute(
                "UPDATE urunler SET barkod=?, kod_hazir=1, guncelleme=datetime('now','localtime') WHERE id=?",
                (b0, aid),
            )
            n += 1
            # varyantlar
            cur.execute(
                "SELECT id, stok_kodu FROM urunler WHERE aktif=1 AND parent_id=? ORDER BY id",
                (aid,),
            )
            vars_ = [dict(r) for r in cur.fetchall()]
            for i, v in enumerate(vars_):
                vv = i + 1  # 01, 02...
                b = barkod_benzersiz(barkod_varyant(sk, vv), haric_id=v["id"])
                cur.execute(
                    "UPDATE urunler SET barkod=?, kod_hazir=1, guncelleme=datetime('now','localtime') WHERE id=?",
                    (b, v["id"]),
                )
                n += 1
        # parent_id olmayan eski kayitlar zaten isledi
        # parent_id olan ama anasi silinmis
        cur.execute("""
            SELECT id, stok_kodu, parent_id FROM urunler
            WHERE aktif=1 AND parent_id IS NOT NULL AND parent_id != 0
              AND parent_id NOT IN (SELECT id FROM urunler WHERE aktif=1)
        """)
        yetim = [dict(r) for r in cur.fetchall()]
        for y in yetim:
            b = barkod_benzersiz(barkod_varyant(y["stok_kodu"] or "KZM-0000", 0), haric_id=y["id"])
            cur.execute("UPDATE urunler SET barkod=? WHERE id=?", (b, y["id"]))
            n += 1
        conn.commit()
        conn.close()
        sonuc["ok"] = True
        sonuc["guncellenen"] = n
        sonuc["mesaj"] = f"{n} barkod yeni formata cevrildi (KZM-YYMM+stok+vv)"
        log_info(sonuc["mesaj"])
        return sonuc
    except Exception as e:
        log_error("Barkod toplu cevir", e, __file__, "barkodlari_yeni_formata_cevir")
        sonuc["mesaj"] = str(e)
        return sonuc



def stok_girisinde_kod_ata(urun_id: int) -> tuple[bool, str]:
    """Stok 0->pozitif olunca kod_hazir=0 varyanta gercek stok/barkod verir."""
    try:
        u = urun_getir(urun_id)
        if not u:
            return False, "Urun yok"
        if int(u.get("kod_hazir") or 1) == 1:
            return True, "Kod zaten hazir"
        if int(u.get("stok_adedi") or 0) <= 0:
            return False, "Once stok girin"
        parent = urun_getir(u.get("parent_id")) if u.get("parent_id") else None
        ana_kod = (parent or u).get("stok_kodu") or "KZM-0000"
        # gecici degilse ana
        if str(ana_kod).startswith("_TMP"):
            ana_kod = f"KZM-{sonraki_stok_sira():04d}"
        ek = (u.get("beden") or "").strip().upper()
        yeni_kod = stok_kodu_varyant(ana_kod if not str(ana_kod).startswith("_TMP") else f"KZM-{sonraki_stok_sira():04d}", ek)
        # parent stok kodu TMP degil
        if parent and not str(parent.get("stok_kodu") or "").startswith("_TMP"):
            yeni_kod = stok_kodu_varyant(parent.get("stok_kodu"), ek)
        barkod = barkod_stoktan(yeni_kod)
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM urunler WHERE stok_kodu = ? AND id != ?", (yeni_kod, urun_id))
        if cur.fetchone():
            conn.close()
            return False, f"Kod cakismasi: {yeni_kod}"
        cur.execute(
            "UPDATE urunler SET stok_kodu = ?, barkod = ?, kod_hazir = 1, "
            "guncelleme = datetime('now','localtime') WHERE id = ?",
            (yeni_kod, barkod, urun_id),
        )
        conn.commit()
        conn.close()
        return True, f"Kod atandi: {yeni_kod} / {barkod}"
    except Exception as e:
        log_error("Kod ata", e, __file__, "stok_girisinde_kod_ata")
        return False, str(e)


def barkod_yenile_onayli(urun_id: int, onay: bool) -> tuple[bool, str]:
    """
    Onay=True: stok koduna uyumlu yeni barkod dogrudan yazar.
    Onay=False: eski barkod korunur.
    """
    try:
        u = urun_getir(urun_id)
        if not u:
            return False, "Urun yok"
        if not onay:
            return True, "Barkod degistirilmedi (iptal)"
        kod = (u.get("stok_kodu") or "").strip()
        if not kod or str(kod).startswith("_TMP"):
            return False, "Gecerli stok kodu yok"
        # kod_hazir 0 olsa bile barkod stoktan turetilebilir
        yeni = barkod_stoktan(kod)
        if not yeni:
            return False, "Barkod uretilemedi"

        yeni = barkod_benzersiz(yeni, haric_id=urun_id)

        def _yaz_barkod(barkod_deger: str):
            conn = get_connection()
            try:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE urunler SET barkod = ?, kod_hazir = 1, "
                    "guncelleme = datetime('now','localtime') WHERE id = ?",
                    (barkod_deger, urun_id),
                )
                conn.commit()
                return barkod_deger
            finally:
                conn.close()

        son = _db_retry(lambda: _yaz_barkod(yeni))
        # dogrula
        u2 = urun_getir(urun_id)
        gercek = (u2 or {}).get("barkod") or ""
        if gercek != son and gercek != yeni:
            return False, f"Kayit dogrulanamadi (DB: {gercek})"
        return True, f"Yeni barkod kaydedildi: {gercek or son}"
    except Exception as e:
        log_error("Barkod yenile", e, __file__, "barkod_yenile_onayli")
        return False, str(e)


def barkod_uyumsuz_liste() -> list:
    """Barkod yok veya stok kodu ile uyumsuz urunler."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, stok_kodu, barkod, ad, stok_adedi
            FROM urunler WHERE aktif = 1
            ORDER BY ad
        """)
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            bk = d.get("barkod") or ""
            sk = d.get("stok_kodu") or ""
            if sk.startswith("_TMP"):
                continue
            if not bk or bk.startswith("_TMP") or not barkod_stok_uyumlu_mu(sk, bk):
                d["oneri_barkod"] = barkod_stoktan(sk)
                rows.append(d)
        conn.close()
        return rows
    except Exception as e:
        log_error("Barkod uyumsuz liste", e, __file__, "barkod_uyumsuz_liste")
        return []


def barkod_toplu_duzelt(sadece_oneri: bool = False) -> dict:
    """Tum uyumsuzlari stok koduna gore duzeltir."""
    liste = barkod_uyumsuz_liste()
    if sadece_oneri:
        return {"ok": True, "adet": len(liste), "liste": liste}
    n = 0
    for u in liste:
        ok, _ = barkod_yenile_onayli(u["id"], True)
        if ok:
            n += 1
    return {"ok": True, "duzeltilen": n, "toplam": len(liste)}


def barkod_olustur_toplu(urun_ids: list | None = None) -> dict:
    """
    Eksik/uyumsuz barkodlari yeni formata cevirir.
    Ana urun: KZM-YYMM{stok no} (KZM-26111455) — Varyant: KZM-YYMM{stok no}{BEDEn} (KZM-26111455L).
    Beden turetilemezse kardes sirasi (01,02..). urun_ids None -> tum aktif urunler.
    """
    import re
    sonuc = {"ok": False, "duzeltilen": 0, "toplam": 0, "atlanan": 0, "hatalar": [], "mesaj": ""}
    try:
        conn = get_connection()
        cur = conn.cursor()
        if urun_ids:
            ids = [int(i) for i in urun_ids]
            placeholders = ",".join("?" * len(ids))
            cur.execute(
                f"""SELECT id, stok_kodu, barkod, beden, parent_id FROM urunler
                    WHERE aktif = 1 AND id IN ({placeholders})""",
                ids,
            )
        else:
            cur.execute(
                "SELECT id, stok_kodu, barkod, beden, parent_id FROM urunler WHERE aktif = 1 ORDER BY id"
            )
        hedefler = [dict(r) for r in cur.fetchall()]
        sonuc["toplam"] = len(hedefler)
        for u in hedefler:
            uid = int(u["id"])
            sk = (u["stok_kodu"] or "").strip()
            if sk.startswith("_TMP"):
                sonuc["atlanan"] += 1
                continue
            if not sk:
                sk = f"KZM-{sonraki_stok_sira():04d}"
                try:
                    cur.execute(
                        "UPDATE urunler SET stok_kodu = ?, guncelleme = datetime('now','localtime') WHERE id = ?",
                        (sk, uid),
                    )
                except sqlite3.IntegrityError:
                    sonuc["hatalar"].append(f"id {uid}: stok kodu atanamadi ({sk} cakisma)")
                    continue
            sayi = stok_kodundan_sayi(re.sub(r"-V\d+$", "", sk))
            eski = (u["barkod"] or "").strip().upper()
            ek = re.sub(r"[^A-Z0-9]", "", (u["beden"] or "").upper())
            pid = int(u["parent_id"] or 0)
            if ek and pid:
                m = re.search(r"(\d)([A-Z]+)$", sk.upper())
                if m and m.group(2) != ek:
                    ek = ""
            if pid and not ek:
                m = re.search(r"(\d)([A-Z]+)$", sk.upper())
                if m:
                    ek = m.group(2)
            if pid and not ek:
                cur.execute(
                    "SELECT id FROM urunler WHERE parent_id = ? AND aktif = 1 ORDER BY id",
                    (pid,),
                )
                kardesler = [int(r["id"]) for r in cur.fetchall()]
                if uid in kardesler:
                    ek = f"{kardesler.index(uid) + 1:02d}"
            if not pid:
                ek = ""
            if ek:
                aday = barkod_varyant_ek(re.sub(r"-V\d+$", "", sk), ek, 0)
            else:
                aday = barkod_varyant_ek(re.sub(r"-V\d+$", "", sk), "", 0)[:-2]
            pattern = rf"^KZM-\d{{4}}{re.escape(sayi)}{re.escape(ek) if ek else ''}$"
            if eski and re.fullmatch(pattern, eski, flags=re.IGNORECASE):
                sonuc["atlanan"] += 1
                continue
            yeni = barkod_benzersiz(aday, haric_id=uid)
            cur.execute(
                "UPDATE urunler SET barkod = ?, kod_hazir = 1, guncelleme = datetime('now','localtime') WHERE id = ?",
                (yeni, uid),
            )
            sonuc["duzeltilen"] += 1
        conn.commit()
        conn.close()
        sonuc["ok"] = True
        sonuc["mesaj"] = (
            f"{sonuc['duzeltilen']} barkod olusturuldu/guncellendi, "
            f"{sonuc['atlanan']} zaten uyumlu"
        )
        log_info(sonuc["mesaj"])
        return sonuc
    except Exception as e:
        log_error("Barkod olustur toplu", e, __file__, "barkod_olustur_toplu")
        sonuc["mesaj"] = str(e)
        return sonuc


def barkod_gosterim(barkod: str, stok_kodu: str = "") -> str:
    """Magaza kartinda size harfi olmadan: KZM-26111422L -> KZM-26111422"""
    import re
    b = (barkod or stok_kodu or "").strip().upper()
    if not b:
        return ""
    # sondaki beden harflerini (S/M/L/XL/L/XL) kaldir
    b = re.sub(r"(L/XL|XL|XXL|XS|S|M|L)+$", "", b)
    return b.rstrip("-/")


def varyantlari_bedene_gore(parent_veya_id: int) -> dict:
    """
    { 'S': urun_dict, 'M': ..., 'L': ..., 'XL': ... }
    Ana urun + parent_id eslesenler.
    """
    rows = varyantlari_listele(parent_veya_id)
    if not rows:
        u = urun_getir(parent_veya_id)
        rows = [u] if u else []
    sonuc = {}
    for r in rows:
        if not r:
            continue
        bed = (r.get("beden") or "").strip().upper()
        # stok kodundan beden cikar
        if not bed:
            import re
            sk = (r.get("stok_kodu") or "").upper()
            m = re.search(r"(XL|XXL|XS|S|M|L)(/XL)?$", sk)
            if m:
                bed = m.group(0)
        if bed:
            sonuc[bed] = r
        else:
            sonuc["_ANA"] = r
    return sonuc
