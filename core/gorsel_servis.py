# -*- coding: utf-8 -*-
"""
Urun gorselleri eslestirme (siki eslesme).
Kaynak:
  - KozmoStok/assets/urun_gorselleri
  - artifacts/urun_gorselleri
Eslesme: stok_kodu / barkod == dosya adi veya alt klasor adi
MDL/BCK/FRNT yerine ana gorsel tercih edilir.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.database import get_connection
from core.logger import log_error, log_info
from core.yollar import BASE_DIR, KAYNAK_DIR, VARLIK_DIR

GORSEL_DIR = VARLIK_DIR / "urun_gorselleri"
if not GORSEL_DIR.exists():
    GORSEL_DIR = BASE_DIR / "assets" / "urun_gorselleri"
EXTRA_GORSEL_DIR = KAYNAK_DIR.parent / "urun_gorselleri"
UZANTILAR = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

_YAN_SONEK = re.compile(
    r"[-_](MDL|BCK|FRNT|BACK|FRONT|SIDE|DETAY|DETAIL)(\d)?$",
    re.IGNORECASE,
)


def gorsel_klasoru() -> Path:
    try:
        GORSEL_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return GORSEL_DIR


def _normalize(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\\", "/").split("/")[-1]
    s = s.replace("_", "-")
    s = re.sub(r"\s+", "", s)
    # turkce karakter sade
    repl = {
        "İ": "I", "I": "I", "ı": "I",
        "Ş": "S", "ş": "S",
        "Ğ": "G", "ğ": "G",
        "Ü": "U", "ü": "U",
        "Ö": "O", "ö": "O",
        "Ç": "C", "ç": "C",
    }
    for a, b in repl.items():
        s = s.replace(a, b)
    return s.upper()


def _base_stem(stem: str) -> str:
    return _YAN_SONEK.sub("", stem.strip())


def _oncelik(path: Path) -> int:
    stem = path.stem
    u = stem.upper()
    # Ana gorsel tercihi
    if stem.isdigit():
        return int(stem)  # 1.png once
    if "FRONT" in u or "FRNT" in u:
        return 1
    if _YAN_SONEK.search(stem) or any(x in u for x in ("MDL", "BCK", "BACK", "SIDE")):
        return 5
    return 0


def _tum_gorseller() -> list[Path]:
    adaylar: list[Path] = []
    for root in (GORSEL_DIR, EXTRA_GORSEL_DIR):
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if f.is_file() and f.suffix.lower() in UZANTILAR:
                adaylar.append(f)
    return adaylar


def _indeks_olustur(dosyalar: list[Path]) -> dict[str, list[Path]]:
    idx: dict[str, list[Path]] = {}

    def ekle(key: str, path: Path):
        k = _normalize(key)
        if not k or len(k) < 3:
            return
        # sadece sayi olan anahtarlar (1, 2, 12) urun kodu degil
        if k.isdigit():
            return
        idx.setdefault(k, []).append(path)

    for f in dosyalar:
        stem = f.stem
        base = _base_stem(stem)
        ekle(stem, f)
        ekle(base, f)
        # Alt klasor adi urun kodu ise (ornek: KZM-XT-2811/)
        parent = f.parent
        if parent.name and parent not in (GORSEL_DIR, EXTRA_GORSEL_DIR):
            # ust kok degilse
            if parent.parent in (GORSEL_DIR, EXTRA_GORSEL_DIR) or True:
                ekle(parent.name, f)
                ekle(_base_stem(parent.name), f)

    for k in idx:
        idx[k] = sorted(idx[k], key=_oncelik)
    return idx


def _kod_varyasyonlari(kod: str) -> list[str]:
    if not kod:
        return []
    v = [
        kod,
        kod.replace("_", "-"),
        kod.replace(" ", ""),
        kod.replace(" ", "-"),
        _base_stem(kod),
    ]
    # ASSASIN MAX -> ASSASIN-MAX
    v.append(re.sub(r"\s+", "-", kod.strip()))
    # Beden soneklerini at: -S -M -L -XL -S/M -L/XL vb.
    beden = re.compile(
        r"[-_]((XXL|XL|XS|S|M|L)([/\-](XXL|XL|XS|S|M|L))?)$",
        re.IGNORECASE,
    )
    ekstra = []
    for x in list(v):
        y = beden.sub("", x.strip())
        if y and y != x:
            ekstra.append(y)
            ekstra.append(y.replace("_", "-"))
    v.extend(ekstra)
    out = []
    seen = set()
    for x in v:
        n = _normalize(x)
        if n and n not in seen and not n.isdigit() and len(n) >= 3:
            seen.add(n)
            out.append(n)
    return out


def gorsel_yolu_bul(stok_kodu: str = "", barkod: str = "", indeks: dict | None = None) -> str | None:
    if indeks is None:
        indeks = _indeks_olustur(_tum_gorseller())

    for c in list(_kod_varyasyonlari(stok_kodu)) + list(_kod_varyasyonlari(barkod)):
        if c in indeks and indeks[c]:
            return str(indeks[c][0])
    return None


def gorselleri_esle() -> dict:
    sonuc = {
        "eslesen": 0,
        "toplam_dosya": 0,
        "toplam_urun": 0,
        "eslesmeyen": 0,
        "mesaj": "",
        "ornekler": [],
    }
    try:
        dosyalar = _tum_gorseller()
        sonuc["toplam_dosya"] = len(dosyalar)
        if not dosyalar:
            sonuc["mesaj"] = (
                f"Gorsel bulunamadi.\n{GORSEL_DIR}\n{EXTRA_GORSEL_DIR}"
            )
            return sonuc

        indeks = _indeks_olustur(dosyalar)
        conn = get_connection()
        cur = conn.cursor()
        # once eski yanlis eslesmeleri temizle
        cur.execute("UPDATE urunler SET gorsel_yolu = NULL")
        cur.execute("SELECT id, stok_kodu, barkod, ad FROM urunler WHERE aktif = 1")
        urunler = cur.fetchall()
        sonuc["toplam_urun"] = len(urunler)

        for u in urunler:
            yol = gorsel_yolu_bul(u["stok_kodu"] or "", u["barkod"] or "", indeks=indeks)
            if yol:
                cur.execute(
                    "UPDATE urunler SET gorsel_yolu = ?, guncelleme = datetime('now','localtime') WHERE id = ?",
                    (yol, u["id"]),
                )
                sonuc["eslesen"] += 1
                if len(sonuc["ornekler"]) < 8:
                    sonuc["ornekler"].append(
                        f"{u['stok_kodu']} -> {Path(yol).name}"
                    )
            else:
                sonuc["eslesmeyen"] += 1

        conn.commit()
        conn.close()
        sonuc["mesaj"] = (
            f"{sonuc['eslesen']} / {sonuc['toplam_urun']} urune gorsel eslesti "
            f"(dosya: {sonuc['toplam_dosya']}, eslesmeyen: {sonuc['eslesmeyen']})"
        )
        log_info(sonuc["mesaj"])
        return sonuc
    except Exception as e:
        log_error("Gorsel esleme hatasi", e, __file__, "gorselleri_esle")
        sonuc["mesaj"] = str(e)
        return sonuc
