# -*- coding: utf-8 -*-
"""Fiziki stok sayim modu"""

from core.database import get_connection
from core.logger import log_error, log_info
from core.kanal_servis import kanal_stok_yaz


def sayim_baslat(ad: str = "") -> tuple[bool, int | str]:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sayim_oturum (ad, durum) VALUES (?, 'acik')",
            (ad or "Sayim",),
        )
        oid = cur.lastrowid
        cur.execute(
            """
            SELECT id, stok_adedi FROM urunler
            WHERE aktif = 1
              AND NOT EXISTS (SELECT 1 FROM urunler c WHERE c.parent_id = urunler.id AND c.aktif = 1)
            """
        )
        for u in cur.fetchall():
            cur.execute(
                """INSERT INTO sayim_satir (oturum_id, urun_id, sistem_stok, sayilan_stok, fark)
                   VALUES (?, ?, ?, NULL, NULL)""",
                (oid, u["id"], int(u["stok_adedi"] or 0)),
            )
        conn.commit()
        conn.close()
        log_info(f"Sayim basladi #{oid}")
        return True, oid
    except Exception as e:
        log_error("Sayim baslat", e, __file__, "sayim_baslat")
        return False, str(e)


def sayim_liste(oturum_id: int) -> list:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT s.id, s.urun_id, s.sistem_stok, s.sayilan_stok, s.fark,
                   u.stok_kodu, u.barkod, u.ad
            FROM sayim_satir s
            JOIN urunler u ON u.id = s.urun_id
            WHERE s.oturum_id = ?
            ORDER BY u.ad
        """, (oturum_id,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log_error("Sayim liste", e, __file__, "sayim_liste")
        return []


def sayim_kaydet_satir(satir_id: int, sayilan: int) -> tuple[bool, str]:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT sistem_stok FROM sayim_satir WHERE id=?", (satir_id,))
        r = cur.fetchone()
        if not r:
            conn.close()
            return False, "Satir yok"
        fark = int(sayilan) - int(r["sistem_stok"])
        cur.execute(
            "UPDATE sayim_satir SET sayilan_stok=?, fark=? WHERE id=?",
            (int(sayilan), fark, satir_id),
        )
        conn.commit()
        conn.close()
        return True, "Kaydedildi"
    except Exception as e:
        return False, str(e)


def sayim_uygula(oturum_id: int, sadece_farkli: bool = True) -> tuple[bool, str]:
    """Sayilan degerleri magaza stoguna yazar."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT urun_id, sayilan_stok, fark FROM sayim_satir WHERE oturum_id=? AND sayilan_stok IS NOT NULL",
            (oturum_id,),
        )
        rows = cur.fetchall()
        conn.close()
        n = 0
        for r in rows:
            if sadece_farkli and int(r["fark"] or 0) == 0:
                continue
            ok, _, _ = kanal_stok_yaz(
                r["urun_id"], "magaza", int(r["sayilan_stok"]),
                f"Sayim oturum #{oturum_id}", fazla_onay=True,
            )
            if ok:
                n += 1
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE sayim_oturum SET durum='kapali', kapanis=datetime('now','localtime') WHERE id=?",
            (oturum_id,),
        )
        conn.commit()
        conn.close()
        return True, f"{n} urun magaza stogu guncellendi, sayim kapatildi"
    except Exception as e:
        log_error("Sayim uygula", e, __file__, "sayim_uygula")
        return False, str(e)


def acik_sayim() -> int | None:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM sayim_oturum WHERE durum='acik' ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        conn.close()
        return int(r["id"]) if r else None
    except Exception:
        return None
