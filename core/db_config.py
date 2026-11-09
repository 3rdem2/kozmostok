# -*- coding: utf-8 -*-
"""Veritabani yapilandirmasi — config.ini, sonra ortam degiskenleri.

Sifre config.ini icinde "enc:v1:..." biciminde sifreli tutulur (core/kasa.py).
Ortam degiskeni (PG_PASS) verilirse o kullanilir.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path

from core.kasa import coz, sifrele, sifreli_mi
from core.yollar import BASE_DIR

_KOK = Path(__file__).resolve().parent.parent
_INI_YOLU = _KOK / "config.ini"
KULLANICI_INI = BASE_DIR / "config.ini"


def _oku() -> configparser.ConfigParser:
    ini = configparser.ConfigParser(interpolation=None)
    for yol in (_INI_YOLU, KULLANICI_INI):
        try:
            if yol.exists():
                ini.read(yol, encoding="utf-8")
        except Exception:
            pass
    return ini


_ini = _oku()


def _g(key, env, default):
    v = os.getenv(env)
    if v:
        return v
    return _ini.get("database", key, fallback=default).strip()


def _sifre() -> str:
    ham = _g("password", "PG_PASS", "")
    if not ham:
        ham = _g("password_enc", "PG_PASS_ENC", "")
    return coz(ham) if sifreli_mi(ham) else ham


DB_MODE = _g("mode", "DB_MODE", "sqlite")  # sqlite | postgres

POSTGRES = {
    "host": _g("host", "PG_HOST", "127.0.0.1"),
    "port": int(_g("port", "PG_PORT", "5432")),
    "dbname": _g("dbname", "PG_DB", "kozmostok"),
    "user": _g("user", "PG_USER", "postgres"),
    "password": _sifre(),
}


def ayarlari_yeniden_yukle() -> None:
    """config.ini degistikten sonra bellekteki degerleri tazeler."""
    global _ini, DB_MODE, POSTGRES
    _ini = _oku()
    DB_MODE = _g("mode", "DB_MODE", "sqlite")
    POSTGRES = {
        "host": _g("host", "PG_HOST", "127.0.0.1"),
        "port": int(_g("port", "PG_PORT", "5432")),
        "dbname": _g("dbname", "PG_DB", "kozmostok"),
        "user": _g("user", "PG_USER", "postgres"),
        "password": _sifre(),
    }


def config_yaz(degerler: dict, bolum: str = "database") -> tuple[bool, str]:
    """Kullanici config.ini dosyasina yazar; sifre sifrelenir."""
    try:
        ini = configparser.ConfigParser(interpolation=None)
        if KULLANICI_INI.exists():
            ini.read(KULLANICI_INI, encoding="utf-8")
        if not ini.has_section(bolum):
            ini.add_section(bolum)
        for anahtar, deger in degerler.items():
            metin = "" if deger is None else str(deger)
            if anahtar in ("password", "password_enc") and metin:
                metin = sifrele(metin)
                anahtar = "password"
            ini.set(bolum, anahtar, metin)
        KULLANICI_INI.parent.mkdir(parents=True, exist_ok=True)
        with open(KULLANICI_INI, "w", encoding="utf-8") as f:
            ini.write(f)
        ayarlari_yeniden_yukle()
        return True, str(KULLANICI_INI)
    except Exception as e:
        return False, str(e)


def config_oku() -> dict:
    """Arayuz icin mevcut baglanti ayarlari (sifre cozulmus)."""
    return {
        "mode": DB_MODE,
        "host": POSTGRES.get("host", ""),
        "port": POSTGRES.get("port", 5432),
        "dbname": POSTGRES.get("dbname", ""),
        "user": POSTGRES.get("user", ""),
        "password": POSTGRES.get("password", ""),
    }
