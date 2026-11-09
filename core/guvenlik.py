# -*- coding: utf-8 -*-
"""
Sifre guvenligi: PBKDF2-HMAC-SHA256 + kullaniciye ozel tuz (salt).
Eski kayitsiz sha256 hashleri dogrulamada kabul edilir, giriste otomatik yukseltilir.
"""

import hashlib
import hmac
import secrets

PBKDF2_ITERASYON = 120_000
_ETIKET = "pbkdf2_sha256"


def _temizle(s: str) -> str:
    """Sifre girdisini normalizasyon: bastaki/sondaki bosluklari at."""
    return (s or "").strip()


def sifre_hashle(sifre: str) -> str:
    """pbkdf2_sha256$iterasyon$salt_hex$hash_hex formatinda kayit uretir."""
    sifre = _temizle(sifre)
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac(
        "sha256", sifre.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERASYON
    )
    return f"{_ETIKET}${PBKDF2_ITERASYON}${salt}${h.hex()}"


def sifre_dogrula(sifre: str, kayitli_hash: str) -> bool:
    """Kayitli hash ile girilen sifreyi karsilastirir. Eski sha256 kaydini da kabul eder."""
    sifre = _temizle(sifre)
    kayitli_hash = kayitli_hash or ""
    try:
        if kayitli_hash.startswith(f"{_ETIKET}$"):
            _, iter_str, salt_hex, hash_hex = kayitli_hash.split("$", 3)
            hesap = hashlib.pbkdf2_hmac(
                "sha256",
                sifre.encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(iter_str),
            ).hex()
            return hmac.compare_digest(hesap, hash_hex)
        # Eski format: tuzsuz sha256 (64 hex)
        eski = hashlib.sha256(sifre.encode("utf-8")).hexdigest()
        return hmac.compare_digest(eski, kayitli_hash)
    except Exception:
        return False


def eski_format_mi(kayitli_hash: str) -> bool:
    """True ise kayit eski (tuzsuz) formatta; giris sonrasi yenisine cevrilmeli."""
    return bool(kayitli_hash) and not kayitli_hash.startswith(f"{_ETIKET}$")
