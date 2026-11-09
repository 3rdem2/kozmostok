# -*- coding: utf-8 -*-
"""
Kanal stoklari, transfer, dogrulama, hareket gecmisi, API ayarlari.
"""

from __future__ import annotations

from core.database import get_connection, get_ayar, set_ayar, PG_MOD
from core.logger import log_error, log_info
from datetime import datetime

API_KEYS = {
    "wix": ["wix_api_key", "wix_site_id", "wix_account_id"],
    "etsy": ["etsy_api_key", "etsy_shared_secret", "etsy_shop_id", "etsy_access_token"],
    "trendyol": ["trendyol_supplier_id", "trendyol_api_key", "trendyol_api_secret"],
}

KANAL_KOLON = {
    "magaza": "stok_adedi",
    "wix": "wix_stok",
    "etsy": "etsy_stok",
    "trendyol": "trendyol_stok",
}

# Kanal listesinde kalma bayragi (adet 0 olsa bile)
KANAL_YAYIN = {
    "wix": "wix_yayin",
    "etsy": "etsy_yayin",
    "trendyol": "trendyol_yayin",
}

# Tek seferde bu kadar ve uzeri artista uyari
FAZLA_GIRIS_ESIK = 20


def api_ayarlari_oku(kanal: str) -> dict:
    return {k: get_ayar(k, "") for k in API_KEYS.get(kanal, [])}


def api_ayarlari_kaydet(kanal: str, degerler: dict) -> bool:
    try:
        for k, v in degerler.items():
            if k in API_KEYS.get(kanal, []):
                set_ayar(k, str(v or ""))
        log_info(f"API ayarlari kaydedildi: {kanal}")
        return True
    except Exception as e:
        log_error(f"API ayar kayit: {kanal}", e, __file__, "api_ayarlari_kaydet")
        return False


def api_hazir_mi(kanal: str) -> bool:
    ay = api_ayarlari_oku(kanal)
    if kanal == "wix":
        return bool(ay.get("wix_api_key"))
    if kanal == "etsy":
        return bool(ay.get("etsy_api_key") and ay.get("etsy_shop_id"))
    if kanal == "trendyol":
        return bool(ay.get("trendyol_supplier_id") and ay.get("trendyol_api_key") and ay.get("trendyol_api_secret"))
    return False


def kanal_urunleri(kanal: str = "ana", arama: str = "", stok_filtre: str = "hepsi") -> list:
    """
    ana/magaza: fiziksel (ana) stok listesi.
    wix/etsy/trendyol: o kanalda SATILAN urunler (kanal adedi > 0 = vitrinde).
    Kanal adedi ayri depo degil; sitede gorunen adet (genelde 1). Satis olunca 0 olur.

    stok_filtre: hepsi | stokta | tukenen | kritik | kanal_kritik
      kanal_kritik = ana stok kritik AND bu kanalda satiliyor
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        sql = """
            SELECT u.id, u.stok_kodu, u.barkod, u.ad,
                   COALESCE(u.stok_adedi, 0) AS magaza_stok,
                   COALESCE(u.wix_stok, 0) AS wix_stok,
                   COALESCE(u.etsy_stok, 0) AS etsy_stok,
                   COALESCE(u.trendyol_stok, 0) AS trendyol_stok,
                   COALESCE(u.stok_adedi, 0) AS ana_stok,
                   u.satis_fiyati, u.kritik_stok, u.beden, u.renk,
                   k.ad AS kategori_adi,
                   COALESCE(u.wix_yayin, 0) AS wix_yayinda,
                   COALESCE(u.etsy_yayin, 0) AS etsy_yayinda,
                   COALESCE(u.trendyol_yayin, 0) AS trendyol_yayinda
            FROM urunler u
            LEFT JOIN kategoriler k ON k.id = u.kategori_id
            WHERE u.aktif = 1
        """
        params = []
        if kanal in ("ana", "magaza"):
            sql += " AND NOT EXISTS (SELECT 1 FROM urunler c WHERE c.parent_id = u.id AND c.aktif = 1)"
        if arama:
            sql += " AND (u.ad LIKE ? OR u.stok_kodu LIKE ? OR u.barkod LIKE ?)"
            q = f"%{arama}%"
            params.extend([q, q, q])

        # Kanal sayfalari: sadece o kanalda listelenenler (adet > 0)
        kanal_kol = {
            "wix": "COALESCE(u.wix_stok,0)",
            "etsy": "COALESCE(u.etsy_stok,0)",
            "trendyol": "COALESCE(u.trendyol_stok,0)",
        }
        if kanal in kanal_kol:
            yay = {"wix": "COALESCE(u.wix_yayin,0)", "etsy": "COALESCE(u.etsy_yayin,0)",
                   "trendyol": "COALESCE(u.trendyol_yayin,0)"}[kanal]
            # Kanalda listelenenler (yayin=1). Adet 0 olsa da listede kalir.
            sql += f" AND {yay} = 1"
            if stok_filtre == "tukenen":
                sql += f" AND {kanal_kol[kanal]} <= 0"
            elif stok_filtre == "stokta":
                sql += f" AND {kanal_kol[kanal]} > 0"

        # Ana stok filtresi
        ana = "COALESCE(u.stok_adedi,0)"
        if stok_filtre == "stokta":
            sql += f" AND {ana} > 0"
        elif stok_filtre == "tukenen" and kanal in ("ana", "magaza"):
            sql += f" AND {ana} <= 0"
        elif stok_filtre == "kritik":
            sql += f" AND {ana} > 0 AND {ana} <= COALESCE(u.kritik_stok, 3)"
        elif stok_filtre == "kanal_kritik":
            sql += f" AND {ana} <= COALESCE(u.kritik_stok, 3)"
            sql += (
                " AND (COALESCE(u.wix_yayin,0)>0 OR COALESCE(u.etsy_yayin,0)>0 "
                "OR COALESCE(u.trendyol_yayin,0)>0)"
            )

        sql += " ORDER BY u.ad"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        # Uyari bayragi
        for r in rows:
            ana_s = int(r.get("magaza_stok") or 0)
            krit = int(r.get("kritik_stok") or 3)
            kanallarda = (
                int(r.get("wix_yayinda") or 0) > 0
                or int(r.get("etsy_yayinda") or 0) > 0
                or int(r.get("trendyol_yayinda") or 0) > 0
            )
            r["uyari_kritik_kanal"] = ana_s <= krit and kanallarda
            r["toplam_stok"] = ana_s  # tek gercek stok = ana/magaza
        conn.close()
        return rows
    except Exception as e:
        log_error(f"Kanal urun: {kanal}", e, __file__, "kanal_urunleri")
        return []


def kanal_ozet() -> dict:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) AS urun_sayisi,
              COALESCE(SUM(stok_adedi), 0) AS magaza,
              COALESCE(SUM(CASE WHEN COALESCE(wix_yayin,0)>0 THEN 1 ELSE 0 END), 0) AS wix_urun,
              COALESCE(SUM(CASE WHEN COALESCE(etsy_yayin,0)>0 THEN 1 ELSE 0 END), 0) AS etsy_urun,
              COALESCE(SUM(CASE WHEN COALESCE(trendyol_yayin,0)>0 THEN 1 ELSE 0 END), 0) AS trendyol_urun,
              COALESCE(SUM(wix_stok), 0) AS wix,
              COALESCE(SUM(etsy_stok), 0) AS etsy,
              COALESCE(SUM(trendyol_stok), 0) AS trendyol
            FROM urunler u WHERE u.aktif = 1 AND NOT EXISTS (SELECT 1 FROM urunler c WHERE c.parent_id = u.id AND c.aktif = 1)
        """)
        r = dict(cur.fetchone())
        conn.close()
        r["ana_stok"] = int(r["magaza"])
        r["toplam"] = int(r["magaza"])
        return r
    except Exception as e:
        log_error("Kanal ozet", e, __file__, "kanal_ozet")
        return {
            "urun_sayisi": 0, "magaza": 0, "wix": 0, "etsy": 0, "trendyol": 0,
            "toplam": 0, "ana_stok": 0, "wix_urun": 0, "etsy_urun": 0, "trendyol_urun": 0,
        }



def stok_dogrula() -> dict:
    """
    Ana stok dogrulama: her urunde toplam = magaza+wix+etsy+trendyol (her zaman dogru)
    Burada 'tutarsiz' = negatif stok veya kritik alti ozeti.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, stok_kodu, ad,
                   COALESCE(stok_adedi,0) AS m,
                   COALESCE(wix_stok,0) AS w,
                   COALESCE(etsy_stok,0) AS e,
                   COALESCE(trendyol_stok,0) AS t
            FROM urunler WHERE aktif=1
              AND (COALESCE(stok_adedi,0) < 0 OR COALESCE(wix_stok,0) < 0
                   OR COALESCE(etsy_stok,0) < 0 OR COALESCE(trendyol_stok,0) < 0)
        """)
        negatif = [dict(r) for r in cur.fetchall()]
        cur.execute("""
            SELECT COUNT(*) AS n FROM urunler
            WHERE aktif=1 AND stok_adedi <= COALESCE(kritik_stok, 3)
        """)
        kritik_n = cur.fetchone()["n"]
        conn.close()
        o = kanal_ozet()
        return {
            "ozet": o,
            "negatif": negatif,
            "kritik_adet": kritik_n,
            "uyari": bool(negatif) or kritik_n > 0,
            "mesaj": (
                f"Toplam stok: {o['toplam']} | Magaza:{o['magaza']} Wix:{o['wix']} "
                f"Etsy:{o['etsy']} TY:{o['trendyol']} | "
                f"Negatif: {len(negatif)} | Kritik: {kritik_n}"
            ),
        }
    except Exception as e:
        log_error("Stok dogrula", e, __file__, "stok_dogrula")
        return {"ozet": {}, "negatif": [], "kritik_adet": 0, "uyari": False, "mesaj": str(e)}


def kanal_stok_oku(urun_id: int, kanal: str) -> int:
    kolon = KANAL_KOLON.get(kanal)
    if not kolon:
        return 0
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT COALESCE({kolon},0) AS s FROM urunler WHERE id=?", (urun_id,))
    r = cur.fetchone()
    conn.close()
    return int(r["s"]) if r else 0


def kanal_stok_yaz(
    urun_id: int,
    kanal: str,
    yeni_stok: int,
    aciklama: str = "",
    fazla_onay: bool = False,
) -> tuple[bool, str, bool]:
    """
    Tek kanal stok gunceller.
    Donus: (basarili, mesaj, fazla_uyari_gerekli)
    fazla_uyari_gerekli=True ise kullaniciya sorulmali; fazla_onay=True ile tekrar cagirin.
    """
    try:
        kolon = KANAL_KOLON.get(kanal)
        if not kolon:
            return False, "Gecersiz kanal", False
        yeni_stok = int(yeni_stok)
        if yeni_stok < 0:
            return False, "Stok negatif olamaz", False

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            f"SELECT ad, COALESCE({kolon},0) AS eski FROM urunler WHERE id=? AND aktif=1",
            (urun_id,),
        )
        u = cur.fetchone()
        if not u:
            conn.close()
            return False, "Urun yok", False
        if kolon == "stok_adedi":
            cur.execute(
                "SELECT COUNT(*) AS n FROM urunler WHERE parent_id = ? AND aktif = 1",
                (urun_id,),
            )
            if int(cur.fetchone()["n"] or 0) > 0:
                conn.close()
                return False, (
                    "Bu urunun varyantlari var: magaza adedi varyant satirlarindan girilir "
                    "(ana adet otomatik hesaplanir)."
                ), False
        eski = int(u["eski"])
        delta = yeni_stok - eski

        if delta >= FAZLA_GIRIS_ESIK and not fazla_onay:
            conn.close()
            return False, (
                f"Fazla giris uyarisi: {u['ad']}\n"
                f"{kanal}: {eski} → {yeni_stok} (+{delta})\n"
                f"Esik: +{FAZLA_GIRIS_ESIK}. Onayliyor musunuz?"
            ), True

        # Adet>0: kanala ekle (yayin=1). Adet=0: sadece sifirla, yayin AYNI kalir (listeden dusmez).
        yayin_kol = KANAL_YAYIN.get(kanal)
        if yayin_kol and yeni_stok > 0:
            cur.execute(
                f"UPDATE urunler SET {kolon}=?, {yayin_kol}=1, guncelleme=datetime('now','localtime') WHERE id=?",
                (yeni_stok, urun_id),
            )
        else:
            cur.execute(
                f"UPDATE urunler SET {kolon}=?, guncelleme=datetime('now','localtime') WHERE id=?",
                (yeni_stok, urun_id),
            )
        cur.execute("""
            INSERT INTO stok_hareketleri (urun_id, hareket_tipi, adet, aciklama)
            VALUES (?, 'duzeltme', ?, ?)
        """, (
            urun_id,
            delta,
            f"[{kanal}] {aciklama or 'Manuel'} ({eski}->{yeni_stok})",
        ))
        conn.commit()
        conn.close()
        log_info(f"Kanal stok [{kanal}] id={urun_id} {eski}->{yeni_stok}")
        if kanal == "magaza":
            from core.urun_servis import _bagli_ana_stogu_tazele
            _bagli_ana_stogu_tazele(urun_id)
        return True, f"{kanal}: {eski} → {yeni_stok}", False
    except Exception as e:
        log_error("kanal_stok_yaz", e, __file__, "kanal_stok_yaz")
        return False, str(e), False


def kanal_transfer(
    urun_id: int,
    kaynak: str,
    hedef: str,
    adet: int,
    aciklama: str = "",
) -> tuple[bool, str]:
    """Bir kanaldan digerine stok tasir (toplam degismez)."""
    try:
        adet = int(adet)
        if adet <= 0:
            return False, "Adet > 0 olmali"
        if kaynak == hedef:
            return False, "Kaynak ve hedef ayni olamaz"
        if kaynak not in KANAL_KOLON or hedef not in KANAL_KOLON:
            return False, "Gecersiz kanal"

        conn = get_connection()
        cur = conn.cursor()
        k_kol = KANAL_KOLON[kaynak]
        h_kol = KANAL_KOLON[hedef]
        cur.execute(
            f"SELECT ad, COALESCE({k_kol},0) AS ks, COALESCE({h_kol},0) AS hs FROM urunler WHERE id=? AND aktif=1",
            (urun_id,),
        )
        u = cur.fetchone()
        if not u:
            conn.close()
            return False, "Urun yok"
        if int(u["ks"]) < adet:
            conn.close()
            return False, f"Yetersiz {kaynak} stok (mevcut {u['ks']})"

        cur.execute(
            f"UPDATE urunler SET {k_kol}={k_kol}-?, {h_kol}={h_kol}+?, guncelleme=datetime('now','localtime') WHERE id=?",
            (adet, adet, urun_id),
        )
        cur.execute("""
            INSERT INTO stok_hareketleri (urun_id, hareket_tipi, adet, aciklama)
            VALUES (?, 'transfer', ?, ?)
        """, (
            urun_id,
            adet,
            f"[{kaynak}→{hedef}] {aciklama or 'Transfer'} x{adet}",
        ))
        conn.commit()
        conn.close()
        log_info(f"Transfer {kaynak}->{hedef} id={urun_id} x{adet}")
        return True, f"{adet} adet {kaynak} → {hedef}"
    except Exception as e:
        log_error("kanal_transfer", e, __file__, "kanal_transfer")
        return False, str(e)


def stok_hareketleri(limit: int = 100, urun_id: int | None = None) -> list:
    try:
        conn = get_connection()
        cur = conn.cursor()
        sql = """
            SELECT h.id, h.urun_id, h.hareket_tipi, h.adet, h.aciklama, h.tarih,
                   u.ad AS urun_adi, u.stok_kodu
            FROM stok_hareketleri h
            JOIN urunler u ON u.id = h.urun_id
        """
        params = []
        if urun_id:
            sql += " WHERE h.urun_id = ?"
            params.append(urun_id)
        sql += " ORDER BY h.id DESC LIMIT ?"
        params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error("stok_hareketleri", e, __file__, "stok_hareketleri")
        return []


def senkron_wix() -> tuple[bool, str]:
    if not api_hazir_mi("wix"):
        return False, "Wix API anahtari girilmemis. API Ayarlari sekmesine bakin."
    return False, "Wix API kayitli. Canli senkron sonraki adimda acilacak; simdilik manuel/Excel kullanin."


def senkron_etsy() -> tuple[bool, str]:
    if not api_hazir_mi("etsy"):
        return False, "Etsy API bilgileri eksik."
    return False, "Etsy API kayitli. Canli senkron sonraki adimda; simdilik manuel/Excel."


def senkron_trendyol() -> tuple[bool, str]:
    if not api_hazir_mi("trendyol"):
        return False, "Trendyol API bilgileri eksik."
    return False, "Trendyol API kayitli. Canli senkron sonraki adimda; simdilik manuel/Excel."



def urun_birlestir(ana_id: int, diger_idler: list) -> tuple:
    """diger urun stoklarini ana urune toplar; digerlerini pasif eder."""
    try:
        diger_idler = [int(i) for i in diger_idler if int(i) != int(ana_id)]
        if not diger_idler:
            return False, "Birlestirilecek baska urun secilmedi"

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, stok_kodu, barkod, ad,
                      COALESCE(stok_adedi,0) AS m,
                      COALESCE(wix_stok,0) AS w,
                      COALESCE(etsy_stok,0) AS e,
                      COALESCE(trendyol_stok,0) AS t,
                      aciklama
               FROM urunler WHERE id=? AND aktif=1""",
            (ana_id,),
        )
        ana = cur.fetchone()
        if not ana:
            conn.close()
            return False, "Ana urun bulunamadi"

        ek_m = ek_w = ek_e = ek_t = 0
        birlesen_kodlar = []
        for did in diger_idler:
            cur.execute(
                """SELECT id, stok_kodu, barkod, ad,
                          COALESCE(stok_adedi,0) AS m,
                          COALESCE(wix_stok,0) AS w,
                          COALESCE(etsy_stok,0) AS e,
                          COALESCE(trendyol_stok,0) AS t,
                          aciklama
                   FROM urunler WHERE id=?""",
                (did,),
            )
            d = cur.fetchone()
            if not d:
                continue
            ek_m += int(d["m"])
            ek_w += int(d["w"])
            ek_e += int(d["e"])
            ek_t += int(d["t"])
            kod = d["stok_kodu"] or ""
            bar = d["barkod"] or ""
            birlesen_kodlar.append(kod + (("/" + bar) if bar else ""))

            not_diger = (
                "[BIRLESTIRILDI] Bu urun "
                + str(ana["stok_kodu"])
                + " ("
                + str(ana["barkod"] or "-")
                + ") ile birlestirilmistir. Ana urun: "
                + str(ana["ad"] or "")[:80]
            )
            eski_ack = (d["aciklama"] or "").strip()
            if eski_ack:
                not_diger = eski_ack[:300] + " | " + not_diger
            cur.execute(
                """UPDATE urunler SET
                    aktif=0,
                    stok_adedi=0, wix_stok=0, etsy_stok=0, trendyol_stok=0,
                    aciklama=?,
                    guncelleme=datetime('now','localtime')
                   WHERE id=?""",
                (not_diger[:900], did),
            )
            cur.execute(
                """INSERT INTO stok_hareketleri (urun_id, hareket_tipi, adet, aciklama)
                   VALUES (?, 'birlestirme', ?, ?)""",
                (
                    did,
                    int(d["m"]) + int(d["w"]) + int(d["e"]) + int(d["t"]),
                    "Pasife alindi -> ana:" + str(ana["stok_kodu"]),
                ),
            )

        if not birlesen_kodlar:
            conn.close()
            return False, "Gecerli urun bulunamadi"

        yeni_m = int(ana["m"]) + ek_m
        yeni_w = int(ana["w"]) + ek_w
        yeni_e = int(ana["e"]) + ek_e
        yeni_t = int(ana["t"]) + ek_t
        not_ana = (
            "[BIRLESTIRME] Su stok numaralari ile birlestirilmistir: "
            + ", ".join(birlesen_kodlar)
        )
        eski_ana = (ana["aciklama"] or "").strip()
        if eski_ana:
            not_ana = eski_ana[:400] + " | " + not_ana

        cur.execute(
            """UPDATE urunler SET
                stok_adedi=?, wix_stok=?, etsy_stok=?, trendyol_stok=?,
                aciklama=?,
                guncelleme=datetime('now','localtime')
               WHERE id=?""",
            (yeni_m, yeni_w, yeni_e, yeni_t, not_ana[:900], ana_id),
        )
        cur.execute(
            """INSERT INTO stok_hareketleri (urun_id, hareket_tipi, adet, aciklama)
               VALUES (?, 'birlestirme', ?, ?)""",
            (
                ana_id,
                ek_m + ek_w + ek_e + ek_t,
                "Birlestirilen: " + ", ".join(birlesen_kodlar),
            ),
        )
        conn.commit()
        conn.close()
        log_info(
            "Urun birlestirme ana=%s + %s" % (ana["stok_kodu"], birlesen_kodlar)
        )
        msg = (
            "Birlestirme tamam. Ana: "
            + str(ana["stok_kodu"])
            + " | Birlesen: "
            + ", ".join(birlesen_kodlar)
            + " | Stok M:%s W:%s E:%s T:%s" % (yeni_m, yeni_w, yeni_e, yeni_t)
        )
        return True, msg
    except Exception as e:
        log_error("Urun birlestir", e, __file__, "urun_birlestir")
        return False, str(e)


# ---------------------------------------------------------------------------
# Uyari + kanal satisi (API altyapisi — su an manuel / hazir kanca)
# ---------------------------------------------------------------------------

def kritik_kanal_uyarilari(limit: int = 200) -> list:
    """
    Ana stok kritik alti VE en az bir kanalda satilan urunler.
    Magaza + kanal sayfalarinda uyari listesi icin.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.stok_kodu, u.ad, u.beden, u.renk,
                   COALESCE(u.stok_adedi, 0) AS ana_stok,
                   COALESCE(u.kritik_stok, 3) AS kritik_stok,
                   COALESCE(u.wix_stok, 0) AS wix_stok,
                   COALESCE(u.etsy_stok, 0) AS etsy_stok,
                   COALESCE(u.trendyol_stok, 0) AS trendyol_stok,
                   COALESCE(u.wix_yayin, 0) AS wix_yayin,
                   COALESCE(u.etsy_yayin, 0) AS etsy_yayin,
                   COALESCE(u.trendyol_yayin, 0) AS trendyol_yayin
            FROM urunler u
            WHERE u.aktif = 1
              AND COALESCE(u.stok_adedi, 0) <= COALESCE(u.kritik_stok, 3)
              AND (
                    COALESCE(u.wix_yayin, 0) > 0
                 OR COALESCE(u.etsy_yayin, 0) > 0
                 OR COALESCE(u.trendyol_yayin, 0) > 0
              )
            ORDER BY u.stok_adedi ASC, u.ad
            LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        for r in rows:
            kanallar = []
            if int(r.get("wix_yayin") or 0) > 0:
                kanallar.append("wix")
            if int(r.get("etsy_yayin") or 0) > 0:
                kanallar.append("etsy")
            if int(r.get("trendyol_yayin") or 0) > 0:
                kanallar.append("trendyol")
            r["kanallar"] = kanallar
        return rows
    except Exception as e:
        log_error("Kritik kanal uyari", e, __file__, "kritik_kanal_uyarilari")
        return []


def kanal_yayindan_kaldir(urun_id: int, kanal: str, aciklama: str = "") -> tuple[bool, str]:
    """
    Kanaldan tamamen cikar: adet=0 ve yayin=0 (listeden kalkar).
    Sadece adedi sifirlamak icin kanal_stok_yaz(..., 0) kullanin — listede kalir.
    """
    if kanal not in ("wix", "etsy", "trendyol"):
        return False, "Gecersiz kanal"
    try:
        ok, msg, _ = kanal_stok_yaz(
            urun_id, kanal, 0,
            aciklama=aciklama or "Yayindan kaldirildi",
            fazla_onay=True,
        )
        if not ok:
            return False, msg
        yayin_kol = KANAL_YAYIN.get(kanal)
        if yayin_kol:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                f"UPDATE urunler SET {yayin_kol}=0, guncelleme=datetime('now','localtime') WHERE id=?",
                (urun_id,),
            )
            conn.commit()
            conn.close()
        api_sonuc = kanal_api_stok_guncelle(kanal, urun_id, 0)
        extra = ""
        if api_sonuc.get("denendi") and not api_sonuc.get("ok"):
            extra = f" | API: {api_sonuc.get('mesaj', 'bekliyor')}"
        return True, f"{msg} | Kanaldan cikarildi (listeden kaldirildi){extra}"
    except Exception as e:
        log_error("Yayindan kaldir", e, __file__, "kanal_yayindan_kaldir")
        return False, str(e)


def kanal_satis_bildir(
    kanal: str,
    stok_kodu: str = "",
    barkod: str = "",
    adet: int = 1,
    harici_siparis_no: str = "",
    fiyat: float = 0.0,
) -> tuple[bool, str, dict | None]:
    """
    Kanal satisi bildirimi (API veya manuel).
    - Kanal vitrin adedini dusurur (genelde 1 -> 0)
    - Ana stoktan dusmez; kullanici ayirir / onaylar
    - Donen dict: uyari bilgisi (kanal satisi uyarisi)

    API altyapisi: senkron_* fonksiyonlari bunu cagiracak.
    """
    try:
        if kanal not in ("wix", "etsy", "trendyol"):
            return False, "Gecersiz kanal", None
        conn = get_connection()
        cur = conn.cursor()
        if stok_kodu:
            cur.execute(
                "SELECT id, ad, stok_adedi, wix_stok, etsy_stok, trendyol_stok, kritik_stok "
                "FROM urunler WHERE aktif=1 AND stok_kodu = ? LIMIT 1",
                (stok_kodu,),
            )
        elif barkod:
            cur.execute(
                "SELECT id, ad, stok_adedi, wix_stok, etsy_stok, trendyol_stok, kritik_stok "
                "FROM urunler WHERE aktif=1 AND barkod = ? LIMIT 1",
                (barkod,),
            )
        else:
            conn.close()
            return False, "stok_kodu veya barkod gerekli", None
        row = cur.fetchone()
        if not row:
            from core.urun_servis import eski_kodla_bul
            eid = eski_kodla_bul(cur, stok_kodu or barkod)
            if eid:
                cur.execute(
                    "SELECT id, ad, stok_adedi, wix_stok, etsy_stok, trendyol_stok, kritik_stok "
                    "FROM urunler WHERE id = ?",
                    (eid,),
                )
                row = cur.fetchone()
        if row and int(dict(row).get("stok_adedi") or 0) > 0:
            # Magazada gorunuyor: kapatilamaz ayirma uyarisi olustur
            try:
                _bekleyen_ekle(cur, int(row["id"]), kanal, max(1, int(adet or 1)), harici_siparis_no, fiyat)
                conn.commit()
            except Exception as e:
                log_error("Bekleyen ayirma eklenemedi", e, __file__, "kanal_satis_bildir")
        conn.close()
        if not row:
            return False, "Urun bulunamadi", None
        u = dict(row)
        mevcut_k = int(u.get({"wix": "wix_stok", "etsy": "etsy_stok", "trendyol": "trendyol_stok"}[kanal]) or 0)
        yeni_k = max(0, mevcut_k - max(1, int(adet)))
        ok, msg, _ = kanal_stok_yaz(
            u["id"], kanal, yeni_k,
            aciklama=f"Kanal satisi {kanal} siparis={harici_siparis_no}",
            fazla_onay=True,
        )
        uyari = {
            "tip": "kanal_satisi",
            "kanal": kanal,
            "urun_id": u["id"],
            "stok_kodu": stok_kodu or "",
            "ad": u.get("ad"),
            "kanal_adet_yeni": yeni_k,
            "ana_stok": int(u.get("stok_adedi") or 0),
            "mesaj": (
                f"Kanal satisi: {u.get('ad')} ({kanal}). "
                f"Vitrin adedi {mevcut_k} -> {yeni_k}. "
                f"Ana stoktan ayirmayi unutmayin (su an {int(u.get('stok_adedi') or 0)})."
            ),
            "siparis_no": harici_siparis_no,
        }
        # Kalici uyari kaydi (ayarlar / basit log)
        try:
            set_ayar(
                f"son_kanal_satisi_{kanal}",
                f"{u.get('ad')}|{yeni_k}|{harici_siparis_no}",
            )
        except Exception:
            pass
        log_info(uyari["mesaj"])
        return ok, uyari["mesaj"], uyari
    except Exception as e:
        log_error("Kanal satis bildir", e, __file__, "kanal_satis_bildir")
        return False, str(e), None


def bekleyen_onayla(bek_id: int, onaylayan: str = "") -> tuple[bool, str]:
    """
    2. asama: yonetici kanal sayfasindaki OK ile ayirmayi onaylar;
    kayit 'ayrildi' olur ve Satilanlar sekmesine/rapora dusar.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bekleyen_ayirma WHERE id=? AND durum='ayrildi_bekliyor'", (int(bek_id),))
        k = cur.fetchone()
        if not k:
            conn.close()
            return False, "Onaylanmayacak kayit (ayrilma beklemiyor)"
        cur.execute(
            "UPDATE bekleyen_ayirma SET durum='ayrildi', onaylayan=?, onay_zamani=datetime('now','localtime') WHERE id=?",
            (onaylayan or "-", int(bek_id)),
        )
        conn.commit()
        conn.close()
        log_info(f"Kanal satisi onaylandi: id={bek_id} onaylayan={onaylayan}")
        return True, "Satis onaylandi; Satilanlar bolumune eklendi (kargo bekliyor)"
    except Exception as e:
        log_error("Bekleyen onay", e, __file__, "bekleyen_onayla")
        return False, str(e)


def kargo_no_yaz(satis_id: int, kargo_no: str, yazan: str = "") -> tuple[bool, str]:
    """Satilanlar satirina kargo takip numarasi yazar; durum 'kargoda' olur."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT durum FROM bekleyen_ayirma WHERE id=?", (int(satis_id),))
        k = cur.fetchone()
        if not k:
            conn.close()
            return False, "Kayit bulunamadi"
        if k["durum"] != "ayrildi":
            conn.close()
            return False, "Kargo numarasi sadece onaylanmis satisa eklenebilir"
        cur.execute(
            "UPDATE bekleyen_ayirma SET kargo_no=?, kargo_zamani=datetime('now','localtime') WHERE id=?",
            ((kargo_no or "").strip(), int(satis_id)),
        )
        conn.commit()
        conn.close()
        return True, "Kargo numarasi kaydedildi; durum: kargoda"
    except Exception as e:
        log_error("Kargo no", e, __file__, "kargo_no_yaz")
        return False, str(e)


def kargo_teslim_onayla(satis_id: int, onaylayan: str = "") -> tuple[bool, str]:
    """Kargo varisini onaylar (Wix/Etsy/Trendyol takibinden); durum 'teslim edildi' olur."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT durum, kargo_no FROM bekleyen_ayirma WHERE id=?", (int(satis_id),))
        k = cur.fetchone()
        if not k:
            conn.close()
            return False, "Kayit bulunamadi"
        if k["durum"] not in ("ayrildi", "kargoda"):
            conn.close()
            return False, "Teslim onayi sadece kargodaki/kargo bekleyen satisa verilebilir"
        cur.execute(
            "UPDATE bekleyen_ayirma SET durum='teslim', teslim_zamani=datetime('now','localtime') WHERE id=?",
            (int(satis_id),),
        )
        conn.commit()
        conn.close()
        return True, "Teslim edildi olarak isaretlendi"
    except Exception as e:
        log_error("Kargo teslim", e, __file__, "kargo_teslim_onayla")
        return False, str(e)


def satis_durumu(r: dict) -> str:
    """Satilanlar tablosundaki durum kolonu metni."""
    d = r.get("durum")
    if d == "teslim":
        return "Teslim edildi"
    if d == "kargoda" or (d == "ayrildi" and r.get("kargo_no")):
        return "Kargoda"
    if d == "ayrildi":
        return "Kargo bekliyor"
    if d == "iade_bekliyor":
        return "Iade kargo bekliyor"
    if d == "iade":
        return "IADE EDILDI"
    return d or "-"


def bekleyen_iptal(bek_id: int, iptal_eden: str = "") -> tuple[bool, str]:
    """
    Bekleyen kanal satisini iptal eder: vitrin adedi geri artirilir,
    rapora hic eklenmez, kayit 'iptal' olur.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bekleyen_ayirma WHERE id=?", (int(bek_id),))
        k = cur.fetchone()
        if not k:
            conn.close()
            return False, "Kayit bulunamadi"
        k = dict(k)
        if k["durum"] != "bekliyor":
            conn.close()
            if k["durum"] == "ayrildi":
                return False, "Bu satis zaten ayrildi; iade olarak isaretleyin"
            return False, f"Bu kayit zaten {k['durum']} durumunda"
        adet = max(1, int(k["adet"] or 1))
        kolon = KANAL_KOLON.get(k["kanal"])
        if kolon:
            cur.execute(
                f"UPDATE urunler SET {kolon} = COALESCE({kolon},0) + ? WHERE id=?",
                (adet, int(k["urun_id"])),
            )
            cur.execute(
                "INSERT INTO stok_hareketleri (urun_id, hareket_tipi, adet, aciklama) "
                "VALUES (?, 'kanal_iptal', ?, ?)",
                (int(k["urun_id"]), adet,
                 f"[{k['kanal']}] satis iptal siparis={k['siparis_no'] or '-'} {iptal_eden}".strip()),
            )
        cur.execute(
            "UPDATE bekleyen_ayirma SET durum='iptal', ayiran=? WHERE id=?",
            (iptal_eden or "-", int(bek_id)),
        )
        conn.commit()
        conn.close()
        return True, "Satis iptal edildi; vitrin adedi geri eklendi, rapora eklenmedi"
    except Exception as e:
        log_error("Bekleyen iptal", e, __file__, "bekleyen_iptal")
        return False, str(e)


def bekleyen_ayirma_geri_al(bek_id: int, kim: str = "", tam_iptal: bool = False) -> tuple[bool, str]:
    """
    Ayirildiktan sonraki iptal: stok geri eklenir.
    tam_iptal=True ise vitrin adedi de geri eklenip satis tamamen iptal olur;
    degilse kayit 'bekliyor'a doner (magaza uyarisi yeniden cikar).
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bekleyen_ayirma WHERE id=? AND durum='ayrildi_bekliyor'", (int(bek_id),))
        k = cur.fetchone()
        if not k:
            conn.close()
            return False, "Geri alinacak ayirma bulunamadi"
        k = dict(k)
        adet = max(1, int(k["adet"] or 1))
        cur.execute(
            "UPDATE urunler SET stok_adedi = COALESCE(stok_adedi,0) + ?, "
            "guncelleme=datetime('now','localtime') WHERE id=?",
            (adet, int(k["urun_id"])),
        )
        cur.execute(
            "INSERT INTO stok_hareketleri (urun_id, hareket_tipi, adet, aciklama) "
            "VALUES (?, 'kanal_ayirma_geri', ?, ?)",
            (int(k["urun_id"]), adet,
             f"[{k['kanal']}] ayirma geri alindi siparis={k['siparis_no'] or '-'} {kim}".strip()),
        )
        if tam_iptal:
            kolon = KANAL_KOLON.get(k["kanal"])
            if kolon:
                cur.execute(
                    f"UPDATE urunler SET {kolon} = COALESCE({kolon},0) + ? WHERE id=?",
                    (adet, int(k["urun_id"])),
                )
                cur.execute(
                    "INSERT INTO stok_hareketleri (urun_id, hareket_tipi, adet, aciklama) "
                    "VALUES (?, 'kanal_iptal', ?, ?)",
                    (int(k["urun_id"]), adet,
                     f"[{k['kanal']}] satis iptal siparis={k['siparis_no'] or '-'} {kim}".strip()),
                )
            cur.execute("UPDATE bekleyen_ayirma SET durum='iptal', ayiran=? WHERE id=?",
                        (kim or "-", int(bek_id)))
            mesaj = "Ayirma geri alindi; satis tamamen iptal edildi (rapora eklenmez)"
        else:
            cur.execute(
                "UPDATE bekleyen_ayirma SET durum='bekliyor', ayirilma=NULL, ayiran=NULL WHERE id=?",
                (int(bek_id),),
            )
            mesaj = "Ayirma geri alindi; satis beklemeye dondu (magaza uyarisi yeniden cikar)"
        conn.commit()
        conn.close()
        return True, mesaj
    except Exception as e:
        log_error("Ayirma geri al", e, __file__, "bekleyen_ayirma_geri_al")
        return False, str(e)


def kanal_satis_iade(satis_id: int, iade_eden: str = "") -> tuple[bool, str]:
    """
    Tamamlanmis kanal satisina iade kaydi acar: durum 'iade_bekliyor' olur.
    Stok, iade kargosu magazaya ulasip 'iade_teslim_al' ile teslim alinincaya degismez.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bekleyen_ayirma WHERE id=?", (int(satis_id),))
        k = cur.fetchone()
        if not k:
            conn.close()
            return False, "Kayit bulunamadi"
        k = dict(k)
        if k["durum"] not in ("ayrildi", "kargoda", "teslim"):
            conn.close()
            if k["durum"] == "iade_bekliyor":
                return False, "Bu satis icin iade zaten beklemede"
            return False, "Sadece tamamlanmis satis iade edilebilir"
        adet = max(1, int(k["adet"] or 1))
        cur.execute(
            "UPDATE bekleyen_ayirma SET durum='iade_bekliyor', iade_eden=? WHERE id=?",
            (iade_eden or "-", int(satis_id)),
        )
        conn.commit()
        conn.close()
        return True, (f"Iade kaydi olusturuldu ({adet} adet). Iade kargosu magazaya ulasinca "
                      "'Iade teslim al' ile stoga giris yapin")
    except Exception as e:
        log_error("Kanal satis iade", e, __file__, "kanal_satis_iade")
        return False, str(e)


def iade_teslim_al(satis_id: int, alan: str = "") -> tuple[bool, str]:
    """
    Iade kargosu magazaya ulastiginda: urun magaza stoguna giris yapar,
    durum 'iade' (IADE EDILDI) olur.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bekleyen_ayirma WHERE id=?", (int(satis_id),))
        k = cur.fetchone()
        if not k:
            conn.close()
            return False, "Kayit bulunamadi"
        k = dict(k)
        if k["durum"] != "iade_bekliyor":
            conn.close()
            return False, "Teslim alinacak iade bulunamadi"
        adet = max(1, int(k["adet"] or 1))
        cur.execute(
            "UPDATE urunler SET stok_adedi = COALESCE(stok_adedi,0) + ?, "
            "guncelleme=datetime('now','localtime') WHERE id=?",
            (adet, int(k["urun_id"])),
        )
        cur.execute(
            "INSERT INTO stok_hareketleri (urun_id, hareket_tipi, adet, aciklama) "
            "VALUES (?, 'iade', ?, ?)",
            (int(k["urun_id"]), adet,
             f"[{k['kanal']}] iade stoga giris siparis={k['siparis_no'] or '-'} {alan}".strip()),
        )
        cur.execute(
            "UPDATE bekleyen_ayirma SET durum='iade', iade_edilme=datetime('now','localtime'), iade_eden=? WHERE id=?",
            (alan or k.get("iade_eden") or "-", int(satis_id)),
        )
        conn.commit()
        conn.close()
        return True, f"Iade teslim alindi: magaza stoguna {adet} adet giris yapildi"
    except Exception as e:
        log_error("Iade teslim al", e, __file__, "iade_teslim_al")
        return False, str(e)


def kanal_satislari(kanal: str = "", limit: int = 500) -> list:
    """Satilanlar sekmesi + rapor: tamamlanmis (ayrildi) ve iade edilmis kanal satislari."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        _bekleyen_tablo(cur)
        sql = """
            SELECT b.id, b.urun_id, b.kanal, b.adet, b.siparis_no, b.fiyat, b.durum,
                   b.ayirilma, b.ayiran, b.iade_edilme, b.iade_eden,
                   b.onaylayan, b.onay_zamani, b.kargo_no, b.kargo_zamani, b.teslim_zamani,
                   u.ad, u.stok_kodu, u.barkod, u.beden
            FROM bekleyen_ayirma b
            LEFT JOIN urunler u ON u.id = b.urun_id
            WHERE b.durum IN ('ayrildi', 'iade', 'kargoda', 'teslim', 'iade_bekliyor')
        """
        params: list = []
        if kanal in ("wix", "etsy", "trendyol"):
            sql += " AND b.kanal = ?"
            params.append(kanal)
        sql += " ORDER BY b.id DESC LIMIT ?"
        params.append(int(limit))
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
        conn.close()
        try:
            from core.denetci_servis import beden_cikar
        except Exception:
            beden_cikar = None
        for r in rows:
            b = (r.get("beden") or "").strip()
            if not b and beden_cikar is not None:
                try:
                    b = (beden_cikar({"stok_kodu": r.get("stok_kodu"), "barkod": r.get("barkod")}) or "").strip()
                except Exception:
                    b = ""
            r["beden_goster"] = b or "-"
        return rows
    except Exception as e:
        log_error("Kanal satislari", e, __file__, "kanal_satislari")
        return []


def bekleyen_hatirlatmalar(esik_gun: int = 1) -> list[str]:
    """
    Yonetim paneli acilis uyarisi: yapilmayan/yarida kalan isler.
    - 1 gunden eski bekleyen ayirmalar (magaza henuz ayirmamis)
    - yonetici onayi bekleyen ayirmalar
    - kargo bekleyen / kargoda / teslim edilen satislar
    - iade bekleyen ve iade edilmis satislar
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        _bekleyen_tablo(cur)
        cur.execute("""
            SELECT b.id, b.urun_id, b.kanal, b.adet, b.siparis_no, b.durum, b.olusturma,
                   b.ayirilma, b.ayiran, b.kargo_no, u.ad, u.stok_kodu
            FROM bekleyen_ayirma b
            LEFT JOIN urunler u ON u.id = b.urun_id
            WHERE b.durum IN ('bekliyor', 'ayrildi_bekliyor', 'ayrildi', 'kargoda', 'iade_bekliyor')
            ORDER BY b.id
        """)
        rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
        conn.close()
    except Exception as e:
        log_error("Hatirlatmalar", e, __file__, "bekleyen_hatirlatmalar")
        return []

    from datetime import datetime as _dt
    simdi = _dt.now()
    satirlar: list[str] = []
    for r in rows:
        when = r.get("ayirilma") or r.get("olusturma") or ""
        try:
            yas = (simdi - _dt.strptime(when[:19], "%Y-%m-%d %H:%M:%S")).days
        except Exception:
            yas = 0
        ad = f"{r.get('ad') or '?'} ({r.get('stok_kodu') or '-'})"
        sp = f" — Siparis: {r['siparis_no']}" if r.get("siparis_no") and r["siparis_no"] != "-" else ""
        d = r["durum"]
        if d == "bekliyor" and yas >= max(0, int(esik_gun)):
            satirlar.append(f"[BEKLEYEN] {ad} — {r['kanal']} satisi {r['adet']} adet, "
                            f"{yas} gundur magazada ayrilmadi{sp}")
        elif d == "ayrildi_bekliyor":
            satirlar.append(f"[ONAY BEKLIYOR] {ad} — ayiran: {r.get('ayiran') or '-'}, "
                            f"yonetici OK onayi verilmemis{sp}")
        elif d == "ayrildi" and not r.get("kargo_no"):
            satirlar.append(f"[KARGO BEKLIYOR] {ad} — onaylandi, kargo numarasi girilmedi{sp}")
        elif d == "kargoda":
            satirlar.append(f"[KARGODA] {ad} — kargo no: {r.get('kargo_no') or '-'} — varis onayi bekleniyor{sp}")
        elif d == "iade_bekliyor":
            satirlar.append(f"[IADE BEKLIYOR] {ad} — iade kargosu magazaya ulasinca teslim alinmali{sp}")
        # 'teslim' ve 'iade' isleri tamamlanmistir; hatirlatma cikmaz
    return satirlar


def kanal_satis_rapor_csv(kanal: str = "") -> str:
    """Satilanlari raporlar/ altina CSV olarak yazar, dosya yolunu dondurur."""
    from core.database import BASE_DIR
    from csv import writer
    rows = kanal_satislari(kanal)
    klasor = BASE_DIR / "raporlar"
    klasor.mkdir(parents=True, exist_ok=True)
    ad = f"kanal_satis_raporu_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    yol = klasor / ad
    with open(yol, "w", newline="", encoding="utf-8-sig") as f:
        w = writer(f, delimiter=";")
        w.writerow(["Siparis No", "Urun", "Varyant", "Kanal", "Adet", "Fiyat",
                    "Tutar", "Tarih-Saat", "Ayiran", "Onaylayan", "Kargo No", "Durum"])
        for r in rows:
            try:
                tutar = float(r.get("fiyat") or 0) * int(r.get("adet") or 1)
            except Exception:
                tutar = 0.0
            w.writerow([
                r.get("siparis_no") or "", r.get("ad") or "", r.get("beden_goster") or "-",
                r.get("kanal") or "", r.get("adet") or 0,
                f"{float(r.get('fiyat') or 0):.2f}", f"{tutar:.2f}",
                (r.get("ayirilma") or "")[:16], r.get("ayiran") or "-",
                r.get("onaylayan") or "-", r.get("kargo_no") or "",
                "IADE EDILDI" if r.get("durum") == "iade" else satis_durumu(r),
            ])
    return str(yol)


def _bekleyen_tablo(cur) -> None:
    if PG_MOD:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS bekleyen_ayirma ("
            "id SERIAL PRIMARY KEY, urun_id INTEGER, kanal TEXT, adet INTEGER DEFAULT 1, "
            "siparis_no TEXT, fiyat REAL DEFAULT 0, durum TEXT DEFAULT 'bekliyor', olusturma TEXT, "
            "ayirilma TEXT, ayiran TEXT, iade_edilme TEXT, iade_eden TEXT)"
        )
    else:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS bekleyen_ayirma ("
            "id INTEGER PRIMARY KEY, urun_id INTEGER, kanal TEXT, adet INTEGER DEFAULT 1, "
            "siparis_no TEXT, fiyat REAL DEFAULT 0, durum TEXT DEFAULT 'bekliyor', olusturma TEXT, "
            "ayirilma TEXT, ayiran TEXT, iade_edilme TEXT, iade_eden TEXT)"
        )
    for kol, tip in (("fiyat", "REAL DEFAULT 0"), ("iade_edilme", "TEXT"), ("iade_eden", "TEXT"),
                     ("onaylayan", "TEXT"), ("onay_zamani", "TEXT"),
                     ("kargo_no", "TEXT"), ("kargo_zamani", "TEXT"), ("teslim_zamani", "TEXT")):
        try:
            if PG_MOD:
                cur.execute(f"ALTER TABLE bekleyen_ayirma ADD COLUMN IF NOT EXISTS {kol} {tip}")
            else:
                cur.execute(f"ALTER TABLE bekleyen_ayirma ADD COLUMN {kol} {tip}")
        except Exception:
            pass


def _bekleyen_ekle(cur, urun_id: int, kanal: str, adet: int, siparis_no: str, fiyat: float = 0.0) -> None:
    _bekleyen_tablo(cur)
    cur.execute(
        "SELECT id, adet FROM bekleyen_ayirma WHERE urun_id=? AND kanal=? AND durum='bekliyor' LIMIT 1",
        (urun_id, kanal),
    )
    r = cur.fetchone()
    if r:
        cur.execute(
            "UPDATE bekleyen_ayirma SET adet = COALESCE(adet,0) + ?, "
            "fiyat = CASE WHEN ? > 0 THEN ? ELSE fiyat END WHERE id=?",
            (int(adet), float(fiyat or 0), float(fiyat or 0), int(r["id"])),
        )
    else:
        cur.execute(
            "INSERT INTO bekleyen_ayirma (urun_id, kanal, adet, siparis_no, fiyat, durum, olusturma) "
            "VALUES (?, ?, ?, ?, ?, 'bekliyor', datetime('now','localtime'))",
            (urun_id, kanal, int(adet), siparis_no or "", float(fiyat or 0)),
        )


def bekleyen_ayirmalar() -> list:
    """Magaza ekraninin uyarı bandı için bekleyen kanal ayırmaları."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        _bekleyen_tablo(cur)
        cur.execute("""
            SELECT b.id, b.urun_id, b.kanal, b.adet, b.siparis_no, b.fiyat, b.durum, b.olusturma,
                   u.ad, u.stok_kodu, u.barkod, u.beden,
                   COALESCE(u.stok_adedi,0) AS ana_stok
            FROM bekleyen_ayirma b
            LEFT JOIN urunler u ON u.id = b.urun_id
            WHERE b.durum IN ('bekliyor', 'ayrildi_bekliyor')
            ORDER BY b.id
        """)
        rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
        conn.close()
        try:
            from core.denetci_servis import beden_cikar
        except Exception:
            beden_cikar = None
        for r in rows:
            b = (r.get("beden") or "").strip()
            if not b and beden_cikar is not None:
                try:
                    b = (beden_cikar({"stok_kodu": r.get("stok_kodu"), "barkod": r.get("barkod")}) or "").strip()
                except Exception:
                    b = ""
            r["beden_goster"] = b or "-"
        return rows
    except Exception as e:
        log_error("Bekleyen ayirmalar", e, __file__, "bekleyen_ayirmalar")
        return []


def bekleyen_ayirma_yap(bek_id: int, ayiran: str = "") -> tuple[bool, str]:
    """
    1. asama: magaza urunu fiziksel olarak ayirir (stok duser),
    durum 'ayrildi_bekliyor' olur; yonetici OK onayi beklemede kalir.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bekleyen_ayirma WHERE id=? AND durum='bekliyor'", (int(bek_id),))
        k = cur.fetchone()
        if not k:
            conn.close()
            return False, "Kayit bulunamadi (zaten ayrilmis olabilir)"
        cur.execute("SELECT ad, stok_adedi FROM urunler WHERE id=?", (int(k["urun_id"]),))
        u = cur.fetchone()
        if not u:
            conn.close()
            return False, "Urun bulunamadi"
        eski = int(u["stok_adedi"] or 0)
        adet = max(1, int(k["adet"] or 1))
        yeni = max(0, eski - adet)
        dusen = eski - yeni
        cur.execute(
            "UPDATE urunler SET stok_adedi=?, guncelleme=datetime('now','localtime') WHERE id=?",
            (yeni, int(k["urun_id"])),
        )
        cur.execute(
            "INSERT INTO stok_hareketleri (urun_id, hareket_tipi, adet, aciklama) "
            "VALUES (?, 'kanal_ayirma', ?, ?)",
            (int(k["urun_id"]), -dusen,
             f"[{k['kanal']}] satis ayirma siparis={k['siparis_no'] or '-'} {ayiran}".strip()),
        )
        cur.execute(
            "UPDATE bekleyen_ayirma SET durum='ayrildi_bekliyor', ayirilma=datetime('now','localtime'), ayiran=? WHERE id=?",
            (ayiran or "-", int(bek_id)),
        )
        conn.commit()
        conn.close()
        return True, f"{u['ad']} ayrildi: magaza stoku {eski} -> {yeni}. Yonetici OK onayi bekleniyor"
    except Exception as e:
        log_error("Bekleyen ayirma", e, __file__, "bekleyen_ayirma_yap")
        return False, str(e)


def son_ayirmalar(kanal: str = "", limit: int = 5) -> list:
    """Kanal sayfasi icin son yapilan ayirmalar (kim ayirdi bilgisiyle)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        _bekleyen_tablo(cur)
        sql = """
            SELECT b.urun_id, b.kanal, b.adet, b.ayiran, b.ayirilma,
                   u.ad, u.stok_kodu, u.beden
            FROM bekleyen_ayirma b
            LEFT JOIN urunler u ON u.id = b.urun_id
            WHERE b.durum = 'ayrildi'
        """
        params: list = []
        if kanal in ("wix", "etsy", "trendyol"):
            sql += " AND b.kanal = ?"
            params.append(kanal)
        sql += " ORDER BY b.id DESC LIMIT ?"
        params.append(int(limit))
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
        conn.close()
        return rows
    except Exception as e:
        log_error("Son ayirmalar", e, __file__, "son_ayirmalar")
        return []


def kanal_api_stok_guncelle(kanal: str, urun_id: int, yeni_adet: int) -> dict:
    """
    Dis API stok/yayin guncelleme kancasi.
    API anahtarlari yoksa denendi=False doner; altyapi hazir.
    """
    if not api_hazir_mi(kanal):
        return {
            "ok": False,
            "denendi": False,
            "mesaj": f"{kanal} API anahtari tanimli degil — manuel/beklemede",
        }
    # Gercek HTTP cagrilari API baglaninca buraya eklenecek
    return {
        "ok": False,
        "denendi": True,
        "mesaj": (
            f"{kanal} API bagli gorunuyor ancak senkron henuz uygulanmadi "
            f"(urun_id={urun_id}, adet={yeni_adet}). Altyapi hazir."
        ),
        "urun_id": urun_id,
        "adet": yeni_adet,
        "kanal": kanal,
    }


def magaza_kritik_uyarilari(limit: int = 100) -> list:
    """Sadece ana stok kritik (kanal bagimsiz) — magaza ekrani icin."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, stok_kodu, ad, beden,
                   COALESCE(stok_adedi,0) AS ana_stok,
                   COALESCE(kritik_stok,3) AS kritik_stok
            FROM urunler
            WHERE aktif=1 AND COALESCE(stok_adedi,0) <= COALESCE(kritik_stok,3)
            ORDER BY stok_adedi ASC
            LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error("Magaza kritik", e, __file__, "magaza_kritik_uyarilari")
        return []
