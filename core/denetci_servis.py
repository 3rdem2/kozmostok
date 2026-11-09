# -*- coding: utf-8 -*-
"""
Denetci: ayni urun birlestirme, stok kodu standardi (KZM-0000), bos kod havuzu.
Varyantlar ana urunun stok kodunu paylasir; ayrim barkod sonekidir.
"""

import html
import json
import re
from datetime import datetime
from pathlib import Path

from core.database import (
    get_connection, PG_MOD, get_ayar, set_ayar,
)
from core.logger import log_error, log_info

KOD_RE = re.compile(r"^KZM-(\d{4})$")
_hazir = False


def _ek(beden) -> str:
    return re.sub(r"[^A-Z0-9]", "", (beden or "").upper())


_BEDEN_SON = re.compile(
    r"(?:^|[-_ ]|(?<=\d))(XXXL|XXL|XL|XXS|XS|S/M|M/L|L/XL|L/M|S|M|L|\d{2})$"
)


def beden_cikar(r) -> str:
    """Beden alani bossa stok kodu sonundan (-L, -M, 013S...) cikarir."""
    b = (r.get("beden") or "").strip().upper()
    if b:
        return b
    m = _BEDEN_SON.search((r.get("stok_kodu") or "").strip().upper())
    return m.group(1) if m else ""


def _ad_anahtar(ad) -> str:
    t = html.unescape(ad or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip().casefold()


def sema_hazirla() -> None:
    """kod_havuzu tablosu, eski_* kolonlari; PostgreSQL'de stok_kodu UNIQUE kaldirilir."""
    global _hazir
    if _hazir:
        return
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS kod_havuzu ("
            "stok_kodu TEXT PRIMARY KEY, eklenme TEXT, kaynak TEXT)"
        )
        conn.commit()
    finally:
        conn.close()
    for kol in ("eski_stok_kodu", "eski_barkod"):
        conn = get_connection()
        try:
            cur = conn.cursor()
            if PG_MOD:
                cur.execute(f"ALTER TABLE urunler ADD COLUMN IF NOT EXISTS {kol} TEXT")
            else:
                cur.execute(f"ALTER TABLE urunler ADD COLUMN {kol} TEXT")
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()
    if PG_MOD:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'urunler'::regclass "
                "AND contype = 'u' AND pg_get_constraintdef(oid) = 'UNIQUE (stok_kodu)'"
            )
            for r in cur.fetchall():
                cur.execute(f'ALTER TABLE urunler DROP CONSTRAINT "{r["conname"]}"')
            conn.commit()
        except Exception as e:
            log_error("stok_kodu UNIQUE kaldirilamadi", e, __file__, "sema_hazirla")
        finally:
            conn.close()
    _hazir = True


def kod_paylasilabilir() -> bool:
    """Varyantlar ana stok kodunu paylasabilir mi (sadece PostgreSQL)."""
    if not PG_MOD:
        return False
    sema_hazirla()
    return True


def cocuk_stok_kodu(ana_kod: str, sira: int) -> str:
    if PG_MOD:
        return ana_kod
    return f"{ana_kod}-V{int(sira):02d}"


def _yymm() -> str:
    return datetime.now().strftime("%y%m")


def _barkod_bos_mu(cur, barkod: str, haric_id: int) -> bool:
    cur.execute("SELECT id FROM urunler WHERE barkod = ? AND id != ?", (barkod, haric_id))
    return cur.fetchone() is None


def _barkod_sec(cur, aday: str, haric_id: int) -> str:
    deneme = aday
    for n in range(0, 80):
        if n:
            deneme = f"{aday}-{n}"
        if _barkod_bos_mu(cur, deneme, haric_id):
            return deneme
    return f"{aday}-{haric_id}"


def _cocuk_barkod(cur, ana_kod: str, beden, sira: int, haric_id: int) -> str:
    sayi = re.sub(r"[^0-9]", "", ana_kod.split("-", 1)[-1]) or "0000"
    e = _ek(beden) or f"{int(sira) % 100:02d}"
    return _barkod_sec(cur, f"KZM-{_yymm()}{sayi}{e}", haric_id)


def _yedek_json(cur, idler: list) -> str:
    klasor = Path(__file__).resolve().parent.parent / "yedekler"
    klasor.mkdir(parents=True, exist_ok=True)
    tum = set(int(i) for i in idler)
    for i in list(tum):
        cur.execute("SELECT id FROM urunler WHERE parent_id = ?", (i,))
        tum.update(int(r["id"]) for r in cur.fetchall())
    veri = []
    for i in sorted(tum):
        cur.execute("SELECT * FROM urunler WHERE id = ?", (i,))
        r = cur.fetchone()
        if r:
            veri.append(dict(r))
    yol = klasor / f"denetci_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    yol.write_text(json.dumps(veri, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return str(yol)


def havuz_listele() -> list:
    sema_hazirla()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT stok_kodu, eklenme, kaynak FROM kod_havuzu ORDER BY stok_kodu")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _havuza_ekle(cur, kod: str, kaynak: str) -> None:
    if not KOD_RE.match(kod or ""):
        return
    cur.execute("SELECT 1 AS x FROM urunler WHERE aktif = 1 AND stok_kodu = ?", (kod,))
    if cur.fetchone():
        return
    cur.execute("SELECT 1 AS x FROM kod_havuzu WHERE stok_kodu = ?", (kod,))
    if cur.fetchone():
        return
    cur.execute(
        "INSERT INTO kod_havuzu (stok_kodu, eklenme, kaynak) VALUES (?, ?, ?)",
        (kod, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), kaynak),
    )


def ayni_isim_gruplari(min_adet: int = 2) -> list:
    """Adi birebir ayni (buyuk/kucuk harf ve bosluk farksiz) aktif ana urun gruplari."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT u.id, u.stok_kodu, u.barkod, u.ad, u.beden, u.renk,
                      COALESCE(u.stok_adedi, 0) AS stok_adedi,
                      (SELECT COUNT(*) FROM urunler v WHERE v.parent_id = u.id AND v.aktif = 1) AS varyant_sayisi
               FROM urunler u
               WHERE u.aktif = 1 AND (u.parent_id IS NULL OR u.parent_id = 0)
               ORDER BY u.id"""
        )
        gruplar = {}
        for r in cur.fetchall():
            d = dict(r)
            d["beden_tahmin"] = beden_cikar(d)
            gruplar.setdefault(_ad_anahtar(r["ad"]), []).append(d)
        sonuc = [
            {"ad": g[0]["ad"], "urunler": g}
            for g in gruplar.values() if len(g) >= min_adet
        ]
        sonuc.sort(key=lambda x: _ad_anahtar(x["ad"]))
        return sonuc
    finally:
        conn.close()


def _toplam(r) -> tuple:
    return (
        int(r.get("stok_adedi") or 0), int(r.get("wix_stok") or 0),
        int(r.get("etsy_stok") or 0), int(r.get("trendyol_stok") or 0),
    )


def _yeniden_bagla(cur, eski_id: int, yeni_id: int) -> None:
    for tablo in ("satislar", "stok_hareketleri", "sayim_satir"):
        try:
            cur.execute(f"UPDATE {tablo} SET urun_id = ? WHERE urun_id = ?", (yeni_id, eski_id))
        except Exception:
            pass


def urunleri_birlestir(ana_id: int, diger_idler: list) -> dict:
    """
    Digerlerini ana urunun varyanti yapar. Ayni bedenli olanlarin stogu toplanir,
    satis/stok gecmisi yeni satira baglanir, ortadan kalkan KZM kodlari havuza girer.
    """
    sema_hazirla()
    ana_id = int(ana_id)
    diger_idler = [int(i) for i in diger_idler if int(i) != ana_id]
    if not diger_idler:
        return {"ok": False, "mesaj": "Birlestirilecek baska urun secilmedi"}
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM urunler WHERE id = ? AND aktif = 1", (ana_id,))
        ana = cur.fetchone()
        if not ana:
            return {"ok": False, "mesaj": "Ana urun bulunamadi"}
        ana = dict(ana)
        kod = (ana.get("stok_kodu") or "").strip()
        yedek = _yedek_json(cur, [ana_id] + diger_idler)

        cur.execute("SELECT * FROM urunler WHERE parent_id = ? AND aktif = 1 ORDER BY id", (ana_id,))
        cocuklar = [dict(r) for r in cur.fetchall()]
        if not cocuklar:
            m, w, e, t = _toplam(ana)
            cur.execute(
                """INSERT INTO urunler (stok_kodu, barkod, ad, kategori_id, marka, beden, renk,
                       alis_fiyati, satis_fiyati, stok_adedi, kritik_stok, aciklama, aktif,
                       parent_id, kod_hazir, gorsel_yolu, wix_stok, etsy_stok, trendyol_stok)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 1, ?, ?, ?, ?)""",
                (
                    cocuk_stok_kodu(kod, 0), "_GECICI_", ana["ad"], ana.get("kategori_id"),
                    ana.get("marka"), beden_cikar(ana) or None, ana.get("renk"),
                    float(ana.get("alis_fiyati") or 0), float(ana.get("satis_fiyati") or 0),
                    m, int(ana.get("kritik_stok") or 3), ana.get("aciklama"), ana_id,
                    ana.get("gorsel_yolu"), w, e, t,
                ),
            )
            cur.execute("SELECT id FROM urunler WHERE barkod = ?", ("_GECICI_",))
            yid = int(cur.fetchone()["id"])
            cur.execute(
                "UPDATE urunler SET barkod = ? WHERE id = ?",
                (_cocuk_barkod(cur, kod, beden_cikar(ana), 0, yid), yid),
            )
            cur.execute(
                "UPDATE urunler SET wix_stok=0, etsy_stok=0, trendyol_stok=0 WHERE id = ?", (ana_id,)
            )
            cur.execute("SELECT * FROM urunler WHERE id = ?", (yid,))
            cocuklar = [dict(cur.fetchone())]

        eklenen = 0
        toplanan = 0
        serbest = []
        for did in diger_idler:
            cur.execute("SELECT * FROM urunler WHERE id = ? AND aktif = 1", (did,))
            o = cur.fetchone()
            if not o:
                continue
            o = dict(o)
            serbest.append((o.get("stok_kodu") or "").strip())
            cur.execute("SELECT * FROM urunler WHERE parent_id = ? AND aktif = 1 ORDER BY id", (did,))
            alt = [dict(r) for r in cur.fetchall()]
            birimler = alt if alt else [o]
            for u in birimler:
                ek = _ek(beden_cikar(u))
                hedef = next((c for c in cocuklar if _ek(beden_cikar(c)) == ek), None)
                if hedef:
                    m, w, e, t = _toplam(u)
                    cur.execute(
                        """UPDATE urunler SET stok_adedi = COALESCE(stok_adedi,0) + ?,
                               wix_stok = COALESCE(wix_stok,0) + ?, etsy_stok = COALESCE(etsy_stok,0) + ?,
                               trendyol_stok = COALESCE(trendyol_stok,0) + ? WHERE id = ?""",
                        (m, w, e, t, hedef["id"]),
                    )
                    _yeniden_bagla(cur, u["id"], hedef["id"])
                    cur.execute(
                        """UPDATE urunler SET aktif = 0, stok_adedi = 0, wix_stok = 0, etsy_stok = 0,
                               trendyol_stok = 0, eski_stok_kodu = ?, eski_barkod = ?,
                               aciklama = ?, guncelleme = datetime('now','localtime') WHERE id = ?""",
                        (u.get("stok_kodu"), u.get("barkod"),
                         f"[BIRLESTIRILDI] {kod} ile birlestirildi (id {hedef['id']})", u["id"]),
                    )
                    toplanan += 1
                else:
                    sira = len(cocuklar)
                    cur.execute(
                        """UPDATE urunler SET parent_id = ?, stok_kodu = ?, eski_stok_kodu = ?,
                               eski_barkod = ?, kod_hazir = 1, beden = ?, gorsel_yolu = COALESCE(gorsel_yolu, ?),
                               guncelleme = datetime('now','localtime') WHERE id = ?""",
                        (ana_id, cocuk_stok_kodu(kod, sira), u.get("stok_kodu"), u.get("barkod"),
                         beden_cikar(u) or None, ana.get("gorsel_yolu"), u["id"]),
                    )
                    cur.execute(
                        "UPDATE urunler SET barkod = ? WHERE id = ?",
                        (_cocuk_barkod(cur, kod, beden_cikar(u), sira, u["id"]), u["id"]),
                    )
                    cur.execute("SELECT * FROM urunler WHERE id = ?", (u["id"],))
                    cocuklar.append(dict(cur.fetchone()))
                    eklenen += 1
            if alt:
                _yeniden_bagla(cur, did, ana_id)
                cur.execute(
                    """UPDATE urunler SET aktif = 0, stok_adedi = 0, wix_stok = 0, etsy_stok = 0,
                           trendyol_stok = 0, eski_stok_kodu = ?, eski_barkod = ?, aciklama = ?,
                           guncelleme = datetime('now','localtime') WHERE id = ?""",
                    (o.get("stok_kodu"), o.get("barkod"),
                     f"[BIRLESTIRILDI] {kod} ile birlestirildi (id {ana_id})", did),
                )

        bedenler = []
        for c in cocuklar:
            b = beden_cikar(c)
            if b and b not in bedenler:
                bedenler.append(b)
        from core.urun_servis import varyant_ana_stok_toplam_yaz
        varyant_ana_stok_toplam_yaz(cur, ana_id)
        cur.execute("UPDATE urunler SET beden = ? WHERE id = ?", (",".join(bedenler) or None, ana_id))
        for k in set(serbest):
            if k and k != kod:
                _havuza_ekle(cur, k, f"birlestirme:{kod}")
        conn.commit()
        msg = (f"Birlestirildi: {kod} | yeni varyant: {eklenen}, stogu toplanan: {toplanan} | "
               f"yedek: {yedek}")
        log_info(msg)
        return {"ok": True, "mesaj": msg}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_error("Urun birlestirme", e, __file__, "urunleri_birlestir")
        return {"ok": False, "mesaj": f"Hata, islem geri alindi: {e}"}
    finally:
        conn.close()


def _maks_sira(cur) -> int:
    cur.execute("SELECT stok_kodu FROM urunler")
    en = 0
    for r in cur.fetchall():
        m = re.match(r"^KZM-(\d{4})(?!\d)", (r["stok_kodu"] or "").upper())
        if m:
            en = max(en, int(m.group(1)))
    try:
        en = max(en, int(get_ayar("son_stok_sira", "0") or 0))
    except Exception:
        pass
    return en


def _standart_plan(cur) -> tuple:
    cur.execute(
        "SELECT id, stok_kodu, barkod, ad, beden, parent_id FROM urunler WHERE aktif = 1 ORDER BY id"
    )
    satirlar = [dict(r) for r in cur.fetchall()]
    ana = [r for r in satirlar if not r["parent_id"]]
    cocuk = {}
    for r in satirlar:
        if r["parent_id"]:
            cocuk.setdefault(int(r["parent_id"]), []).append(r)
    cur.execute("SELECT stok_kodu FROM kod_havuzu ORDER BY stok_kodu")
    havuz = [r["stok_kodu"] for r in cur.fetchall()]
    sira = _maks_sira(cur)
    plan = []
    havuz_kullanilan = []
    for a in ana:
        eski = (a["stok_kodu"] or "").strip()
        if KOD_RE.match(eski.upper()):
            hedef = eski.upper()
        else:
            if havuz:
                hedef = havuz.pop(0)
                havuz_kullanilan.append(hedef)
            else:
                sira += 1
                hedef = f"KZM-{sira:04d}"
        plan.append({
            "id": a["id"], "ad": a["ad"], "eski": eski, "yeni": hedef,
            "degisir": hedef != eski, "cocuklar": cocuk.get(a["id"], []),
        })
    return plan, havuz_kullanilan, sira


def standart_onizle() -> list:
    """KZM-0000 formatinda olmayan ana urunler ve onerilen yeni kodlari."""
    sema_hazirla()
    conn = get_connection()
    try:
        cur = conn.cursor()
        plan, _, _ = _standart_plan(cur)
        sonuc = []
        for p in plan:
            esit_degil = [c for c in p["cocuklar"] if PG_MOD and (c["stok_kodu"] or "") != p["yeni"]]
            if p["degisir"] or esit_degil:
                sonuc.append({
                    "id": p["id"], "ad": p["ad"], "eski": p["eski"], "yeni": p["yeni"],
                    "varyant_sayisi": len(p["cocuklar"]),
                    "tur": "yeni kod" if p["degisir"] else "varyant kodlarini esitle",
                })
        return sonuc
    finally:
        conn.close()


def standart_uygula(idler: list | None = None) -> dict:
    """Secili (veya tum) urunlere KZM-0000 kodu atar; varyant kodlari ana ile ayni olur."""
    sema_hazirla()
    secili = None if idler is None else set(int(i) for i in idler)
    conn = get_connection()
    try:
        cur = conn.cursor()
        plan, havuz_kullanilan, sira = _standart_plan(cur)
        yedek = _yedek_json(cur, [p["id"] for p in plan if secili is None or p["id"] in secili])
        degisen = 0
        yymm = _yymm()
        for p in plan:
            if secili is not None and p["id"] not in secili:
                continue
            yeni = p["yeni"]
            if p["degisir"]:
                sayi = yeni.split("-", 1)[1]
                cur.execute("SELECT barkod FROM urunler WHERE id = ?", (p["id"],))
                eski_barkod = cur.fetchone()["barkod"]
                cur.execute(
                    "UPDATE urunler SET stok_kodu = ?, eski_stok_kodu = ?, eski_barkod = ?, "
                    "guncelleme = datetime('now','localtime') WHERE id = ?",
                    (yeni, p["eski"], eski_barkod, p["id"]),
                )
                cur.execute(
                    "UPDATE urunler SET barkod = ? WHERE id = ?",
                    (_barkod_sec(cur, f"KZM-{yymm}{sayi}", p["id"]), p["id"]),
                )
                degisen += 1
            for i, c in enumerate(p["cocuklar"]):
                kod_c = cocuk_stok_kodu(yeni, i)
                if p["degisir"]:
                    cur.execute("SELECT barkod FROM urunler WHERE id = ?", (c["id"],))
                    eb = cur.fetchone()["barkod"]
                    cur.execute(
                        "UPDATE urunler SET stok_kodu = ?, eski_stok_kodu = ?, eski_barkod = ? WHERE id = ?",
                        (kod_c, c["stok_kodu"], eb, c["id"]),
                    )
                    cur.execute(
                        "UPDATE urunler SET barkod = ? WHERE id = ?",
                        (_cocuk_barkod(cur, yeni, beden_cikar(c), i, c["id"]), c["id"]),
                    )
                elif PG_MOD and (c["stok_kodu"] or "") != kod_c:
                    cur.execute(
                        "UPDATE urunler SET stok_kodu = ?, eski_stok_kodu = ? WHERE id = ?",
                        (kod_c, c["stok_kodu"], c["id"]),
                    )
        for k in havuz_kullanilan:
            if secili is None or any(p["yeni"] == k and p["id"] in secili for p in plan):
                cur.execute("DELETE FROM kod_havuzu WHERE stok_kodu = ?", (k,))
        conn.commit()
        try:
            if sira > int(get_ayar("son_stok_sira", "0") or 0):
                set_ayar("son_stok_sira", str(sira))
        except Exception:
            pass
        msg = f"{degisen} urunun stok kodu standartlandi. Yedek: {yedek}"
        log_info(msg)
        return {"ok": True, "mesaj": msg}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_error("Stok kodu standartlama", e, __file__, "standart_uygula")
        return {"ok": False, "mesaj": f"Hata, islem geri alindi: {e}"}
    finally:
        conn.close()
