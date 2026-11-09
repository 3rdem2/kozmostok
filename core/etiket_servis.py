# -*- coding: utf-8 -*-
"""Barkod etiketi: ZPL ham komut, .prn kaydi, Windows yazicisina ham gonderim.

Etiket olcusu mm, yazici cozunurlugu dpi (Argox OS-214 = 203 dpi).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from core.database import get_connection, get_ayar, set_ayar, BASE_DIR, barkod_normalize
from core.logger import log_error, log_info

ETIKET_DIR = BASE_DIR / "etiketler"

VARSAYILAN = {
    "genislik_mm": 50.0,
    "yukseklik_mm": 25.0,
    "bosluk_mm": 3.0,
    "dpi": 203,
    "dil": "zpl",
    "yazici": "",
}


@dataclass
class Etiket:
    barkod: str
    ad: str = ""
    beden: str = ""
    fiyat: float = 0.0
    stok_kodu: str = ""
    adet: int = 1
    urun_id: int = 0


def mm_dot(mm: float, dpi: int) -> int:
    return max(1, int(round(float(mm) / 25.4 * int(dpi))))


def etiket_ayarlari() -> dict:
    a = dict(VARSAYILAN)
    try:
        a["genislik_mm"] = float(get_ayar("etiket_genislik_mm", a["genislik_mm"]) or a["genislik_mm"])
        a["yukseklik_mm"] = float(get_ayar("etiket_yukseklik_mm", a["yukseklik_mm"]) or a["yukseklik_mm"])
        a["bosluk_mm"] = float(get_ayar("etiket_bosluk_mm", a["bosluk_mm"]) or a["bosluk_mm"])
        a["dpi"] = int(float(get_ayar("etiket_dpi", a["dpi"]) or a["dpi"]))
        a["dil"] = (get_ayar("etiket_dil", a["dil"]) or a["dil"]).strip().lower()
        a["yazici"] = get_ayar("etiket_yazici", a["yazici"]) or ""
    except Exception as e:
        log_error("Etiket ayarlari", e, __file__, "etiket_ayarlari")
    return a


def etiket_ayarlari_kaydet(**kw) -> bool:
    try:
        for k, v in kw.items():
            if k in VARSAYILAN:
                set_ayar(f"etiket_{k}", str(v))
        return True
    except Exception as e:
        log_error("Etiket ayar kaydet", e, __file__, "etiket_ayarlari_kaydet")
        return False


def urun_etiketleri(urun_id: int, adet: int = 1) -> list[Etiket]:
    """Urun + alt varyantlari icin etiket listesi. Varyant yoksa tek etiket."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM urunler WHERE id = ?", (urun_id,))
        ana = cur.fetchone()
        if not ana:
            conn.close()
            return []
        cur.execute(
            """SELECT * FROM urunler
               WHERE aktif = 1 AND parent_id = ? AND id <> ?
               ORDER BY beden, barkod""",
            (urun_id, urun_id),
        )
        altlar = [dict(r) for r in cur.fetchall()]
        conn.close()
        ana = dict(ana)
        kaynak = altlar or [ana]
        out: list[Etiket] = []
        for u in kaynak:
            out.append(
                Etiket(
                    barkod=barkod_normalize(u.get("barkod") or ""),
                    ad=(ana.get("ad") or u.get("ad") or "").strip(),
                    beden=(u.get("beden") or "").strip(),
                    fiyat=float(u.get("satis_fiyati") or ana.get("satis_fiyati") or 0),
                    stok_kodu=(u.get("stok_kodu") or "").strip(),
                    adet=max(1, int(adet)),
                    urun_id=int(u.get("id") or 0),
                )
            )
        return out
    except Exception as e:
        log_error(f"Etiket verisi: {urun_id}", e, __file__, "urun_etiketleri")
        return []


def _zpl_temiz(s: str) -> str:
    """ZPL komut karakterlerini ve satir sonlarini etkisizlestir."""
    s = (s or "").replace("^", " ").replace("~", " ").replace("\\", "/")
    return " ".join(s.split())


def _fiyat_yazi(deger: float) -> str:
    try:
        return f"{float(deger):,.0f}".replace(",", ".") + " TL"
    except Exception:
        return ""


def zpl_olustur(etiketler: list[Etiket], ayar: dict | None = None) -> str:
    """PPLZ (ZPL) ham komut dizisi. Her etiket kendi ^XA...^XZ blogunda."""
    a = ayar or etiket_ayarlari()
    dpi = int(a.get("dpi") or 203)
    w = mm_dot(a.get("genislik_mm", 50), dpi)
    h = mm_dot(a.get("yukseklik_mm", 25), dpi)
    parcalar: list[str] = []
    for e in etiketler:
        ad = _zpl_temiz(e.ad)[:34]
        beden = _zpl_temiz(e.beden)[:18]
        barkod = _zpl_temiz(e.barkod)
        fiyat = _fiyat_yazi(e.fiyat)
        y1 = int(h * 0.04)
        y2 = int(h * 0.18)
        y3 = int(h * 0.30)
        bc_h = int(h * 0.30)
        y4 = y3 + bc_h + int(h * 0.20)
        blok = [
            "^XA",
            f"^PW{w}",
            f"^LL{h}",
            "^LH0,0",
            "^CI28",
            f"^FO{int(w * 0.03)},{y1}^A0N,{max(16, int(h * 0.12))},{max(16, int(h * 0.12))}^FD{ad}^FS",
        ]
        if beden:
            blok.append(
                f"^FO{int(w * 0.03)},{y2}^A0N,{max(14, int(h * 0.10))},{max(14, int(h * 0.10))}^FDBeden: {beden}^FS"
            )
        blok.append(
            f"^FO{int(w * 0.03)},{y3}^BY2,2,{bc_h}^BCN,{bc_h},Y,N,N^FD{barkod}^FS"
        )
        if fiyat:
            blok.append(
                f"^FO{int(w * 0.03)},{y4}^A0N,{max(16, int(h * 0.12))},{max(16, int(h * 0.12))}^FD{fiyat}^FS"
            )
        blok.append(f"^PQ{max(1, int(e.adet))}")
        blok.append("^XZ")
        parcalar.append("\r\n".join(blok))
    return "\r\n".join(parcalar) + ("\r\n" if parcalar else "")


def prn_kaydet(icerik: str, ad: str = "etiket") -> tuple[bool, str]:
    try:
        ETIKET_DIR.mkdir(parents=True, exist_ok=True)
        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        yol = ETIKET_DIR / f"{ad}_{ts}.prn"
        yol.write_bytes(icerik.encode("utf-8"))
        log_info(f"Etiket PRN: {yol}")
        return True, str(yol)
    except Exception as e:
        log_error("PRN kaydet", e, __file__, "prn_kaydet")
        return False, str(e)


def csv_kaydet(etiketler: list[Etiket], ad: str = "etiket") -> tuple[bool, str]:
    """ArgoBar Pro / Excel icin veri dosyasi (sablon .apx'e veri kaynagi)."""
    try:
        import csv
        from datetime import datetime

        ETIKET_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        yol = ETIKET_DIR / f"{ad}_{ts}.csv"
        with open(yol, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["barkod", "urun", "beden", "fiyat", "stok_kodu", "adet"])
            for e in etiketler:
                w.writerow([e.barkod, e.ad, e.beden, f"{e.fiyat:.2f}", e.stok_kodu, e.adet])
        return True, str(yol)
    except Exception as e:
        log_error("CSV kaydet", e, __file__, "csv_kaydet")
        return False, str(e)


# ---------------------------------------------------------------------------
# Windows yazici erisimi (ctypes, ek bagimlilik yok)
# ---------------------------------------------------------------------------

class _DOC_INFO_1(ctypes.Structure):
    _fields_ = [
        ("pDocName", wintypes.LPWSTR),
        ("pOutputFile", wintypes.LPWSTR),
        ("pDatatype", wintypes.LPWSTR),
    ]


class _PRINTER_INFO_4(ctypes.Structure):
    _fields_ = [
        ("pPrinterName", wintypes.LPWSTR),
        ("pServerName", wintypes.LPWSTR),
        ("Attributes", wintypes.DWORD),
    ]


def _winspool():
    lib = ctypes.WinDLL("winspool.drv")
    lib.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), wintypes.LPVOID]
    lib.OpenPrinterW.restype = wintypes.BOOL
    lib.ClosePrinter.argtypes = [wintypes.HANDLE]
    lib.ClosePrinter.restype = wintypes.BOOL
    lib.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(_DOC_INFO_1)]
    lib.StartDocPrinterW.restype = wintypes.DWORD
    lib.EndDocPrinter.argtypes = [wintypes.HANDLE]
    lib.EndDocPrinter.restype = wintypes.BOOL
    lib.StartPagePrinter.argtypes = [wintypes.HANDLE]
    lib.StartPagePrinter.restype = wintypes.BOOL
    lib.EndPagePrinter.argtypes = [wintypes.HANDLE]
    lib.EndPagePrinter.restype = wintypes.BOOL
    lib.WritePrinter.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
    ]
    lib.WritePrinter.restype = wintypes.BOOL
    lib.EnumPrintersW.argtypes = [
        wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
    ]
    lib.EnumPrintersW.restype = wintypes.BOOL
    return lib


def yazicilar() -> list[str]:
    try:
        lib = _winspool()
        flags = 2 | 4  # LOCAL | CONNECTIONS
        gerekli = wintypes.DWORD(0)
        donen = wintypes.DWORD(0)
        lib.EnumPrintersW(flags, None, 4, None, 0, ctypes.byref(gerekli), ctypes.byref(donen))
        if gerekli.value == 0:
            return []
        buf = ctypes.create_string_buffer(gerekli.value)
        ok = lib.EnumPrintersW(
            flags, None, 4, buf, gerekli.value, ctypes.byref(gerekli), ctypes.byref(donen)
        )
        if not ok:
            return []
        arr = ctypes.cast(buf, ctypes.POINTER(_PRINTER_INFO_4))
        return [arr[i].pPrinterName for i in range(donen.value)]
    except Exception as e:
        log_error("Yazici listesi", e, __file__, "yazicilar")
        return []


def ham_yazdir(yazici: str, veri: str | bytes) -> tuple[bool, str]:
    """RAW datatype ile yaziciya gonderir (surucu render etmez)."""
    if not yazici:
        return False, "Yazici secilmedi"
    try:
        ham = veri.encode("utf-8") if isinstance(veri, str) else veri
        lib = _winspool()
        h = wintypes.HANDLE()
        if not lib.OpenPrinterW(yazici, ctypes.byref(h), None):
            return False, f"Yazici acilamadi: {yazici}"
        try:
            doc = _DOC_INFO_1("KozmoStok Etiket", None, "RAW")
            if not lib.StartDocPrinterW(h, 1, ctypes.byref(doc)):
                return False, "Baski isi baslatilamadi"
            try:
                if not lib.StartPagePrinter(h):
                    return False, "Baski sayfasi baslatilamadi"
                yazilan = wintypes.DWORD(0)
                buf = ctypes.create_string_buffer(ham, len(ham))
                ok = lib.WritePrinter(h, buf, len(ham), ctypes.byref(yazilan))
                lib.EndPagePrinter(h)
                if not ok:
                    return False, "Yaziciya veri yazilamadi"
            finally:
                lib.EndDocPrinter(h)
        finally:
            lib.ClosePrinter(h)
        log_info(f"Etiket yazdirildi: {yazici} ({len(ham)} bayt)")
        return True, f"{len(ham)} bayt gonderildi: {yazici}"
    except Exception as e:
        log_error("Ham yazdirma", e, __file__, "ham_yazdir")
        return False, str(e)
