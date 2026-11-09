# -*- coding: utf-8 -*-
"""
Satis, masraf ve gunluk ozet islemleri
"""

from datetime import date
from core.database import get_connection, barkod_normalize
from core.logger import log_error, log_info
from core.urun_servis import varyant_ana_stok_toplam_yaz


def urun_bul_kod(kod: str) -> dict | None:
    """Barkod veya stok kodu ile urun bulur. Tam eslesme oncelikli.

    Barkod artik 'KZM-' onegi olmadan uretiliyor; eski etiketler onekli
    okutulabildigi icin her iki bicim de kabul edilir.
    """
    kod = (kod or "").strip()
    if not kod:
        return None
    duz = barkod_normalize(kod)
    onekli = f"KZM-{duz}"
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.*, k.ad AS kategori_adi
            FROM urunler u
            LEFT JOIN kategoriler k ON k.id = u.kategori_id
            WHERE u.aktif = 1
              AND (u.barkod = ? OR u.stok_kodu = ? OR u.barkod = ? OR u.barkod = ?)
            ORDER BY CASE WHEN u.barkod = ? THEN 0
                          WHEN u.barkod = ? THEN 1
                          WHEN u.barkod = ? THEN 2 ELSE 3 END
            LIMIT 1
        """, (kod, kod, duz, onekli, kod, duz, onekli))
        row = cur.fetchone()
        if row:
            conn.close()
            return dict(row)
        if duz != kod:
            cur.execute("""
                SELECT u.*, k.ad AS kategori_adi
                FROM urunler u
                LEFT JOIN kategoriler k ON k.id = u.kategori_id
                WHERE u.aktif = 1 AND (u.barkod = ? OR u.stok_kodu = ?)
                LIMIT 1
            """, (duz, duz))
            row = cur.fetchone()
            if row:
                conn.close()
                return dict(row)
        # Son 4 hane (sadece rakam) — barkod/stok sonunda
        if kod.isdigit() and len(kod) == 4:
            cur.execute("""
                SELECT u.*, k.ad AS kategori_adi
                FROM urunler u
                LEFT JOIN kategoriler k ON k.id = u.kategori_id
                WHERE u.aktif = 1 AND (
                    u.barkod LIKE ? OR u.stok_kodu LIKE ?
                    OR replace(replace(u.barkod,'KZM-',''), ' ', '') LIKE ?
                    OR u.stok_kodu LIKE ?
                )
                LIMIT 15
            """, (f"%{kod}%", f"%{kod}%", f"%{kod}%", f"%{kod}%"))
            rows = cur.fetchall()
            conn.close()
            if len(rows) == 1:
                return dict(rows[0])
            return None  # coklu eslesme -> isim aramasina birak
        conn.close()
        return None
    except Exception as e:
        log_error(f"Urun arama hatasi: {kod}", e, __file__, "urun_bul_kod")
        return None


def urun_ara_isim(metin: str = "", kategori_id: int | None = None, limit: int = 40) -> list:
    """Isim / kod ile urun arar. metin bos + kategori seciliyse o kategoriyi listeler."""
    metin = (metin or "").strip()
    try:
        conn = get_connection()
        cur = conn.cursor()
        sql = """
            SELECT id, stok_kodu, barkod, ad, satis_fiyati, stok_adedi, beden, kategori_id, gorsel_yolu
            FROM urunler
            WHERE aktif = 1
        """
        params: list = []
        if metin:
            q = f"%{metin}%"
            sql += " AND (ad LIKE ? OR stok_kodu LIKE ? OR barkod LIKE ?)"
            params.extend([q, q, q])
        if kategori_id:
            sql += " AND kategori_id = ?"
            params.append(kategori_id)
        if not metin and not kategori_id:
            conn.close()
            return []
        sql += " ORDER BY ad LIMIT ?"
        params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error(f"Isim arama hatasi: {metin}", e, __file__, "urun_ara_isim")
        return []


def yeni_fis_no() -> str:
    """Tek musteri sepeti icin benzersiz fis numarasi."""
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d%H%M%S%f")


def satis_yap(
    urun_id: int,
    adet: int,
    birim_fiyat: float,
    indirim: float,
    odeme_tipi: str,
    fis_no: str | None = None,
    banka: str | None = None,
) -> tuple[bool, str]:
    """
    Satis kaydeder, stok dusurur.
    odeme_tipi: nakit | kart
    banka: Akbank | Yapikredi (kart ise)
    fis_no: ayni sepet kalemlerini gruplar
    """
    try:
        adet = int(adet)
        if adet <= 0:
            return False, "Adet 0'dan buyuk olmali"
        indirim = float(indirim or 0)
        birim_fiyat = float(birim_fiyat)
        toplam = max(0.0, (birim_fiyat * adet) - indirim)
        odeme_tipi = (odeme_tipi or "nakit").lower()
        if odeme_tipi not in ("nakit", "kart"):
            odeme_tipi = "nakit"
        banka = (banka or "").strip() or None
        if odeme_tipi != "kart":
            banka = None
        if not fis_no:
            fis_no = yeni_fis_no()

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT id, ad, stok_adedi FROM urunler WHERE id = ? AND aktif = 1", (urun_id,))
        urun = cur.fetchone()
        if not urun:
            conn.close()
            return False, "Urun bulunamadi"

        if urun["stok_adedi"] < adet:
            conn.close()
            return False, f"Yetersiz stok. Mevcut: {urun['stok_adedi']}"

        cur.execute(
            "SELECT COUNT(*) AS n FROM urunler WHERE parent_id = ? AND aktif = 1",
            (urun_id,),
        )
        if int(cur.fetchone()["n"] or 0) > 0:
            conn.close()
            return False, "Varyantli urun dogrudan satilamaz; varyant (beden) secin"

        cur.execute("""
            INSERT INTO satislar (urun_id, adet, birim_fiyat, indirim, odeme_tipi, toplam, fis_no, banka)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (urun_id, adet, birim_fiyat, indirim, odeme_tipi, toplam, fis_no, banka))

        cur.execute(
            "UPDATE urunler SET stok_adedi = stok_adedi - ?, guncelleme = datetime('now','localtime') WHERE id = ?",
            (adet, urun_id)
        )
        cur.execute(
            "SELECT COALESCE(parent_id, 0) AS parent_id FROM urunler WHERE id = ?",
            (urun_id,),
        )
        bag = cur.fetchone()
        pid = int(bag["parent_id"] or 0) if bag else 0
        if pid and pid != int(urun_id):
            varyant_ana_stok_toplam_yaz(cur, pid)

        cur.execute("""
            INSERT INTO stok_hareketleri (urun_id, hareket_tipi, adet, aciklama)
            VALUES (?, 'satis', ?, ?)
        """, (urun_id, -adet, f"Fis {fis_no} / {odeme_tipi}"))

        conn.commit()
        conn.close()
        log_info(f"Satis: {urun['ad']} x{adet} = {toplam} TL ({odeme_tipi}) fis={fis_no}")
        return True, f"{urun['ad']} satildi. {toplam:,.0f} TL"
    except Exception as e:
        log_error("Satis hatasi", e, __file__, "satis_yap")
        return False, str(e)


def masraf_ekle(tutar: float, aciklama: str) -> tuple[bool, str]:
    try:
        tutar = float(tutar)
        if tutar <= 0:
            return False, "Tutar 0'dan buyuk olmali"
        aciklama = (aciklama or "").strip() or "Masraf"
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO masraflar (tutar, aciklama) VALUES (?, ?)",
            (tutar, aciklama)
        )
        conn.commit()
        conn.close()
        log_info(f"Masraf: {tutar} TL - {aciklama}")
        return True, "Masraf kaydedildi"
    except Exception as e:
        log_error("Masraf ekleme hatasi", e, __file__, "masraf_ekle")
        return False, str(e)


def gunluk_ozet(gun: str | None = None) -> dict:
    """
    Gunluk ciro, nakit, kart, masraf, net.
    gun: YYYY-MM-DD veya None = bugun
    """
    if not gun:
        gun = date.today().isoformat()
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                COALESCE(SUM(toplam), 0) AS ciro,
                COALESCE(SUM(CASE WHEN odeme_tipi = 'nakit' THEN toplam ELSE 0 END), 0) AS nakit,
                COALESCE(SUM(CASE WHEN odeme_tipi = 'kart' THEN toplam ELSE 0 END), 0) AS kart,
                COUNT(*) AS adet_satis
            FROM satislar
            WHERE satis_tarihi = ?
        """, (gun,))
        s = dict(cur.fetchone())

        cur.execute("""
            SELECT COALESCE(SUM(tutar), 0) AS masraf, COUNT(*) AS adet_masraf
            FROM masraflar
            WHERE masraf_tarihi = ?
        """, (gun,))
        m = dict(cur.fetchone())

        conn.close()
        ciro = float(s["ciro"] or 0)
        masraf = float(m["masraf"] or 0)
        return {
            "tarih": gun,
            "ciro": ciro,
            "nakit": float(s["nakit"] or 0),
            "kart": float(s["kart"] or 0),
            "masraf": masraf,
            "net": ciro - masraf,
            "adet_satis": int(s["adet_satis"] or 0),
            "adet_masraf": int(m["adet_masraf"] or 0),
        }
    except Exception as e:
        log_error("Gunluk ozet hatasi", e, __file__, "gunluk_ozet")
        return {
            "tarih": gun, "ciro": 0, "nakit": 0, "kart": 0,
            "masraf": 0, "net": 0, "adet_satis": 0, "adet_masraf": 0,
        }


def bugunku_satislar(limit: int = 30) -> list:
    """
    Bugunku satislari fis bazinda gruplar.
    """
    try:
        gun = date.today().isoformat()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT s.id, s.fis_no, s.adet, s.birim_fiyat, s.indirim, s.odeme_tipi, s.toplam,
                   s.satis_saati, s.banka, u.ad AS urun_adi, u.stok_kodu
            FROM satislar s
            JOIN urunler u ON u.id = s.urun_id
            WHERE s.satis_tarihi = ?
            ORDER BY s.id DESC
        """, (gun,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()

        gruplar = {}
        sira = []
        for r in rows:
            fis = r.get("fis_no") or f"TEK-{r['id']}"
            if fis not in gruplar:
                gruplar[fis] = {
                    "fis_no": fis,
                    "odeme_tipi": r.get("odeme_tipi") or "",
                    "banka": r.get("banka") or "",
                    "saat": r.get("satis_saati") or "",
                    "toplam": 0.0,
                    "indirim": 0.0,
                    "kalemler": [],
                }
                sira.append(fis)
            g = gruplar[fis]
            g["toplam"] += float(r.get("toplam") or 0)
            g["indirim"] += float(r.get("indirim") or 0)
            g["kalemler"].append({
                "urun_adi": r.get("urun_adi") or "",
                "adet": r.get("adet") or 0,
                "toplam": float(r.get("toplam") or 0),
                "indirim": float(r.get("indirim") or 0),
                "stok_kodu": r.get("stok_kodu") or "",
            })
        return [gruplar[f] for f in sira[:limit]]
    except Exception as e:
        log_error("Bugunku satislar listelenemedi", e, __file__, "bugunku_satislar")
        return []


def bugunku_satislari_temizle() -> tuple[bool, str]:
    """Sadece bugunun satis kayitlarini siler (stok geri eklenmez - kasa listesi temizligi)."""
    try:
        gun = date.today().isoformat()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM satislar WHERE satis_tarihi = ?", (gun,))
        n = cur.fetchone()["n"]
        cur.execute("DELETE FROM satislar WHERE satis_tarihi = ?", (gun,))
        conn.commit()
        conn.close()
        log_info(f"Bugunku satis listesi temizlendi: {n} kayit")
        return True, f"{n} satis kaydi listeden silindi"
    except Exception as e:
        log_error("Satis temizleme hatasi", e, __file__, "bugunku_satislari_temizle")
        return False, str(e)


def bugunku_masraflar(limit: int = 40) -> list:
    try:
        gun = date.today().isoformat()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, tutar, aciklama, olusturma, masraf_tarihi
            FROM masraflar
            WHERE masraf_tarihi = ?
            ORDER BY id DESC
            LIMIT ?
        """, (gun, limit))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error("Bugunku masraflar listelenemedi", e, __file__, "bugunku_masraflar")
        return []


def masraf_sil(masraf_id: int) -> tuple[bool, str]:
    """Masraf kaydini siler (sifre gerekmez)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, tutar, aciklama FROM masraflar WHERE id = ?", (masraf_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return False, "Masraf bulunamadi"
        cur.execute("DELETE FROM masraflar WHERE id = ?", (masraf_id,))
        conn.commit()
        conn.close()
        log_info(f"Masraf silindi: id={masraf_id} {row['tutar']} TL")
        return True, "Masraf silindi"
    except Exception as e:
        log_error("Masraf silme hatasi", e, __file__, "masraf_sil")
        return False, str(e)


def fis_sil(fis_no: str) -> tuple[bool, str]:
    """
    Bir fisin tum kalemlerini satislardan siler.
    Stok geri eklenmez (kasa listesi duzeltmesi).
    """
    try:
        fis_no = (fis_no or "").strip()
        if not fis_no:
            return False, "Fis no yok"
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM satislar WHERE fis_no = ?", (fis_no,))
        n = cur.fetchone()["n"]
        if n == 0:
            # TEK-id formati
            if fis_no.startswith("TEK-"):
                try:
                    sid = int(fis_no.replace("TEK-", ""))
                    cur.execute("DELETE FROM satislar WHERE id = ?", (sid,))
                    conn.commit()
                    conn.close()
                    return True, "Satis silindi"
                except ValueError:
                    pass
            conn.close()
            return False, "Fis bulunamadi"
        cur.execute("DELETE FROM satislar WHERE fis_no = ?", (fis_no,))
        conn.commit()
        conn.close()
        log_info(f"Fis silindi: {fis_no} ({n} kalem)")
        return True, f"Fis silindi ({n} kalem)"
    except Exception as e:
        log_error("Fis silme hatasi", e, __file__, "fis_sil")
        return False, str(e)


def fis_iade(fis_no: str) -> tuple[bool, str]:
    """
    Fisi iptal/iade eder: stoklari geri ekler, satis kayitlarini siler.
    """
    try:
        fis_no = (fis_no or "").strip()
        if not fis_no:
            return False, "Fis no yok"
        conn = get_connection()
        cur = conn.cursor()

        if fis_no.startswith("TEK-"):
            try:
                sid = int(fis_no.replace("TEK-", ""))
                cur.execute(
                    "SELECT id, urun_id, adet FROM satislar WHERE id = ?", (sid,)
                )
            except ValueError:
                conn.close()
                return False, "Gecersiz fis"
        else:
            cur.execute(
                "SELECT id, urun_id, adet FROM satislar WHERE fis_no = ?", (fis_no,)
            )
        kalemler = cur.fetchall()
        if not kalemler:
            conn.close()
            return False, "Fis bulunamadi"

        for k in kalemler:
            cur.execute(
                "UPDATE urunler SET stok_adedi = stok_adedi + ?, guncelleme = datetime('now','localtime') WHERE id = ?",
                (int(k["adet"]), k["urun_id"]),
            )
            cur.execute(
                "SELECT COALESCE(parent_id, 0) AS parent_id FROM urunler WHERE id = ?",
                (k["urun_id"],),
            )
            bag = cur.fetchone()
            pid = int(bag["parent_id"] or 0) if bag else 0
            if pid and pid != int(k["urun_id"]):
                cur.execute(
                    """
                    UPDATE urunler
                    SET stok_adedi = COALESCE(stok_adedi, 0) + ?,
                        guncelleme = datetime('now','localtime')
                    WHERE id = ?
                    """,
                    (int(k["adet"]), pid),
                )
            cur.execute("""
                INSERT INTO stok_hareketleri (urun_id, hareket_tipi, adet, aciklama)
                VALUES (?, 'iade', ?, ?)
            """, (k["urun_id"], int(k["adet"]), f"Iade fis {fis_no}"))

        ids = [k["id"] for k in kalemler]
        cur.execute(
            f"DELETE FROM satislar WHERE id IN ({','.join('?'*len(ids))})",
            ids,
        )
        conn.commit()
        conn.close()
        log_info(f"Fis iade: {fis_no} ({len(kalemler)} kalem, stok geri)")
        return True, f"Iade tamam ({len(kalemler)} kalem, stok geri eklendi)"
    except Exception as e:
        log_error("Fis iade hatasi", e, __file__, "fis_iade")
        return False, str(e)
