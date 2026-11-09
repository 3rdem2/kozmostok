# -*- coding: utf-8 -*-
"""
Gun sonu kasa ve stok Excel raporlari
Kasa: raporlar/kasa/YYYY-MM/gun_sonu_YYYYMMDD.xlsx
Stok: raporlar/stok/stok_listesi_....xlsx
"""

from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill

from core.database import get_connection, BASE_DIR
from core.logger import log_error, log_info
from core.satis_servis import gunluk_ozet


RAPOR_DIR = BASE_DIR / "raporlar"
KASA_DIR = RAPOR_DIR / "kasa"
STOK_DIR = RAPOR_DIR / "stok"


def _stil_baslik(ws, row, cols):
    fill = PatternFill("solid", fgColor="1A1A1A")
    font = Font(bold=True, color="FFFFFF")
    for c in range(1, cols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center")


def _aylik_kasa_klasor(gun: str) -> Path:
    ay = gun[:7] if len(gun) >= 7 else datetime.now().strftime("%Y-%m")
    klasor = KASA_DIR / ay
    klasor.mkdir(parents=True, exist_ok=True)
    return klasor


def gun_sonu_excel(gun: str | None = None, otomatik: bool = False) -> tuple[bool, str]:
    """
    Gunluk kasa raporu.
    raporlar/kasa/YYYY-MM/gun_sonu_YYYYMMDD.xlsx
    otomatik=True ise dosya adina _otomatik eklenir (program kapanisi).
    """
    try:
        if not gun:
            gun = date.today().isoformat()
        ay_klasor = _aylik_kasa_klasor(gun)
        ozet = gunluk_ozet(gun)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT s.satis_saati, u.stok_kodu, u.ad, s.adet, s.birim_fiyat,
                   s.indirim, s.odeme_tipi, s.banka, s.toplam, s.fis_no
            FROM satislar s
            JOIN urunler u ON u.id = s.urun_id
            WHERE s.satis_tarihi = ?
            ORDER BY s.id
        """, (gun,))
        satislar = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT masraf_tarihi, tutar, aciklama, olusturma
            FROM masraflar WHERE masraf_tarihi = ? ORDER BY id
        """, (gun,))
        masraflar = [dict(r) for r in cur.fetchall()]
        conn.close()

        wb = Workbook()
        ws = wb.active
        ws.title = "Ozet"
        ws["A1"] = "KOZMOSIZE Gunluk Kasa Raporu"
        ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = f"Tarih: {gun}"
        if otomatik:
            ws["A3"] = f"Otomatik yedek: {datetime.now().strftime('%H:%M:%S')}"
        ws["A5"] = "Ciro"
        ws["B5"] = ozet["ciro"]
        ws["A6"] = "Nakit"
        ws["B6"] = ozet["nakit"]
        ws["A7"] = "Kart"
        ws["B7"] = ozet["kart"]
        ws["A8"] = "Masraf"
        ws["B8"] = ozet["masraf"]
        ws["A9"] = "Net"
        ws["B9"] = ozet["net"]
        ws["A10"] = "Satis adedi"
        ws["B10"] = ozet["adet_satis"]
        ws.column_dimensions["A"].width = 18
        ws.column_dimensions["B"].width = 16

        ws2 = wb.create_sheet("Satislar")
        headers = ["Saat", "Fis", "Stok Kodu", "Urun", "Adet", "Birim", "Indirim", "Odeme", "Banka", "Toplam"]
        for i, h in enumerate(headers, 1):
            ws2.cell(1, i, h)
        _stil_baslik(ws2, 1, len(headers))
        for r, s in enumerate(satislar, 2):
            ws2.cell(r, 1, s.get("satis_saati") or "")
            ws2.cell(r, 2, s.get("fis_no") or "")
            ws2.cell(r, 3, s.get("stok_kodu") or "")
            ws2.cell(r, 4, s.get("ad") or "")
            ws2.cell(r, 5, s.get("adet") or 0)
            ws2.cell(r, 6, s.get("birim_fiyat") or 0)
            ws2.cell(r, 7, s.get("indirim") or 0)
            ws2.cell(r, 8, s.get("odeme_tipi") or "")
            ws2.cell(r, 9, s.get("banka") or "")
            ws2.cell(r, 10, s.get("toplam") or 0)
        ws2.column_dimensions["D"].width = 32

        ws3 = wb.create_sheet("Masraflar")
        for i, h in enumerate(["Tarih", "Tutar", "Aciklama", "Kayit"], 1):
            ws3.cell(1, i, h)
        _stil_baslik(ws3, 1, 4)
        for r, m in enumerate(masraflar, 2):
            ws3.cell(r, 1, m.get("masraf_tarihi") or "")
            ws3.cell(r, 2, m.get("tutar") or 0)
            ws3.cell(r, 3, m.get("aciklama") or "")
            ws3.cell(r, 4, m.get("olusturma") or "")
        ws3.column_dimensions["C"].width = 40

        ek = "_otomatik" if otomatik else ""
        dosya = ay_klasor / f"gun_sonu_{gun.replace('-', '')}{ek}.xlsx"
        wb.save(dosya)
        log_info(f"Kasa raporu: {dosya}")
        return True, str(dosya)
    except Exception as e:
        log_error("Gun sonu Excel hatasi", e, __file__, "gun_sonu_excel")
        return False, str(e)


def stok_listesi_excel() -> tuple[bool, str]:
    """Stok listesi: raporlar/stok/ altina."""
    try:
        STOK_DIR.mkdir(parents=True, exist_ok=True)
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.stok_kodu, u.barkod, u.ad, k.ad AS kategori,
                   u.beden, u.renk, u.alis_fiyati, u.satis_fiyati,
                   u.stok_adedi, COALESCE(u.etsy_stok, 0), COALESCE(u.trendyol_stok, 0),
                   u.kritik_stok, u.marka
            FROM urunler u
            LEFT JOIN kategoriler k ON k.id = u.kategori_id
            WHERE u.aktif = 1
            ORDER BY u.ad
        """)
        rows = cur.fetchall()
        conn.close()

        wb = Workbook()
        ws = wb.active
        ws.title = "Stok"
        headers = [
            "Stok Kodu", "Barkod", "Urun", "Kategori", "Beden", "Renk",
            "Alis", "Satis", "Magaza Stok", "Etsy Stok", "Trendyol Stok",
            "Kritik", "Marka",
        ]
        for i, h in enumerate(headers, 1):
            ws.cell(1, i, h)
        _stil_baslik(ws, 1, len(headers))
        for r, row in enumerate(rows, 2):
            for c, val in enumerate(row, 1):
                ws.cell(r, c, val if val is not None else "")
        ws.column_dimensions["C"].width = 36

        dosya = STOK_DIR / f"stok_listesi_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        wb.save(dosya)
        log_info(f"Stok listesi: {dosya}")
        return True, str(dosya)
    except Exception as e:
        log_error("Stok Excel hatasi", e, __file__, "stok_listesi_excel")
        return False, str(e)


def sayim_excel(oturum_id: int) -> tuple[bool, str]:
    """Sayim listesi Excel (barkod dahil): raporlar/stok/ altina."""
    try:
        from core.sayim_servis import sayim_liste
        STOK_DIR.mkdir(parents=True, exist_ok=True)
        rows = sayim_liste(int(oturum_id))
        wb = Workbook()
        ws = wb.active
        ws.title = "Sayim"
        headers = ["Stok Kodu", "Barkod", "Urun", "Sistem", "Sayilan", "Fark"]
        for i, h in enumerate(headers, 1):
            ws.cell(1, i, h)
        _stil_baslik(ws, 1, len(headers))
        for r, row in enumerate(rows, 2):
            ws.cell(r, 1, row.get("stok_kodu") or "")
            ws.cell(r, 2, row.get("barkod") or "")
            ws.cell(r, 3, row.get("ad") or "")
            ws.cell(r, 4, int(row.get("sistem_stok") or 0))
            ws.cell(r, 5, "" if row.get("sayilan_stok") is None else int(row.get("sayilan_stok")))
            ws.cell(r, 6, "" if row.get("fark") is None else int(row.get("fark")))
        ws.column_dimensions["C"].width = 36
        dosya = STOK_DIR / f"sayim_{int(oturum_id)}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        wb.save(dosya)
        log_info(f"Sayim Excel: {dosya}")
        return True, str(dosya)
    except Exception as e:
        log_error("Sayim Excel", e, __file__, "sayim_excel")
        return False, str(e)


def kapanis_yedek() -> tuple[bool, str]:
    """Program kapanirken otomatik gunluk kasa yedegi."""
    return gun_sonu_excel(otomatik=True)


def stok_sablon_excel() -> tuple[bool, str]:
    """Toplu stok guncelleme icin ornek Excel."""
    try:
        STOK_DIR.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        ws = wb.active
        ws.title = "StokGuncelle"
        ws.append(["stok_kodu", "barkod", "yeni_stok", "aciklama"])
        ws.append(["ORNEK-KOD", "", 10, "ornek satir - silin"])
        # mevcut urunlerden ornek
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT stok_kodu, barkod, stok_adedi FROM urunler WHERE aktif=1 ORDER BY ad LIMIT 20"
        )
        for row in cur.fetchall():
            ws.append([row["stok_kodu"], row["barkod"] or "", row["stok_adedi"], ""])
        conn.close()
        dosya = STOK_DIR / "stok_guncelle_sablon.xlsx"
        wb.save(dosya)
        return True, str(dosya)
    except Exception as e:
        log_error("Stok sablon hatasi", e, __file__, "stok_sablon_excel")
        return False, str(e)




def stok_excel_yukle(yol: str | Path) -> dict:
    """Geriye uyumlu: magaza kanalina yukler (Trendyol kolonlari destekli)."""
    return stok_excel_yukle_kanal(yol, varsayilan_kanal="magaza")

def stok_sablon_excel_kanal(kanal: str = "magaza") -> tuple[bool, str]:
    """Kanal bazli stok guncelleme sablonu."""
    try:
        kolon_map = {
            "magaza": "stok_adedi",
            "wix": "wix_stok",
            "etsy": "etsy_stok",
            "trendyol": "trendyol_stok",
        }
        kolon = kolon_map.get(kanal, "stok_adedi")
        STOK_DIR.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        ws = wb.active
        ws.title = "StokGuncelle"
        ws.append(["stok_kodu", "barkod", "yeni_stok", "kanal", "aciklama"])
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            f"SELECT stok_kodu, barkod, COALESCE({kolon},0) AS s FROM urunler WHERE aktif=1 ORDER BY ad LIMIT 30"
        )
        for row in cur.fetchall():
            ws.append([row["stok_kodu"], row["barkod"] or "", row["s"], kanal, ""])
        conn.close()
        dosya = STOK_DIR / f"stok_sablon_{kanal}.xlsx"
        wb.save(dosya)
        return True, str(dosya)
    except Exception as e:
        log_error("Kanal sablon", e, __file__, "stok_sablon_excel_kanal")
        return False, str(e)


def _excel_baslik_bul(rows):
    """Trendyol vb. cok satirli basliklari atlar; barkod iceren satiri baslik sayar."""
    for idx, row in enumerate(rows[:15]):
        cells = [str(c or "").strip().lower() for c in row]
        joined = " | ".join(cells)
        if "barkod" in joined or "barcode" in joined:
            return idx, cells
    if rows:
        return 0, [str(c or "").strip().lower() for c in rows[0]]
    return 0, []


def _col_index(header, *names):
    for n in names:
        n = n.lower().strip()
        for i, h in enumerate(header):
            h2 = h.replace("\n", " ").strip()
            if h2 == n or n in h2:
                return i
    return None


def stok_excel_yukle_kanal(yol: str | Path, varsayilan_kanal: str = "magaza") -> dict:
    """
    Excel toplu stok — Trendyol sablonu destekli.
    Taninan stok kolonlari: yeni_stok, urun stok adedi, stok adedi, stok, adet, miktar
    Taninan barkod/kod: barkod, stok kodu, model kodu, tedarikci stok kodu
    """
    from openpyxl import load_workbook
    from core.kanal_servis import KANAL_KOLON

    sonuc = {"ok": False, "guncellenen": 0, "bulunamayan": 0, "hata": 0, "mesaj": ""}
    guncellenen_idler: list[int] = []
    try:
        yol = Path(yol)
        wb = load_workbook(yol, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        if not rows:
            sonuc["mesaj"] = "Bos dosya"
            return sonuc

        hdr_i, header = _excel_baslik_bul(rows)
        i_kod = _col_index(
            header,
            "stok_kodu", "stok kodu", "sku", "kod", "model kodu",
            "tedarikçi stok kodu", "tedarikci stok kodu",
        )
        i_bar = _col_index(header, "barkod", "barcode")
        i_stok = _col_index(
            header,
            "yeni_stok", "urun stok adedi", "ürün stok adedi",
            "stok adedi", "stok_adedi", "stok", "adet", "miktar",
        )
        i_fiyat = _col_index(
            header,
            "trendyol satış fiyatı (tsf) (kdv dahil)",
            "trendyol satis fiyati", "satis fiyati", "fiyat",
            "piyasa satış fiyatı (kdv dahil)",
        )
        i_kanal = _col_index(header, "kanal", "channel")
        i_ack = _col_index(header, "aciklama", "not")

        if i_stok is None:
            sonuc["mesaj"] = (
                "Stok kolonu bulunamadi. "
                "Beklenen ornek: 'Ürün Stok Adedi' (Trendyol) veya 'yeni_stok'. "
                f"Baslik satiri: {header[:8]}"
            )
            return sonuc
        if i_kod is None and i_bar is None:
            sonuc["mesaj"] = "Barkod veya stok kodu kolonu bulunamadi."
            return sonuc

        conn = get_connection()
        cur = conn.cursor()
        for row in rows[hdr_i + 1:]:
            if not row:
                continue
            try:
                if i_stok >= len(row):
                    continue
                yeni = row[i_stok]
                if yeni is None or str(yeni).strip() == "":
                    continue
                # baslik tekrari / metin satirlarini atla
                if str(yeni).strip().lower() in ("opsiyonel", "ürün stok adedi", "stok adedi"):
                    continue
                try:
                    yeni = int(float(yeni))
                except (TypeError, ValueError):
                    continue

                kod = ""
                if i_kod is not None and i_kod < len(row) and row[i_kod] is not None:
                    kod = str(row[i_kod]).strip()
                bar = ""
                if i_bar is not None and i_bar < len(row) and row[i_bar] is not None:
                    bar = str(row[i_bar]).strip()
                if not kod and not bar:
                    continue
                if kod.upper().startswith("ORNEK"):
                    continue

                kanal = varsayilan_kanal
                if i_kanal is not None and i_kanal < len(row) and row[i_kanal]:
                    k = str(row[i_kanal]).strip().lower()
                    if k in KANAL_KOLON:
                        kanal = k

                ack = "Excel"
                if i_ack is not None and i_ack < len(row) and row[i_ack]:
                    ack = str(row[i_ack])

                # eslestirme: once barkod, sonra stok_kodu
                u = None
                if bar:
                    cur.execute(
                        "SELECT id FROM urunler WHERE aktif=1 AND barkod=? LIMIT 1",
                        (bar,),
                    )
                    u = cur.fetchone()
                if not u and kod:
                    cur.execute(
                        "SELECT id FROM urunler WHERE aktif=1 AND stok_kodu=? LIMIT 1",
                        (kod,),
                    )
                    u = cur.fetchone()
                if not u and bar:
                    cur.execute(
                        "SELECT id FROM urunler WHERE aktif=1 AND stok_kodu=? LIMIT 1",
                        (bar,),
                    )
                    u = cur.fetchone()
                if not u:
                    from core.urun_servis import eski_kodla_bul
                    eid = eski_kodla_bul(cur, bar) or eski_kodla_bul(cur, kod)
                    if eid:
                        u = {"id": eid}
                if not u:
                    # Trendyol satiri sistemde yoksa yeni urun olustur (barkod zorunlu)
                    ad = ""
                    i_ad = _col_index(header, "ürün adı", "urun adi", "urun ad", "ad", "name")
                    if i_ad is not None and i_ad < len(row) and row[i_ad]:
                        ad = str(row[i_ad]).strip()
                    if not ad:
                        ad = bar or kod
                    stok_kodu = kod or bar
                    barkod_val = bar or None
                    try:
                        from core.urun_servis import urun_ekle, barkod_uret
                        # barkod_uret may not exist - use simple
                    except Exception:
                        pass
                    try:
                        # benzersiz stok kodu
                        sk = stok_kodu
                        cur.execute("SELECT id FROM urunler WHERE stok_kodu=?", (sk,))
                        if cur.fetchone():
                            sk = f"{stok_kodu}-{bar or 'TY'}"[:40]
                        br = barkod_val
                        if br:
                            cur.execute("SELECT id FROM urunler WHERE barkod=?", (br,))
                            if cur.fetchone():
                                br = None
                        fiyat = 0.0
                        if i_fiyat is not None and i_fiyat < len(row) and row[i_fiyat]:
                            try:
                                fiyat = float(row[i_fiyat])
                            except Exception:
                                fiyat = 0.0
                        cur.execute(
                            """INSERT INTO urunler
                               (stok_kodu, barkod, ad, satis_fiyati, stok_adedi, trendyol_stok, aktif)
                               VALUES (?, ?, ?, ?, 0, 0, 1)""",
                            (sk, br, ad[:200], fiyat),
                        )
                        uid = cur.lastrowid
                        u = {"id": uid}
                        log_info(f"Trendyol excel yeni urun: {sk}")
                    except Exception as e:
                        sonuc["bulunamayan"] += 1
                        log_error(f"yeni urun: {e}", e, __file__, "stok_excel_yukle_kanal")
                        continue

                kolon = KANAL_KOLON.get(kanal, "stok_adedi")
                cur.execute(
                    f"SELECT COALESCE({kolon},0) AS eski FROM urunler WHERE id=?",
                    (u["id"],),
                )
                eski = int(cur.fetchone()["eski"])
                delta = yeni - eski
                cur.execute(
                    f"UPDATE urunler SET {kolon}=?, guncelleme=datetime('now','localtime') WHERE id=?",
                    (yeni, u["id"]),
                )
                cur.execute(
                    """INSERT INTO stok_hareketleri (urun_id, hareket_tipi, adet, aciklama)
                       VALUES (?, 'duzeltme', ?, ?)""",
                    (u["id"], delta, f"[excel/{kanal}] {ack} ({eski}->{yeni})"),
                )
                if i_fiyat is not None and i_fiyat < len(row) and row[i_fiyat] is not None:
                    try:
                        fiyat = float(row[i_fiyat])
                        if fiyat > 0:
                            cur.execute(
                                "UPDATE urunler SET satis_fiyati=? WHERE id=?",
                                (fiyat, u["id"]),
                            )
                    except (TypeError, ValueError):
                        pass
                guncellenen_idler.append(u["id"])
                sonuc["guncellenen"] += 1
            except Exception as e:
                sonuc["hata"] += 1
                log_error(f"excel kanal satir: {e}", e, __file__, "stok_excel_yukle_kanal")
        conn.commit()
        conn.close()
        if kanal == "magaza" and guncellenen_idler:
            from core.urun_servis import _bagli_ana_stogu_tazele
            for uid in sorted(set(guncellenen_idler)):
                _bagli_ana_stogu_tazele(uid)
        sonuc["ok"] = True
        sonuc["mesaj"] = (
            f"Guncellenen:{sonuc['guncellenen']} "
            f"Bulunamayan:{sonuc['bulunamayan']} Hata:{sonuc['hata']}"
        )
        return sonuc
    except Exception as e:
        log_error("stok_excel_yukle_kanal", e, __file__, "stok_excel_yukle_kanal")
        sonuc["mesaj"] = str(e)
        return sonuc
