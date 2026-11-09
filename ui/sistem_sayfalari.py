# -*- coding: utf-8 -*-
"""Yedek, sayim, kullanici yonetimi UI"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QLineEdit, QHeaderView,
    QMessageBox, QSpinBox, QComboBox, QFormLayout, QDialog,
    QDialogButtonBox, QInputDialog, QAbstractItemView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from core.yedek_servis import yedek_al, son_yedekler
from core.sayim_servis import (
    sayim_baslat, sayim_liste, sayim_kaydet_satir, sayim_uygula, acik_sayim,
)
from core.rapor_servis import sayim_excel
from core.kullanici_servis import (
    kullanici_listele, kullanici_ekle, sifre_degistir, sifre_sifirla_kurtarma,
)
from core.database import get_ayar, set_ayar
from core.db_config import config_oku, config_yaz
from core.guncelleme_servis import (
    kontrol as guncelleme_kontrol,
    indir as guncelleme_indir,
    hazirla as guncelleme_hazirla,
    uygula as guncelleme_uygula,
    manifest_adresi,
    surum,
)
from core.logger import log_error


class YedekSayfasi(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Veritabani yedegi (db kopyasi)"))
        btn = QPushButton("Simdi yedek al")
        btn.setStyleSheet("background:#2980b9;color:white;padding:8px;font-weight:bold;")
        btn.clicked.connect(self.yedekle)
        lay.addWidget(btn)
        self.liste = QLabel("")
        self.liste.setWordWrap(True)
        lay.addWidget(self.liste)
        lay.addStretch()
        self.yenile()

    def yenile(self):
        ys = son_yedekler(8)
        self.liste.setText("Son yedekler:\n" + ("\n".join(ys) if ys else "(henuz yok)"))

    def yedekle(self):
        ok, yol = yedek_al("manuel")
        if ok:
            QMessageBox.information(self, "Yedek", f"Alindi:\n{yol}")
            self.yenile()
        else:
            QMessageBox.warning(self, "Hata", yol)


class SayimSayfasi(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.oturum_id = acik_sayim()
        lay = QVBoxLayout(self)
        ust = QHBoxLayout()
        self.lbl = QLabel("Sayim modu")
        self.lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        ust.addWidget(self.lbl)
        ust.addStretch()
        b1 = QPushButton("Yeni sayim baslat")
        b1.clicked.connect(self.baslat)
        ust.addWidget(b1)
        b2 = QPushButton("Yenile")
        b2.clicked.connect(self.yenile)
        ust.addWidget(b2)
        b_excel = QPushButton("Excel çıktı")
        b_excel.clicked.connect(self.excel_aktar)
        ust.addWidget(b_excel)
        b3 = QPushButton("Sayimi uygula (magaza stok)")
        b3.setStyleSheet("background:#c0392b;color:white;padding:6px;")
        b3.clicked.connect(self.uygula)
        ust.addWidget(b3)
        lay.addLayout(ust)

        self.tablo = QTableWidget()
        self.tablo.setColumnCount(6)
        self.tablo.setHorizontalHeaderLabels(["Kod", "Barkod", "Urun", "Sistem", "Sayilan", "Fark"])
        self.tablo.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tablo.cellChanged.connect(self._hucre)
        lay.addWidget(self.tablo)
        self._rows = []
        self._lock = False
        self.yenile()

    def baslat(self):
        if self.oturum_id:
            if QMessageBox.question(
                self, "Acik sayim", "Acik sayim var. Yine de yeni baslatilsin mi?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
        ok, oid = sayim_baslat("Magaza sayim")
        if ok:
            self.oturum_id = int(oid)
            QMessageBox.information(self, "Sayim", f"Sayim #{self.oturum_id} acildi. Sayilan sutununu doldurun.")
            self.yenile()
        else:
            QMessageBox.warning(self, "Hata", str(oid))

    def yenile(self):
        self.oturum_id = acik_sayim() or self.oturum_id
        self.lbl.setText(f"Sayim modu  #{self.oturum_id or '-'}")
        if not self.oturum_id:
            self.tablo.setRowCount(0)
            return
        self._lock = True
        self._rows = sayim_liste(self.oturum_id)
        self.tablo.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            self.tablo.setItem(i, 0, QTableWidgetItem(r.get("stok_kodu") or ""))
            self.tablo.setItem(i, 1, QTableWidgetItem(r.get("barkod") or ""))
            self.tablo.setItem(i, 2, QTableWidgetItem(r.get("ad") or ""))
            _r = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            s_it = QTableWidgetItem(str(r.get("sistem_stok", 0)))
            s_it.setTextAlignment(_r)
            self.tablo.setItem(i, 3, s_it)
            say = r.get("sayilan_stok")
            y_it = QTableWidgetItem("" if say is None else str(say))
            y_it.setTextAlignment(_r)
            self.tablo.setItem(i, 4, y_it)
            f_it = QTableWidgetItem("" if r.get("fark") is None else str(r.get("fark")))
            f_it.setTextAlignment(_r)
            self.tablo.setItem(i, 5, f_it)
            for c in range(3):
                it = self.tablo.item(i, c)
                if it:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._lock = False

    def _hucre(self, row, col):
        if self._lock or col != 4 or row >= len(self._rows):
            return
        try:
            txt = self.tablo.item(row, 4).text().strip()
            if txt == "":
                return
            sayilan = int(float(txt))
            sid = self._rows[row]["id"]
            ok, msg = sayim_kaydet_satir(sid, sayilan)
            if ok:
                self._lock = True
                fark = sayilan - int(self._rows[row]["sistem_stok"])
                self.tablo.setItem(row, 5, QTableWidgetItem(str(fark)))
                self._rows[row]["sayilan_stok"] = sayilan
                self._rows[row]["fark"] = fark
                self._lock = False
            else:
                QMessageBox.warning(self, "Hata", msg)
        except Exception as e:
            QMessageBox.warning(self, "Hata", str(e))

    def uygula(self):
        if not self.oturum_id:
            QMessageBox.information(self, "Sayim", "Once sayim baslatin.")
            return
        if QMessageBox.question(
            self, "Onay",
            "Sayilan degerler MAGAZA stoguna yazilacak ve sayim kapanacak. Devam?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        ok, msg = sayim_uygula(self.oturum_id)
        if ok:
            QMessageBox.information(self, "Tamam", msg)
            self.oturum_id = None
            self.yenile()
        else:
            QMessageBox.warning(self, "Hata", msg)

    def excel_aktar(self):
        if not self.oturum_id:
            QMessageBox.information(self, "Sayim", "Once sayim baslatin.")
            return
        ok, yol = sayim_excel(self.oturum_id)
        if ok:
            QMessageBox.information(self, "Rapor", f"Sayim Excel olusturuldu:\n{yol}")
        else:
            QMessageBox.warning(self, "Hata", yol)



class KullaniciSayfasi(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#0a0a0c; color:#e8e0e0;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        baslik = QLabel("Kullanicilar")
        baslik.setStyleSheet("color:#c9a66b; font-size:13px; font-weight:600;")
        lay.addWidget(baslik)

        # Tablo ustte — genis alan
        self.tablo = QTableWidget()
        self.tablo.setColumnCount(4)
        self.tablo.setHorizontalHeaderLabels(["ID", "Kullanici", "Rol", "E-posta"])
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tablo.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.setMinimumHeight(180)
        self.tablo.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tablo.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tablo.setStyleSheet(
            "QTableWidget { background:#0e0e12; color:#e8e0e0; border:1px solid #2a1a1a; "
            "gridline-color:#1f1a1a; font-size:12px; alternate-background-color:#121018; }"
            "QHeaderView::section { background:#1a1212; color:#c9a66b; padding:5px; "
            "border:none; border-bottom:1px solid #8b0000; font-size:11px; }"
            "QTableWidget::item:selected { background:#8b0000; }"
        )
        self.tablo.itemSelectionChanged.connect(self._secim_degisti)
        lay.addWidget(self.tablo, 3)

        # Alt formlar %10 kucuk / kompakt
        kompakt = (
            "QLineEdit, QComboBox { background:#1a1a22; color:#e8e0e0; border:1px solid #2a1a1a; "
            "border-radius:3px; padding:1px 5px; min-height:22px; max-height:24px; font-size:11px; }"
            "QComboBox::drop-down { width:16px; border-left:1px solid #2a1a1a; }"
            "QLabel { font-size:11px; color:#8a7a7a; }"
            "QPushButton { background:#2a1a1a; color:#f0eaea; font-size:11px; font-weight:600; "
            "border-radius:3px; padding:2px 8px; min-height:22px; max-height:24px; "
            "border:1px solid #2a1a1a; }"
        )
        alt = QWidget()
        alt.setStyleSheet(kompakt)
        alt_l = QVBoxLayout(alt)
        alt_l.setContentsMargins(0, 4, 0, 0)
        alt_l.setSpacing(4)

        br = QHBoxLayout()
        br.setSpacing(6)
        bdel = QPushButton("Secili sil")
        bdel.setStyleSheet(
            "QPushButton { background:#8b0000; color:white; font-size:11px; "
            "min-height:22px; max-height:24px; border-radius:3px; padding:2px 8px; }"
        )
        bdel.clicked.connect(self.sil)
        br.addWidget(bdel)
        br.addStretch()
        br.addWidget(QLabel("Yetki:"))
        self.rol_sec = QComboBox()
        self.rol_sec.addItems(["kasiyer", "yonetici"])
        br.addWidget(self.rol_sec)
        b_yetki = QPushButton("Yetkiyi kaydet")
        b_yetki.clicked.connect(self.yetki_kaydet)
        br.addWidget(b_yetki)
        alt_l.addLayout(br)

        lbl2 = QLabel("Sifre degistir")
        lbl2.setStyleSheet("color:#c9a66b; font-size:11px; font-weight:600;")
        alt_l.addWidget(lbl2)
        f2 = QFormLayout()
        f2.setHorizontalSpacing(8)
        f2.setVerticalSpacing(3)
        f2.setContentsMargins(0, 0, 0, 0)
        self.k_adi = QLineEdit()
        self.eski = QLineEdit(); self.eski.setEchoMode(QLineEdit.EchoMode.Password)
        self.yeni = QLineEdit(); self.yeni.setEchoMode(QLineEdit.EchoMode.Password)
        f2.addRow("Kullanici *", self.k_adi)
        f2.addRow("Eski sifre *", self.eski)
        f2.addRow("Yeni sifre *", self.yeni)
        alt_l.addLayout(f2)
        b2 = QPushButton("Sifreyi degistir")
        b2.clicked.connect(self.degistir)
        alt_l.addWidget(b2)

        lbl3 = QLabel("SMTP (sifremi unuttum)")
        lbl3.setStyleSheet("color:#c9a66b; font-size:11px; font-weight:600;")
        alt_l.addWidget(lbl3)
        f3 = QFormLayout()
        f3.setHorizontalSpacing(8)
        f3.setVerticalSpacing(3)
        f3.setContentsMargins(0, 0, 0, 0)
        from core.database import get_ayar
        self.smtp_host = QLineEdit(get_ayar("smtp_host", ""))
        self.smtp_port = QLineEdit(get_ayar("smtp_port", "587"))
        self.smtp_user = QLineEdit(get_ayar("smtp_user", ""))
        self.smtp_pass = QLineEdit(get_ayar("smtp_pass", ""))
        self.smtp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.smtp_from = QLineEdit(get_ayar("smtp_from", ""))
        f3.addRow("SMTP host", self.smtp_host)
        f3.addRow("Port", self.smtp_port)
        f3.addRow("Kullanici", self.smtp_user)
        f3.addRow("Sifre", self.smtp_pass)
        f3.addRow("Gonderen", self.smtp_from)
        alt_l.addLayout(f3)
        bs = QPushButton("SMTP kaydet")
        bs.clicked.connect(self.smtp_kaydet)
        alt_l.addWidget(bs)

        lay.addWidget(alt, 2)

        yeni_w = QWidget()
        yeni_w.setStyleSheet(kompakt)
        yeni_l = QHBoxLayout(yeni_w)
        yeni_l.setContentsMargins(0, 2, 0, 0)
        yeni_l.setSpacing(6)
        yeni_l.addWidget(QLabel("Yeni kullanici:"))
        self.y_adi = QLineEdit()
        self.y_adi.setPlaceholderText("kullanici adi")
        self.y_sifre = QLineEdit()
        self.y_sifre.setEchoMode(QLineEdit.EchoMode.Password)
        self.y_sifre.setPlaceholderText("sifre")
        self.y_email = QLineEdit()
        self.y_email.setPlaceholderText("e-posta (opsiyonel)")
        self.y_rol = QComboBox()
        self.y_rol.addItems(["kasiyer", "yonetici"])
        b_ekle = QPushButton("Kullanici ekle")
        b_ekle.clicked.connect(self.ekle)
        for w in (self.y_adi, self.y_sifre, self.y_email):
            yeni_l.addWidget(w, 1)
        yeni_l.addWidget(self.y_rol)
        yeni_l.addWidget(b_ekle)
        lay.addWidget(yeni_w)
        self.yenile()

    def yenile(self):
        from core.kullanici_servis import kullanici_listele
        rows = kullanici_listele()
        self.tablo.setRowCount(len(rows))
        for i, r in enumerate(rows):
            id_it = QTableWidgetItem(str(r.get("id")))
            id_it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tablo.setItem(i, 0, id_it)
            self.tablo.setItem(i, 1, QTableWidgetItem(r.get("kullanici_adi") or ""))
            self.tablo.setItem(i, 2, QTableWidgetItem(r.get("rol") or ""))
            self.tablo.setItem(i, 3, QTableWidgetItem(r.get("email") or ""))

    def _secim_degisti(self):
        row = self.tablo.currentRow()
        if row < 0 or not self.tablo.item(row, 2):
            return
        rol = (self.tablo.item(row, 2).text() or "").strip().lower()
        idx = self.rol_sec.findText(rol)
        if idx >= 0:
            self.rol_sec.setCurrentIndex(idx)

    def ekle(self):
        from core.kullanici_servis import kullanici_ekle
        adi = self.y_adi.text().strip()
        sifre = self.y_sifre.text()
        email = self.y_email.text().strip()
        rol = self.y_rol.currentText()
        if not adi or not sifre:
            QMessageBox.warning(self, "Eksik", "Kullanici adi ve sifre zorunlu.")
            return
        ok, msg = kullanici_ekle(adi, sifre, rol, email)
        if ok:
            QMessageBox.information(
                self, "Kullanici", f"'{adi}' eklendi. Yetki: {rol}"
            )
            self.y_adi.clear()
            self.y_sifre.clear()
            self.y_email.clear()
            self.yenile()
        else:
            QMessageBox.warning(self, "Hata", msg)

    def yetki_kaydet(self):
        from core.kullanici_servis import kullanici_rol_guncelle
        row = self.tablo.currentRow()
        if row < 0:
            QMessageBox.information(self, "Secim", "Yetkisi degisecek kullaniciyi secin.")
            return
        uid = int(self.tablo.item(row, 0).text())
        adi = self.tablo.item(row, 1).text()
        rol = self.rol_sec.currentText()
        if QMessageBox.question(
            self, "Onay", f"'{adi}' kullanicisinin yetkisi '{rol}' olsun mu?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        ok, msg = kullanici_rol_guncelle(uid, rol)
        QMessageBox.information(self, "Sonuc", msg)
        if ok:
            self.yenile()

    def sil(self):
        from core.kullanici_servis import kullanici_sil
        row = self.tablo.currentRow()
        if row < 0:
            QMessageBox.information(self, "Secim", "Silinecek kullaniciyi secin.")
            return
        uid = int(self.tablo.item(row, 0).text())
        if QMessageBox.question(
            self, "Onay", "Kullanici silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        ok, msg = kullanici_sil(uid)
        QMessageBox.information(self, "Sonuc", msg)
        if ok:
            self.yenile()

    def degistir(self):
        from core.kullanici_servis import sifre_degistir
        if not self.k_adi.text().strip() or not self.eski.text() or not self.yeni.text():
            QMessageBox.warning(self, "Eksik", "Tum sifre alanlarini doldurun.")
            return
        ok, msg = sifre_degistir(self.k_adi.text(), self.eski.text(), self.yeni.text())
        QMessageBox.information(self, "Sonuc", msg)

    def smtp_kaydet(self):
        from core.kullanici_servis import smtp_ayarlari_kaydet
        smtp_ayarlari_kaydet(
            self.smtp_host.text(), self.smtp_port.text(),
            self.smtp_user.text(), self.smtp_pass.text(), self.smtp_from.text(),
        )
        QMessageBox.information(self, "SMTP", "Kaydedildi.")


class SistemSayfasi(QWidget):
    """Sunucu baglantisi, guncelleme adresi ve surum bilgisi."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        baslik = QLabel("Sistem ayarlari")
        baslik.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        lay.addWidget(baslik)

        self.lbl_surum = QLabel("")
        self.lbl_surum.setStyleSheet("color:#9aa4b2;")
        lay.addWidget(self.lbl_surum)

        lay.addWidget(QLabel("Sunucu baglantisi (Supabase / PostgreSQL)"))
        form = QFormLayout()
        self.ed_host = QLineEdit()
        self.ed_port = QSpinBox()
        self.ed_port.setRange(1, 65535)
        self.ed_db = QLineEdit()
        self.ed_user = QLineEdit()
        self.ed_sifre = QLineEdit()
        self.ed_sifre.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Sunucu (host)", self.ed_host)
        form.addRow("Port", self.ed_port)
        form.addRow("Veritabani", self.ed_db)
        form.addRow("Kullanici", self.ed_user)
        form.addRow("Sifre", self.ed_sifre)
        lay.addLayout(form)

        satir = QHBoxLayout()
        b_kaydet = QPushButton("Sunucu ayarlarini kaydet")
        b_kaydet.clicked.connect(self._sunucu_kaydet)
        b_test = QPushButton("Baglantiyi test et")
        b_test.clicked.connect(self._baglanti_test)
        satir.addWidget(b_kaydet)
        satir.addWidget(b_test)
        satir.addStretch()
        lay.addLayout(satir)

        lay.addWidget(QLabel("Guncelleme"))
        g_form = QFormLayout()
        self.ed_url = QLineEdit()
        self.ed_url.setPlaceholderText("https://.../surum.json")
        g_form.addRow("Manifest adresi", self.ed_url)
        lay.addLayout(g_form)

        g_satir = QHBoxLayout()
        b_url = QPushButton("Adresi kaydet")
        b_url.clicked.connect(self._url_kaydet)
        b_kontrol = QPushButton("Guncellemeyi kontrol et")
        b_kontrol.clicked.connect(self._kontrol)
        self.b_guncelle = QPushButton("Guncelle")
        self.b_guncelle.setStyleSheet("background:#c9a66b;color:#111;font-weight:bold;padding:6px;")
        self.b_guncelle.clicked.connect(self._guncelle)
        self.b_guncelle.setEnabled(False)
        g_satir.addWidget(b_url)
        g_satir.addWidget(b_kontrol)
        g_satir.addWidget(self.b_guncelle)
        g_satir.addStretch()
        lay.addLayout(g_satir)

        self.lbl_durum = QLabel("")
        self.lbl_durum.setWordWrap(True)
        lay.addWidget(self.lbl_durum)
        lay.addStretch()

        self._bilgi = {}
        self.yenile()

    def yenile(self):
        a = config_oku()
        self.ed_host.setText(str(a.get("host") or ""))
        try:
            self.ed_port.setValue(int(a.get("port") or 5432))
        except Exception:
            self.ed_port.setValue(5432)
        self.ed_db.setText(str(a.get("dbname") or ""))
        self.ed_user.setText(str(a.get("user") or ""))
        self.ed_sifre.setText(str(a.get("password") or ""))
        self.ed_url.setText(manifest_adresi())
        self.lbl_surum.setText(
            f"Kurulu surum: {surum()}   ·   Mod: {a.get('mode') or 'sqlite'}"
        )

    def _sunucu_kaydet(self):
        ok, mesaj = config_yaz(
            {
                "mode": "postgres",
                "host": self.ed_host.text().strip(),
                "port": self.ed_port.value(),
                "dbname": self.ed_db.text().strip(),
                "user": self.ed_user.text().strip(),
                "password": self.ed_sifre.text(),
            }
        )
        if ok:
            QMessageBox.information(
                self, "Kaydedildi",
                "Sunucu ayarlari sifrelenerek kaydedildi.\n"
                "Degisikliklerin gecerli olmasi icin programi yeniden baslatin.",
            )
        else:
            QMessageBox.warning(self, "Hata", mesaj)

    def _baglanti_test(self):
        try:
            import psycopg2

            conn = psycopg2.connect(
                host=self.ed_host.text().strip(),
                port=self.ed_port.value(),
                dbname=self.ed_db.text().strip(),
                user=self.ed_user.text().strip(),
                password=self.ed_sifre.text(),
                connect_timeout=10,
            )
            conn.cursor().execute("SELECT 1").fetchone()
            conn.close()
            QMessageBox.information(self, "Baglanti", "Sunucu baglantisi basarili.")
        except Exception as e:
            QMessageBox.warning(self, "Baglanti", f"Baglanti kurulamadi:\n{e}")

    def _url_kaydet(self):
        adres = self.ed_url.text().strip()
        if set_ayar("guncelleme_url", adres):
            QMessageBox.information(self, "Guncelleme", "Adres kaydedildi.")
        else:
            QMessageBox.warning(self, "Guncelleme", "Adres kaydedilemedi.")

    def _kontrol(self):
        ok, mesaj, bilgi = guncelleme_kontrol(self.ed_url.text().strip())
        self.lbl_durum.setText(mesaj)
        self._bilgi = bilgi or {}
        yeni = bool(ok and bilgi and bilgi.get("surum") and bilgi.get("url"))
        self.b_guncelle.setEnabled(yeni)
        if not ok:
            QMessageBox.warning(self, "Guncelleme", mesaj)
        elif not yeni:
            QMessageBox.information(self, "Guncelleme", mesaj)

    def _guncelle(self):
        if not self._bilgi:
            return
        cevap = QMessageBox.question(
            self, "Guncelle",
            f"Surum {self._bilgi.get('surum')} indirilip kurulacak.\n"
            "Program kapanip yeniden acilacak. Devam edilsin mi?",
        )
        if cevap != QMessageBox.StandardButton.Yes:
            return
        ok, mesaj, zip_yol = guncelleme_indir(self._bilgi)
        if not ok:
            QMessageBox.warning(self, "Guncelleme", mesaj)
            return
        ok, mesaj, klasor = guncelleme_hazirla(zip_yol)
        if not ok:
            QMessageBox.warning(self, "Guncelleme", mesaj)
            return
        ok, mesaj = guncelleme_uygula(klasor)
        if not ok:
            QMessageBox.warning(self, "Guncelleme", mesaj)
            return
        QMessageBox.information(self, "Guncelleme", mesaj)
        from PyQt6.QtWidgets import QApplication

        QApplication.quit()
