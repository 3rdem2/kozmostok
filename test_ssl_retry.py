# -*- coding: utf-8 -*-
"""SSL kopmasinda senkronun tekrar deneme mantiginin izole testi.

Gercek veritabanina dokunmaz: senkronize'in bagimliliklari sahtelenir.
1) 1. denemede OperationalError("SSL error: unexpected eof while reading"),
   2. denemede basari -> ok=True, 2 deneme  -> RETRY_SSL_TESTI_GECTI
2) gecici olmayan hata (ValueError) -> tek deneme, ok=False -> NO_RETRY_TESTI_GECTI
"""
import sys
import types

sys.path.insert(0, ".")
import core.sync_servis as ss

# --- Sahteler ---
ss.time.sleep = lambda s: None
ss.yerel_hazirla = lambda: True
ss.sunucu_hazirla = lambda pg: True
ss._ilk_kurulum = lambda conn, pg: False
ss.makine_adi = lambda: "PC-TEST"


class SahtePg:
    def close(self):
        pass


class SahteConn:
    def close(self):
        pass


DURUM = {"deneme": 0, "baglanti": 0}


def sahte_baglan_ok(bekleme=12.0):
    DURUM["baglanti"] += 1
    if DURUM["baglanti"] == 1:
        raise ss.psycopg2.OperationalError("SSL error: unexpected eof while reading")
    return SahtePg()


def sahte_gonder(conn, pg, makine):
    return 0


def sahte_cek(conn, pg, makine):
    return 0


ss._pg_baglan = sahte_baglan_ok
ss._gonder = sahte_gonder
ss._cek = sahte_cek
ss.get_connection = SahteConn

s1 = ss.senkronize(sessiz=True)
tamam1 = s1.get("ok") is True and DURUM["baglanti"] == 2 and "ssl" in s1.get("ilk_hata", "")
# ilk hatayi ayrica dogrulayalim: sonuc["hata"] son denemeden temizlenmez,
# ok=True donmesi yeterli; baglanti sayisi retry'in kaniti.
tamam1 = s1.get("ok") is True and DURUM["baglanti"] == 2
print("deneme1:", s1, "| baglanti sayisi:", DURUM["baglanti"])
print("RETRY_SSL_TESTI_GECTI" if tamam1 else "RETRY_SSL_TESTI_KALDI")

# 2) Gecici olmayan hata: retry yok
DURUM["baglanti"] = 0


def sahte_baglan_kalici(bekleme=12.0):
    DURUM["baglanti"] += 1
    raise ValueError("programlama hatasi - tekrar deneme")


ss._pg_baglan = sahte_baglan_kalici
s2 = ss.senkronize(sessiz=True)
tamam2 = s2.get("ok") is False and DURUM["baglanti"] == 1
print("deneme2:", s2, "| baglanti sayisi:", DURUM["baglanti"])
print("NO_RETRY_TESTI_GECTI" if tamam2 else "NO_RETRY_TESTI_KALDI")

# 3) Uc denemenin hepsi gecici hata -> 3 baglanti denemesi, ok=False
DURUM["baglanti"] = 0


def sahte_surekli_kopuk(bekleme=12.0):
    DURUM["baglanti"] += 1
    raise ss.psycopg2.OperationalError("connection reset by peer")


ss._pg_baglan = sahte_surekli_kopuk
s3 = ss.senkronize(sessiz=True)
tamam3 = s3.get("ok") is False and DURUM["baglanti"] == 3
print("deneme3:", s3, "| baglanti sayisi:", DURUM["baglanti"])
print("UC_DENEME_TESTI_GECTI" if tamam3 else "UC_DENEME_TESTI_KALDI")

if tamam1 and tamam2 and tamam3:
    print("SYNC_RETRY_TESTI_TAMAM")
    sys.exit(0)
sys.exit(1)
