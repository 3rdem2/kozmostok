# -*- coding: utf-8 -*-
"""Hassas degerleri (sunucu sifresi, API anahtari) sifreleyerek saklar.

Yontem: PBKDF2-HMAC-SHA256 ile anahtar turetimi + HMAC-SHA256 akis sifresi
(CTR) + encrypt-then-MAC dogrulama. Yalnizca standart kutuphane kullanilir.

Not: Anahtar malzemesi uygulamanin icinde gomulu oldugu icin bu, dosyayi
dogrudan okuyan kisiye karsi koruma saglar (config.ini'de duz sifre gorunmez).
Isletim sistemi hesabina bagli bir kasaya (DPAPI/Keychain) bagli olmadigi icin
paket birden fazla bilgisayarda ayni sekilde calisir.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

_ON_EK = "enc:v1:"
_TUR = 120_000
# Uygulama icinde gomulu anahtar malzemesi (iki parca halinde)
_P1 = b"KozmoStok/2026/kasa/"
_P2 = b"foreverunderground#stok"
_TUZ = b"|kasa-tuzu|"


def _anahtar(tuz: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", _P1 + _P2, tuz + _TUZ, _TUR, 32)


def _akis(anahtar: bytes, nonce: bytes, uzunluk: int) -> bytes:
    parcalar = []
    sayac = 0
    uretilen = 0
    while uretilen < uzunluk:
        blok = hmac.new(
            anahtar, nonce + sayac.to_bytes(8, "big"), hashlib.sha256
        ).digest()
        parcalar.append(blok)
        uretilen += len(blok)
        sayac += 1
    return b"".join(parcalar)[:uzunluk]


def _xor(veri: bytes, akis: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(veri, akis))


def sifreli_mi(deger: str) -> bool:
    return isinstance(deger, str) and deger.startswith(_ON_EK)


def sifrele(metin: str) -> str:
    """Duz metni sifreli metne cevirir. Bos deger oldugu gibi doner."""
    if not metin:
        return ""
    if sifreli_mi(metin):
        return metin
    veri = metin.encode("utf-8")
    tuz = os.urandom(16)
    nonce = os.urandom(16)
    anahtar = _anahtar(tuz)
    sifreli = _xor(veri, _akis(anahtar, nonce, len(veri)))
    mac = hmac.new(anahtar, tuz + nonce + sifreli, hashlib.sha256).digest()
    return _ON_EK + ":".join(
        base64.b64encode(p).decode("ascii") for p in (tuz, nonce, sifreli, mac)
    )


def coz(deger: str) -> str:
    """Sifreli metni cozer. Bozuk/duz deger icin bos metin doner."""
    if not deger:
        return ""
    if not sifreli_mi(deger):
        return deger
    try:
        govde = deger[len(_ON_EK):]
        tuz_b, nonce_b, sifreli_b, mac_b = govde.split(":")
        tuz = base64.b64decode(tuz_b)
        nonce = base64.b64decode(nonce_b)
        sifreli = base64.b64decode(sifreli_b)
        mac = base64.b64decode(mac_b)
        anahtar = _anahtar(tuz)
        beklenen = hmac.new(anahtar, tuz + nonce + sifreli, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, beklenen):
            return ""
        return _xor(sifreli, _akis(anahtar, nonce, len(sifreli))).decode("utf-8")
    except Exception:
        return ""
