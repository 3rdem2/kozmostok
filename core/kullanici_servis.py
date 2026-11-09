# -*- coding: utf-8 -*-
import random
import string
import smtplib
from email.mime.text import MIMEText

from core.database import get_connection, get_ayar, set_ayar
from core.guvenlik import sifre_hashle, sifre_dogrula, eski_format_mi
from core.logger import log_error, log_info


def giris_yap(kullanici_adi: str, sifre: str) -> tuple[bool, dict | str]:
    try:
        kullanici_adi = (kullanici_adi or "").strip()
        sifre = (sifre or "").strip()
        if not kullanici_adi or not sifre:
            return False, "Kullanici adi ve sifre zorunlu"
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, kullanici_adi, rol, aktif, email, sifre_hash
               FROM kullanicilar WHERE kullanici_adi=?""",
            (kullanici_adi,),
        )
        r = cur.fetchone()
        if not r:
            conn.close()
            return False, "Kullanici veya sifre hatali"
        # Eski (tuzsuz) kayit dogru sifreyle girerse PBKDF2'ye yukselt
        if not sifre_dogrula(sifre, r["sifre_hash"]):
            conn.close()
            return False, "Kullanici veya sifre hatali"
        if eski_format_mi(r["sifre_hash"]):
            cur.execute(
                "UPDATE kullanicilar SET sifre_hash=? WHERE id=?",
                (sifre_hashle(sifre), r["id"]),
            )
            conn.commit()
        if not r["aktif"]:
            conn.close()
            return False, "Hesap pasif"
        d = dict(r)
        d.pop("sifre_hash", None)
        conn.close()
        return True, d
    except Exception as e:
        log_error("Giris", e, __file__, "giris_yap")
        return False, str(e)


def sifre_degistir(kullanici_adi: str, eski: str, yeni: str) -> tuple[bool, str]:
    try:
        kullanici_adi = (kullanici_adi or "").strip()
        eski = (eski or "").strip()
        yeni = (yeni or "").strip()
        if not kullanici_adi or not eski or not yeni:
            return False, "Tum alanlari doldurun"
        if len(yeni) < 4:
            return False, "Yeni sifre en az 4 karakter"
        ok, u = giris_yap(kullanici_adi, eski)
        if not ok:
            return False, "Eski sifre yanlis"
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE kullanicilar SET sifre_hash=? WHERE kullanici_adi=?",
            (sifre_hashle(yeni), kullanici_adi),
        )
        if isinstance(u, dict) and u.get("rol") == "yonetici":
            set_ayar("yonetim_pin", yeni)
        conn.commit()
        conn.close()
        return True, "Sifre guncellendi"
    except Exception as e:
        log_error("Sifre degistir", e, __file__, "sifre_degistir")
        return False, str(e)


def _gecici_sifre() -> str:
    return "Kz" + "".join(random.choices(string.digits, k=6))


def _mail_gonder(alici: str, konu: str, govde: str) -> tuple[bool, str]:
    host = get_ayar("smtp_host", "")
    port = int(get_ayar("smtp_port", "587") or "587")
    user = get_ayar("smtp_user", "")
    password = get_ayar("smtp_pass", "")
    gonderen = get_ayar("smtp_from", "") or user
    if not host or not user or not password or not alici:
        return False, "SMTP ayarlari veya alici e-posta eksik (Yonetim > Kullanicilar / SMTP)"
    try:
        msg = MIMEText(govde, "plain", "utf-8")
        msg["Subject"] = konu
        msg["From"] = gonderen
        msg["To"] = alici
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
        log_info(f"Mail gonderildi: {alici}")
        return True, "E-posta gonderildi"
    except Exception as e:
        log_error("Mail", e, __file__, "_mail_gonder")
        return False, f"Mail gonderilemedi: {e}"


def sifre_unuttum(kullanici_adi: str) -> tuple[bool, str]:
    """
    Eski sifre hashli oldugu icin 'son sifre' gonderilemez.
    Gecici yeni sifre uretilir, kaydedilir ve e-postaya gonderilir.
    """
    try:
        kullanici_adi = (kullanici_adi or "").strip()
        if not kullanici_adi:
            return False, "Kullanici adi zorunlu"
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, rol FROM kullanicilar WHERE kullanici_adi=? AND aktif=1",
            (kullanici_adi,),
        )
        r = cur.fetchone()
        if not r:
            conn.close()
            return False, "Kullanici bulunamadi"
        email = (r["email"] or "").strip()
        if not email or "@" not in email:
            conn.close()
            return False, "Bu kullanicinin e-postasi kayitli degil. Yonetici eklemeli."
        yeni = _gecici_sifre()
        cur.execute("UPDATE kullanicilar SET sifre_hash=? WHERE id=?", (sifre_hashle(yeni), r["id"]))
        if r["rol"] == "yonetici":
            set_ayar("yonetim_pin", yeni)
        conn.commit()
        conn.close()
        ok, msg = _mail_gonder(
            email,
            "KOZMOSIZE - Gecici sifre",
            f"Merhaba {kullanici_adi},\n\nGecici sifreniz: {yeni}\n"
            f"Giris yaptiktan sonra sifrenizi degistirin.\n\n"
            f"Not: Guvenlik nedeniyle eski sifre saklanmaz; yeni gecici sifre uretildi.\n",
        )
        if ok:
            return True, f"Gecici sifre e-postaya gonderildi: {email}"
        # Mail yoksa sifre yine degisti — yoneticiye bilgi
        return False, (
            f"{msg}\nGecici sifre olusturuldu ama mail gidemedi.\n"
            f"SMTP ayarlarini kontrol edin. (Gecici sifre logda yok; kurtarma kodu ile sifirlayin.)"
        )
    except Exception as e:
        log_error("Sifre unuttum", e, __file__, "sifre_unuttum")
        return False, str(e)


def sifre_sifirla_kurtarma(kullanici_adi: str, kurtarma: str, yeni: str) -> tuple[bool, str]:
    try:
        kullanici_adi = (kullanici_adi or "").strip()
        kurtarma = (kurtarma or "").strip()
        yeni = (yeni or "").strip()
        if not kullanici_adi or not kurtarma or not yeni:
            return False, "Tum alanlari doldurun"
        kod = get_ayar("kurtarma_kodu", "KOZMO-2026-RESET")
        if kurtarma != kod:
            return False, "Kurtarma kodu yanlis"
        if len(yeni) < 4:
            return False, "Yeni sifre en az 4 karakter"
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, rol FROM kullanicilar WHERE kullanici_adi=?", (kullanici_adi,))
        r = cur.fetchone()
        if not r:
            conn.close()
            return False, "Kullanici yok"
        cur.execute("UPDATE kullanicilar SET sifre_hash=? WHERE id=?", (sifre_hashle(yeni), r["id"]))
        if r["rol"] == "yonetici":
            set_ayar("yonetim_pin", yeni)
        conn.commit()
        conn.close()
        return True, "Sifre sifirlandi"
    except Exception as e:
        return False, str(e)


def kullanici_listele() -> list:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, kullanici_adi, rol, aktif, email FROM kullanicilar ORDER BY kullanici_adi"
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error("Liste", e, __file__, "kullanici_listele")
        return []


def kullanici_ekle(adi: str, sifre: str, rol: str = "kasiyer", email: str = "") -> tuple[bool, str]:
    try:
        adi = (adi or "").strip()
        sifre = sifre or ""
        email = (email or "").strip()
        if not adi or not sifre:
            return False, "Kullanici adi ve sifre zorunlu"
        if email and "@" not in email:
            return False, "Gecerli e-posta girin"
        if len(sifre) < 4:
            return False, "Sifre en az 4 karakter"
        if rol not in ("kasiyer", "yonetici"):
            rol = "kasiyer"
        sifre = (sifre or "").strip()
        if len(sifre) < 4:
            return False, "Sifre en az 4 karakter"
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO kullanicilar (kullanici_adi, sifre_hash, rol, email) VALUES (?,?,?,?)",
            (adi, sifre_hashle(sifre), rol, email),
        )
        conn.commit()
        conn.close()
        return True, "Kullanici eklendi"
    except Exception as e:
        return False, str(e)


def kullanici_sil(kullanici_id: int) -> tuple[bool, str]:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT kullanici_adi, rol FROM kullanicilar WHERE id=?", (kullanici_id,))
        r = cur.fetchone()
        if not r:
            conn.close()
            return False, "Kullanici yok"
        cur.execute("SELECT COUNT(*) AS n FROM kullanicilar WHERE rol='yonetici' AND aktif=1")
        n_yon = cur.fetchone()["n"]
        if r["rol"] == "yonetici" and n_yon <= 1:
            conn.close()
            return False, "Son yonetici silinemez"
        cur.execute("DELETE FROM kullanicilar WHERE id=?", (kullanici_id,))
        conn.commit()
        conn.close()
        log_info(f"Kullanici silindi: {r['kullanici_adi']}")
        return True, "Kullanici silindi"
    except Exception as e:
        return False, str(e)


def kullanici_rol_guncelle(kullanici_id: int, rol: str) -> tuple[bool, str]:
    """Kullanici yetkisini kasiyer/yonetici olarak degistirir."""
    try:
        rol = (rol or "").strip().lower()
        if rol not in ("kasiyer", "yonetici"):
            return False, "Gecersiz rol"
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT kullanici_adi, rol, aktif FROM kullanicilar WHERE id=?",
            (kullanici_id,),
        )
        r = cur.fetchone()
        if not r:
            conn.close()
            return False, "Kullanici yok"
        if (r["rol"] or "") == rol:
            conn.close()
            return True, "Rol zaten ayni"
        if r["rol"] == "yonetici" and r["aktif"]:
            cur.execute("SELECT COUNT(*) AS n FROM kullanicilar WHERE rol='yonetici' AND aktif=1")
            if cur.fetchone()["n"] <= 1:
                conn.close()
                return False, "Son yonetici kasiyere dusurulemez"
        cur.execute("UPDATE kullanicilar SET rol=? WHERE id=?", (rol, kullanici_id))
        conn.commit()
        conn.close()
        log_info(f"Yetki guncellendi: {r['kullanici_adi']} {r['rol']} -> {rol}")
        return True, f"{r['kullanici_adi']} yetkisi '{rol}' olarak guncellendi"
    except Exception as e:
        log_error("Rol guncelle", e, __file__, "kullanici_rol_guncelle")
        return False, str(e)


def kullanici_email_guncelle(kullanici_id: int, email: str) -> tuple[bool, str]:
    email = (email or "").strip()
    if not email or "@" not in email:
        return False, "Gecerli e-posta gerekli"
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE kullanicilar SET email=? WHERE id=?", (email, kullanici_id))
        conn.commit()
        conn.close()
        return True, "E-posta guncellendi"
    except Exception as e:
        return False, str(e)


def pin_dogrula(pin: str, kullanici_adi: str) -> bool:
    """Sadece giris yapmis kullanicinin KENDI sifresi gecerlidir."""
    pin = (pin or "").strip()
    kullanici_adi = (kullanici_adi or "").strip()
    if not pin or not kullanici_adi:
        return False
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT sifre_hash FROM kullanicilar WHERE kullanici_adi=? AND aktif=1",
            (kullanici_adi,),
        )
        r = cur.fetchone()
        conn.close()
        return bool(r) and sifre_dogrula(pin, r["sifre_hash"])
    except Exception:
        return False


def kullanici_kayit(adi: str, sifre: str, sifre2: str, email: str) -> tuple[bool, str]:
    """Giris ekranindan yeni kasiyer: sifreyi kullanici kendisi belirler."""
    if (sifre or "") != (sifre2 or ""):
        return False, "Sifreler eslesmiyor"
    return kullanici_ekle(adi, sifre, "kasiyer", email)


def smtp_ayarlari_kaydet(host, port, user, password, gonderen) -> bool:
    set_ayar("smtp_host", host or "")
    set_ayar("smtp_port", str(port or "587"))
    set_ayar("smtp_user", user or "")
    set_ayar("smtp_pass", password or "")
    set_ayar("smtp_from", gonderen or "")
    return True
