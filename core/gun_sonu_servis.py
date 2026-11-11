# -*- coding: utf-8 -*-
"""Gun sonu: kasa sayimi, masraf listesi, devir zinciri, Excel arsivi.

Tablolar ilk kullanimda olusturulur (SQLite ve PostgreSQL uyumlu).
Excel dosyasi hem diske hem veritabanina (base64) yazilir; boylece baska
bilgisayarda da eski gun sonlari acilabilir.
"""

from __future__ import annotations

import base64
import io
import json
from datetime import date, datetime, timedelta

from core.database import BASE_DIR, get_ayar, get_connection, set_ayar
from core.logger import log_error, log_info

VARSAYILAN_KALEMLER = [
    {"ad": "Nakit kasa", "tur": "nakit"},
    {"ad": "Kredi karti slip", "tur": "kart"},
    {"ad": "Diger nakit", "tur": "diger"},
]


def tablolari_hazirla() -> bool:
    try:
        from core.database import PG_MOD

        pk = "SERIAL PRIMARY KEY" if PG_MOD else "INTEGER PRIMARY KEY AUTOINCREMENT"
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS gun_sonu (
                id              {pk},
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
            )
            """
        )
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS gun_sonu_kalem (
                id          {pk},
                gun_sonu_id INTEGER NOT NULL,
                ad          TEXT,
                tur         TEXT,
                tutar       DOUBLE PRECISION DEFAULT 0,
                adet        DOUBLE PRECISION DEFAULT 0,
                aciklama    TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_gun_sonu_tarih ON gun_sonu (tarih)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_gun_sonu_kalem_gs ON gun_sonu_kalem (gun_sonu_id)"
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log_error("Gun sonu tablolari", e, __file__, "tablolari_hazirla")
        return False


def _tarih_str(t: str | date | None = None) -> str:
    if isinstance(t, date):
        return t.strftime("%Y-%m-%d")
    if isinstance(t, str) and t.strip():
        return t.strip()[:10]
    return date.today().strftime("%Y-%m-%d")


def gun_ozeti(tarih: str | date | None = None) -> dict:
    """Satis ve masraf toplamlari (odeme tipine gore)."""
    t = _tarih_str(tarih)
    sonuc = {
        "tarih": t, "ciro": 0.0, "nakit": 0.0, "kart": 0.0,
        "diger": 0.0, "masraf": 0.0, "satis_adet": 0,
    }
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT coalesce(sum(toplam),0) AS ciro, count(*) AS adet,
                      coalesce(sum(CASE WHEN lower(odeme_tipi)='nakit' THEN toplam ELSE 0 END),0) AS nakit,
                      coalesce(sum(CASE WHEN lower(odeme_tipi)='kart' THEN toplam ELSE 0 END),0) AS kart
               FROM satislar WHERE substr(satis_tarihi,1,10)=?""",
            (t,),
        )
        r = cur.fetchone()
        if r:
            sonuc["ciro"] = float(r["ciro"] or 0)
            sonuc["nakit"] = float(r["nakit"] or 0)
            sonuc["kart"] = float(r["kart"] or 0)
            sonuc["satis_adet"] = int(r["adet"] or 0)
            sonuc["diger"] = max(0.0, sonuc["ciro"] - sonuc["nakit"] - sonuc["kart"])
        cur.execute(
            "SELECT coalesce(sum(tutar),0) AS m FROM masraflar WHERE substr(masraf_tarihi,1,10)=?",
            (t,),
        )
        sonuc["masraf"] = float((cur.fetchone() or {"m": 0})["m"] or 0)
        conn.close()
    except Exception as e:
        log_error(f"Gun ozeti: {t}", e, __file__, "gun_ozeti")
    return sonuc


def onceki_devir(tarih: str | date | None = None) -> tuple[float, str]:
    """Verilen tarihten onceki en son kapanan gun sonunun devri."""
    t = _tarih_str(tarih)
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT tarih, devir, sayilan_nakit FROM gun_sonu
               WHERE tarih < ? ORDER BY tarih DESC, id DESC LIMIT 1""",
            (t,),
        )
        r = cur.fetchone()
        conn.close()
        if not r:
            return 0.0, ""
        return float(r["devir"] if r["devir"] is not None else (r["sayilan_nakit"] or 0)), r["tarih"]
    except Exception as e:
        log_error("Onceki devir", e, __file__, "onceki_devir")
        return 0.0, ""


def _kalem_gecerli(k: dict) -> bool:
    """Cek ve iade kalemleri kaldirildi; eski kayitlarda varsa elenir."""
    ad = str(k.get("ad") or "").strip().lower()
    if not ad:
        return False
    return not ("cek" in ad or "iade" in ad or "kupon" in ad)


def sayim_kalemleri() -> list[dict]:
    ham = (get_ayar("gun_sonu_kalemleri", "") or "").strip()
    if ham:
        try:
            veri = json.loads(ham)
            if isinstance(veri, list):
                temiz = [k for k in veri if isinstance(k, dict) and _kalem_gecerli(k)]
                if temiz:
                    return temiz
        except Exception:
            pass
    return [dict(k) for k in VARSAYILAN_KALEMLER]


def sayim_kalemleri_kaydet(kalemler: list[dict]) -> bool:
    try:
        temiz = [
            {"ad": str(k.get("ad") or "").strip(), "tur": str(k.get("tur") or "diger")}
            for k in kalemler
            if str(k.get("ad") or "").strip()
        ]
        set_ayar("gun_sonu_kalemleri", json.dumps(temiz, ensure_ascii=False))
        return True
    except Exception as e:
        log_error("Sayim kalemleri", e, __file__, "sayim_kalemleri_kaydet")
        return False


def gun_sonu_var_mi(tarih: str | date | None = None) -> dict | None:
    t = _tarih_str(tarih)
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM gun_sonu WHERE tarih=? ORDER BY id DESC LIMIT 1", (t,))
        r = cur.fetchone()
        conn.close()
        return dict(r) if r else None
    except Exception as e:
        log_error("Gun sonu kontrol", e, __file__, "gun_sonu_var_mi")
        return None


def gun_sonu_kaydet(
    tarih: str | date | None,
    kullanici_adi: str,
    sifre: str,
    sayilan_nakit: float,
    kalemler: list[dict] | None = None,
    notlar: str = "",
    devir_birak: float | None = None,
) -> tuple[bool, str, int]:
    """Sifre dogrulanir, gun sonu kaydedilir, Excel uretilip arsivlenir."""
    from core.kullanici_servis import pin_dogrula

    t = _tarih_str(tarih)
    if not pin_dogrula(sifre, kullanici_adi):
        return False, "Sifre yanlis — gun sonu alinmadi", 0
    if gun_sonu_var_mi(t):
        return False, f"{t} icin gun sonu zaten alinmis", 0
    try:
        tablolari_hazirla()
        o = gun_ozeti(t)
        onceki, onceki_t = onceki_devir(t)
        beklenen = onceki + o["nakit"] - o["masraf"]
        sayilan = float(sayilan_nakit or 0)
        fark = sayilan - beklenen
        devir = float(devir_birak) if devir_birak is not None else sayilan

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM kullanicilar WHERE kullanici_adi=?", (kullanici_adi,))
        kr = cur.fetchone()
        kid = int(kr["id"]) if kr else None
        cur.execute(
            """INSERT INTO gun_sonu
               (tarih, kullanici, kullanici_id, ciro, nakit_satis, kart_satis, diger_satis,
                masraf, onceki_devir, beklenen_nakit, sayilan_nakit, fark, devir, notlar, olusturma)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                t, kullanici_adi, kid, o["ciro"], o["nakit"], o["kart"], o["diger"],
                o["masraf"], onceki, beklenen, sayilan, fark, devir, notlar,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        cur.execute("SELECT id FROM gun_sonu WHERE tarih=? ORDER BY id DESC LIMIT 1", (t,))
        gs_id = int(cur.fetchone()["id"])
        for k in kalemler or []:
            cur.execute(
                """INSERT INTO gun_sonu_kalem (gun_sonu_id, ad, tur, tutar, adet, aciklama)
                   VALUES (?,?,?,?,?,?)""",
                (
                    gs_id, str(k.get("ad") or ""), str(k.get("tur") or "diger"),
                    float(k.get("tutar") or 0), float(k.get("adet") or 0),
                    str(k.get("aciklama") or ""),
                ),
            )
        conn.commit()
        conn.close()

        ok, yol = excel_uret_ve_sakla(gs_id)
        log_info(
            f"Gun sonu: {t} kullanici={kullanici_adi} sayilan={sayilan:.2f} "
            f"beklenen={beklenen:.2f} fark={fark:.2f} excel={yol if ok else 'yok'}"
        )
        try:
            from core.sync_servis import senkronize
            snc = senkronize(bekleme=8.0, sessiz=True)
            if snc.get("ok"):
                log_info(
                    f"Gun sonu senkronu: +{snc.get('gonderilen', 0)} gonderildi, "
                    f"+{snc.get('alinan', 0)} alindi"
                )
        except Exception as e:
            log_error("Gun sonu senkronu", e, __file__, "gun_sonu_kaydet")
        mesaj = (
            f"{t} gun sonu kaydedildi.\n"
            f"Beklenen nakit: {beklenen:,.2f} TL\n"
            f"Sayilan nakit: {sayilan:,.2f} TL\n"
            f"Fark: {fark:,.2f} TL"
        )
        if not ok:
            mesaj += f"\nExcel uyarisi: {yol}"
        return True, mesaj, gs_id
    except Exception as e:
        log_error(f"Gun sonu kaydet: {t}", e, __file__, "gun_sonu_kaydet")
        return False, str(e), 0


def gun_sonu_getir(gs_id: int) -> dict | None:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM gun_sonu WHERE id=?", (int(gs_id),))
        r = cur.fetchone()
        if not r:
            conn.close()
            return None
        kayit = dict(r)
        cur.execute(
            "SELECT * FROM gun_sonu_kalem WHERE gun_sonu_id=? ORDER BY id", (int(gs_id),)
        )
        kayit["kalemler"] = [dict(x) for x in cur.fetchall()]
        conn.close()
        return kayit
    except Exception as e:
        log_error(f"Gun sonu getir: {gs_id}", e, __file__, "gun_sonu_getir")
        return None


def gun_sonu_listele(
    bas: str | date | None = None,
    bit: str | date | None = None,
    kullanici: str = "",
    limit: int = 500,
) -> list[dict]:
    try:
        tablolari_hazirla()
        b = _tarih_str(bas) if bas else "1900-01-01"
        s = _tarih_str(bit) if bit else "2999-12-31"
        sql = "SELECT * FROM gun_sonu WHERE tarih BETWEEN ? AND ?"
        par: list = [b, s]
        if (kullanici or "").strip():
            sql += " AND lower(kullanici) LIKE ?"
            par.append(f"%{kullanici.strip().lower()}%")
        sql += " ORDER BY tarih DESC, id DESC LIMIT ?"
        par.append(int(limit))
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql, tuple(par))
        kayitlar = [dict(r) for r in cur.fetchall()]
        conn.close()
        return kayitlar
    except Exception as e:
        log_error("Gun sonu listesi", e, __file__, "gun_sonu_listele")
        return []


def _excel_icerik(kayit: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Gun Sonu"
    baslik = Font(bold=True, size=13)
    kalin = Font(bold=True)
    dolgu = PatternFill("solid", fgColor="1F1F1F")
    beyaz = Font(bold=True, color="FFFFFF")

    ws["A1"] = "KOZMOSIZE foreverunderground — GUN SONU"
    ws["A1"].font = baslik
    ws["A2"] = f"Tarih: {kayit.get('tarih')}"
    ws["A3"] = f"Gun sonunu alan: {kayit.get('kullanici') or '-'}"
    ws["A4"] = f"Kayit zamani: {kayit.get('olusturma') or '-'}"

    satir = 6
    ws.cell(satir, 1, "KASA OZETI").font = kalin
    satir += 1
    for etiket, anahtar in (
        ("Ciro", "ciro"),
        ("Nakit satis", "nakit_satis"),
        ("Kart satis", "kart_satis"),
        ("Diger satis", "diger_satis"),
        ("Masraf", "masraf"),
        ("Onceki nakit devir", "onceki_devir"),
        ("Beklenen nakit", "beklenen_nakit"),
        ("Sayilan nakit", "sayilan_nakit"),
        ("Fark", "fark"),
        ("Devir (ertesi gune)", "devir"),
    ):
        ws.cell(satir, 1, etiket)
        c = ws.cell(satir, 2, float(kayit.get(anahtar) or 0))
        c.number_format = "#,##0.00"
        satir += 1

    satir += 1
    ws.cell(satir, 1, "SAYIM LISTESI").font = kalin
    satir += 1
    for i, h in enumerate(("Kalem", "Tur", "Tutar", "Adet", "Aciklama"), start=1):
        c = ws.cell(satir, i, h)
        c.font = beyaz
        c.fill = dolgu
        c.alignment = Alignment(horizontal="center")
    satir += 1
    for k in kayit.get("kalemler") or []:
        ws.cell(satir, 1, k.get("ad") or "")
        ws.cell(satir, 2, k.get("tur") or "")
        c = ws.cell(satir, 3, float(k.get("tutar") or 0))
        c.number_format = "#,##0.00"
        ws.cell(satir, 4, float(k.get("adet") or 0))
        ws.cell(satir, 5, k.get("aciklama") or "")
        satir += 1

    if kayit.get("notlar"):
        satir += 1
        ws.cell(satir, 1, "Notlar").font = kalin
        ws.cell(satir + 1, 1, str(kayit.get("notlar")))

    from core.log_servis import vardiya_listesi

    satir += 2
    ws.cell(satir, 1, "VARDIYA OZETI").font = kalin
    satir += 1
    for i, h in enumerate(("Kullanici", "Giris", "Cikis"), start=1):
        c = ws.cell(satir, i, h)
        c.font = beyaz
        c.fill = dolgu
        c.alignment = Alignment(horizontal="center")
    satir += 1
    for v in vardiya_listesi(str(kayit.get("tarih") or "")):
        ws.cell(satir, 1, v.get("kullanici") or "")
        ws.cell(satir, 2, f"{v.get('giris_tarihi') or ''} {(v.get('giris_saati') or '')[:5]}")
        ws.cell(
            satir, 3,
            f"{v.get('cikis_tarihi') or ''} {(v.get('cikis_saati') or 'acik')[:5]}".strip(),
        )
        satir += 1

    satir += 1
    ws.cell(satir, 1, "SATILAN URUNLER").font = kalin
    satir += 1
    for i, h in enumerate(("Saat", "Stok Kodu", "Urun", "Adet", "Birim", "Indirim", "Toplam"), start=1):
        c = ws.cell(satir, i, h)
        c.font = beyaz
        c.fill = dolgu
        c.alignment = Alignment(horizontal="center")
    satir += 1
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT s.satis_saati, u.stok_kodu, u.ad, s.adet, s.birim_fiyat,
                      s.indirim, s.toplam
               FROM satislar s JOIN urunler u ON u.id = s.urun_id
               WHERE s.satis_tarihi = ? ORDER BY s.id""",
            (str(kayit.get("tarih") or ""),),
        )
        satilan = [dict(r) for r in cur.fetchall()]
        conn.close()
    except Exception as e:
        log_error("Gun sonu satilanlar", e, __file__, "_excel_icerik")
        satilan = []
    for s2 in satilan:
        ws.cell(satir, 1, s2.get("satis_saati") or "")
        ws.cell(satir, 2, s2.get("stok_kodu") or "")
        ws.cell(satir, 3, s2.get("ad") or "")
        ws.cell(satir, 4, float(s2.get("adet") or 0))
        c = ws.cell(satir, 5, float(s2.get("birim_fiyat") or 0))
        c.number_format = "#,##0.00"
        c = ws.cell(satir, 6, float(s2.get("indirim") or 0))
        c.number_format = "#,##0.00"
        c = ws.cell(satir, 7, float(s2.get("toplam") or 0))
        c.number_format = "#,##0.00"
        satir += 1

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 34
    ws.column_dimensions["F"].width = 12
    ws.column_dimensions["G"].width = 12

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def excel_uret_ve_sakla(gs_id: int) -> tuple[bool, str]:
    """Excel'i diske yazar ve base64 olarak veritabanina isler."""
    try:
        kayit = gun_sonu_getir(gs_id)
        if not kayit:
            return False, "Kayit yok"
        veri = _excel_icerik(kayit)
        klasor = BASE_DIR / "raporlar"
        klasor.mkdir(parents=True, exist_ok=True)
        yol = klasor / f"gun_sonu_{kayit['tarih']}_{gs_id}.xlsx"
        yol.write_bytes(veri)
        b64 = base64.b64encode(veri).decode("ascii")
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE gun_sonu SET excel_yolu=?, excel_b64=? WHERE id=?",
            (str(yol), b64, int(gs_id)),
        )
        conn.commit()
        conn.close()
        return True, str(yol)
    except Exception as e:
        log_error(f"Gun sonu excel: {gs_id}", e, __file__, "excel_uret_ve_sakla")
        return False, str(e)


def excel_dosyasi(gs_id: int) -> tuple[bool, str]:
    """Arsivdeki Excel'i gecici dosyaya cikarir (acmak/kaydetmek icin)."""
    try:
        kayit = gun_sonu_getir(gs_id)
        if not kayit:
            return False, "Kayit yok"
        b64 = (kayit.get("excel_b64") or "").strip()
        if not b64:
            ok, yol = excel_uret_ve_sakla(gs_id)
            if not ok:
                return False, yol
            return True, yol
        import tempfile

        hedef = (
            BASE_DIR / "raporlar" / f"gun_sonu_{kayit['tarih']}_{int(gs_id)}.xlsx"
        )
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_bytes(base64.b64decode(b64))
        return True, str(hedef)
    except Exception as e:
        log_error(f"Excel dosyasi: {gs_id}", e, __file__, "excel_dosyasi")
        return False, str(e)


def devir_ozeti(tarih: str | date | None = None) -> dict:
    """Magaza ekrani icin: dunku devir + bugunun beklenen nakdi."""
    t = _tarih_str(tarih)
    onceki, onceki_t = onceki_devir(t)
    o = gun_ozeti(t)
    return {
        "onceki_devir": onceki,
        "onceki_tarih": onceki_t,
        "nakit_satis": o["nakit"],
        "masraf": o["masraf"],
        "beklenen_nakit": onceki + o["nakit"] - o["masraf"],
        "gun_sonu_alindi": bool(gun_sonu_var_mi(t)),
    }
