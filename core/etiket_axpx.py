# -*- coding: utf-8 -*-
"""ArgoDesigner (.axpx) etiket ureteci.

.axpx aslinda JSON'dur: panelData (etiket olcusu) + objects (metin, barkod, foto).
Sablon dosyasi ArgoBar/ArgoDesigner'da tasarlanir; program yalnizca veriyi degistirir,
boylece tasarim ve olcu Argox tarafinda kalir.
"""

from __future__ import annotations

import base64
import io
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.database import get_ayar, set_ayar
from core.logger import log_error, log_info
from core.yollar import BASE_DIR, VARLIK_DIR

SABLON_DIR = VARLIK_DIR / "sablonlar"
KULLANICI_SABLON_DIR = BASE_DIR / "sablonlar"
ETIKET_DIR = BASE_DIR / "etiketler"
LOGO_YOLU = VARLIK_DIR / "logo_kozmosize.png"
VARSAYILAN_SABLON = "etiket_30x40.axpx"
CODE128_A = 1

_LOGO_B64: str | None = None


@dataclass
class EtiketVeri:
    barkod: str
    ad: str = ""
    beden: str = ""
    fiyat: float = 0.0
    stok_kodu: str = ""
    adet: int = 1
    urun_id: int = 0


def _sablon_yolu(ad: str) -> Path | None:
    """Sablonu once kullanici klasorunde, sonra paketlenmis klasorde arar."""
    for kok in (KULLANICI_SABLON_DIR, SABLON_DIR):
        yol = kok / ad
        if yol.exists():
            return yol
    return None


def sablonlar() -> list[Path]:
    try:
        bulunan: dict[str, Path] = {}
        for kok in (SABLON_DIR, KULLANICI_SABLON_DIR):
            if not kok.exists():
                continue
            for yol in sorted(kok.glob("*.axpx")):
                bulunan[yol.name] = yol
        return [bulunan[ad] for ad in sorted(bulunan)]
    except Exception as e:
        log_error("Sablon listesi", e, __file__, "sablonlar")
        return []


def varsayilan_sablon() -> Path | None:
    secili = (get_ayar("etiket_sablon", "") or "").strip()
    if secili:
        yol = _sablon_yolu(secili)
        if yol is not None:
            return yol
    for ad in (VARSAYILAN_SABLON,):
        yol = _sablon_yolu(ad)
        if yol is not None:
            return yol
    hepsi = sablonlar()
    return hepsi[0] if hepsi else None


def sablon_ayarla(dosya: str) -> bool:
    try:
        set_ayar("etiket_sablon", dosya)
        return True
    except Exception as e:
        log_error("Sablon ayar", e, __file__, "sablon_ayarla")
        return False


def sablon_oku(yol: Path | str) -> dict | None:
    try:
        with open(yol, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_error(f"Sablon okunamadi: {yol}", e, __file__, "sablon_oku")
        return None


def sablon_olcusu(sablon: dict) -> tuple[float, float]:
    p = sablon.get("panelData", {}) if sablon else {}
    try:
        return float(p.get("labelWidth") or 30.0), float(p.get("labelHeight") or 40.0)
    except Exception:
        return 30.0, 40.0


def _fiyat_yazi(deger: float) -> str:
    try:
        return f"{float(deger):,.0f}".replace(",", ".") + " TL"
    except Exception:
        return ""


def logo_base64() -> str | None:
    """Etiketlerde urun fotografi yerine kullanilan sabit logo (onbellekli)."""
    global _LOGO_B64
    if _LOGO_B64 is not None:
        return _LOGO_B64 or None
    try:
        if not LOGO_YOLU.exists():
            _LOGO_B64 = ""
            return None
        from PIL import Image

        with Image.open(LOGO_YOLU) as im:
            im = im.convert("RGB")
            im.thumbnail((400, 400), Image.LANCZOS)
            im = im.convert("P", palette=Image.ADAPTIVE, colors=128)
            buf = io.BytesIO()
            im.save(buf, format="PNG", optimize=True)
            _LOGO_B64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return _LOGO_B64 or None
    except Exception as e:
        log_error("Etiket logosu", e, __file__, "logo_base64")
        _LOGO_B64 = ""
        return None


def _metin_mi(obj: dict) -> bool:
    return (obj.get("type") or "").lower() == "text"


def _fiyat_metni_mi(metin: str) -> bool:
    m = (metin or "").strip().upper()
    return "TL" in m or "₺" in m


def axpx_olustur(sablon: dict, veri: EtiketVeri) -> dict:
    """Sablonun kopyasinda metin/barkod/foto alanlarini doldurur."""
    d = json.loads(json.dumps(sablon))
    d["panelData"]["labelName"] = (veri.ad or "Etiket")[:40]

    w_mm, h_mm = sablon_olcusu(sablon)
    pc = d["panelData"].get("printerContent", {})
    if pc:
        pc["nWidth"] = int(round(w_mm / 25.4 * 203))
        pc["nHeight"] = int(round(h_mm / 25.4 * 203))

    ad_yazildi = False
    for obj in d.get("objects", []):
        tip = (obj.get("type") or "").lower()
        data = obj.get("data") or {}

        if tip == "barcode1d":
            data.setdefault("bindFixedData", {})["text"] = veri.barkod
            props = data.setdefault("barcodeProperties", {})
            props["code128CharacterSet"] = CODE128_A
            props["textPosition"] = 1
            data["drawReadableText"] = True
            continue

        if tip == "photo":
            b64 = logo_base64()
            if b64:
                data["image"] = b64
                data["timestamp"] = int(datetime.now().timestamp() * 1_000_000)
            continue

        if tip == "text":
            sabit = (data.get("bindFixedData") or {}).get("text") or ""
            if _fiyat_metni_mi(sabit):
                data["bindFixedData"]["text"] = _fiyat_yazi(veri.fiyat)
            elif not ad_yazildi:
                ad = veri.ad or ""
                if veri.beden:
                    ad = f"{ad} {veri.beden}".strip()
                data["bindFixedData"]["text"] = ad[:40]
                ad_yazildi = True
            continue
    return d


def axpx_yaz(icerik: dict, dosya: Path) -> tuple[bool, str]:
    try:
        dosya.parent.mkdir(parents=True, exist_ok=True)
        with open(dosya, "w", encoding="utf-8") as f:
            json.dump(icerik, f, ensure_ascii=False, separators=(",", ":"))
        return True, str(dosya)
    except Exception as e:
        log_error(f"AXPX yazma: {dosya}", e, __file__, "axpx_yaz")
        return False, str(e)


def etiketler_uret(
    etiketler: list[EtiketVeri],
    sablon_yolu: Path | str | None = None,
    klasor: Path | str | None = None,
) -> tuple[bool, str, list[str]]:
    """Her varyant icin ayri .axpx uretir. Donus: (ok, mesaj, dosyalar)."""
    try:
        yol = Path(sablon_yolu) if sablon_yolu else varsayilan_sablon()
        if not yol or not Path(yol).exists():
            return False, "Etiket sablonu bulunamadi (assets/sablonlar/*.axpx)", []
        sablon = sablon_oku(yol)
        if not sablon:
            return False, f"Sablon okunamadi: {yol}", []
        if not etiketler:
            return False, "Etiket verisi yok", []

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        hedef = Path(klasor) if klasor else (ETIKET_DIR / f"axpx_{ts}")
        hedef.mkdir(parents=True, exist_ok=True)

        dosyalar: list[str] = []
        for e in etiketler:
            icerik = axpx_olustur(sablon, e)
            guvenli = "".join(c for c in (e.barkod or "etiket") if c.isalnum() or c in "-_") or "etiket"
            ad = f"{guvenli}.axpx"
            if e.adet > 1:
                ad = f"{guvenli}_x{e.adet}.axpx"
            ok, sonuc = axpx_yaz(icerik, hedef / ad)
            if not ok:
                return False, sonuc, dosyalar
            dosyalar.append(sonuc)

        log_info(f"AXPX uretildi: {len(dosyalar)} dosya -> {hedef}")
        return True, str(hedef), dosyalar
    except Exception as e:
        log_error("AXPX uretim", e, __file__, "etiketler_uret")
        return False, str(e), []


def sablon_kopyala(kaynak: str, ad: str | None = None) -> tuple[bool, str, str]:
    """Kullanicinin ArgoDesigner'da tasarladigi sablonu projeye ekler."""
    try:
        p = Path(kaynak)
        if not p.exists():
            return False, "Dosya bulunamadi", ""
        sablon = sablon_oku(p)
        if not sablon or "panelData" not in sablon:
            return False, "Gecerli bir ArgoDesigner (.axpx) dosyasi degil", ""
        KULLANICI_SABLON_DIR.mkdir(parents=True, exist_ok=True)
        hedef_ad = ad or p.name
        if not hedef_ad.lower().endswith(".axpx"):
            hedef_ad += ".axpx"
        hedef = KULLANICI_SABLON_DIR / hedef_ad
        shutil.copy2(p, hedef)
        w, h = sablon_olcusu(sablon)
        log_info(f"Sablon eklendi: {hedef} ({w}x{h} mm)")
        return True, f"{hedef.name} eklendi ({w:.0f}x{h:.0f} mm)", str(hedef)
    except Exception as e:
        log_error("Sablon kopyala", e, __file__, "sablon_kopyala")
        return False, str(e), ""
