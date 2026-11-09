# -*- coding: utf-8 -*-
"""Ana pencere — giris sonrasi magaza / yonetim"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QMessageBox,
    QDialog, QLineEdit, QDialogButtonBox, QApplication,
)
from PyQt6.QtCore import Qt, QTimer
from pathlib import Path
from datetime import datetime
from PyQt6.QtGui import QFont, QPixmap

from core.logger import log_error, log_info
from core.yollar import varlik
from core.kullanici_servis import pin_dogrula
from ui.giris_ekrani import GirisEkrani
from ui.magaza_ekrani import MagazaEkrani
from ui.yonetim_panel import YonetimPaneli


class PinDialog(QDialog):
    def __init__(self, parent=None, kullanici_adi=""):
        super().__init__(parent)
        self.kullanici_adi = kullanici_adi
        self.setWindowTitle("Yonetim PIN")
        self.setFixedWidth(320)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Yonetim sifresi / PIN:"))
        self.pin_edit = QLineEdit()
        self.pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_edit.returnPressed.connect(self.kontrol_et)
        lay.addWidget(self.pin_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.kontrol_et)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def kontrol_et(self):
        try:
            if pin_dogrula(self.pin_edit.text().strip(), self.kullanici_adi):
                self.accept()
            else:
                QMessageBox.warning(self, "Hata", "PIN yanlis!")
                self.pin_edit.clear()
                self.pin_edit.setFocus()
        except Exception as e:
            log_error("PIN", e, __file__, "PinDialog.kontrol_et")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KOZMOSIZE foreverunderground — Stok & Kasa")
        self.resize(1200, 720)
        self.kullanici = None
        try:
            self._ui_olustur()
        except Exception as e:
            log_error("Ana pencere olusturulamadi", e, __file__, "MainWindow.__init__")
            raise

    def _ui_olustur(self):
        merkezi = QWidget()
        self.setCentralWidget(merkezi)
        ana = QVBoxLayout(merkezi)
        ana.setContentsMargins(0, 0, 0, 0)

        # Ust bar
        self.ust = QWidget()
        self.ust.setStyleSheet("background:#0e1015; border-bottom:1px solid #2a2f3a;")
        ust_l = QHBoxLayout(self.ust)
        ust_l.setContentsMargins(12, 8, 12, 8)
        self.lbl_logo = QLabel()
        logo_yol = varlik("logo_kozmosize.png")
        if logo_yol.exists():
            pix = QPixmap(str(logo_yol))
            if not pix.isNull():
                self.lbl_logo.setPixmap(
                    pix.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                )
        self.lbl_logo.setFixedSize(40, 40)
        ust_l.addWidget(self.lbl_logo)
        self.lbl_baslik = QLabel("KOZMOSIZE foreverunderground")
        self.lbl_baslik.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        ust_l.addWidget(self.lbl_baslik)
        ust_l.addStretch()
        self.lbl_saat_ust = QLabel("")
        self.lbl_saat_ust.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_saat_ust.setStyleSheet(
            "color:#c9a66b; font-size:13px; font-weight:600; letter-spacing:1px;"
        )
        ust_l.addWidget(self.lbl_saat_ust, 1)
        ust_l.addStretch()

        self.btn_magaza = QPushButton("Magaza")
        self.btn_yonetim = QPushButton("Yonetim")
        self.btn_guncelle = QPushButton("Guncelle")
        self.btn_cikis = QPushButton("Cikis")
        self.btn_magaza.setObjectName("ikincil")
        self.btn_yonetim.setObjectName("ikincil")
        self.btn_guncelle.setObjectName("ikincil")
        self.btn_cikis.setObjectName("tehlike")
        self.btn_magaza.clicked.connect(self.magaza_goster)
        self.btn_yonetim.clicked.connect(self.yonetim_iste)
        self.btn_guncelle.clicked.connect(self.guncelle)
        self.btn_cikis.clicked.connect(self.cikis_yap)
        ust_l.addWidget(self.btn_magaza)
        ust_l.addWidget(self.btn_yonetim)
        ust_l.addWidget(self.btn_guncelle)
        ust_l.addWidget(self.btn_cikis)
        self.btn_guncelle.setVisible(False)
        self.ust.setVisible(False)
        ana.addWidget(self.ust)
        self._saat_timer_ust = QTimer(self)
        self._saat_timer_ust.timeout.connect(self._saat_ust_guncelle)
        self._saat_timer_ust.start(1000)
        self._saat_ust_guncelle()
        self._senkron_timer = QTimer(self)
        self._senkron_timer.timeout.connect(self._ekranlari_senkron)
        self._senkron_timer.start(8000)


        self.stack = QStackedWidget()
        self.giris = GirisEkrani()
        self.giris.giris_ok.connect(self._giris_sonrasi)
        self.stack.addWidget(self.giris)
        self.magaza_ekrani = None
        self.yonetim_ekrani = None
        ana.addWidget(self.stack)

    def _giris_sonrasi(self, kullanici: dict):
        self.kullanici = kullanici
        self.ust.setVisible(True)
        if self.magaza_ekrani is None:
            self.magaza_ekrani = MagazaEkrani()
            self.stack.addWidget(self.magaza_ekrani)
        self.magaza_ekrani.kullanici_adi = kullanici.get("kullanici_adi") or ""
        self.magaza_ekrani.kullanici_adi = kullanici.get("kullanici_adi") or ""
        if self.yonetim_ekrani is None:
            self.yonetim_ekrani = YonetimPaneli()
            self.stack.addWidget(self.yonetim_ekrani)
        self.yonetim_ekrani.kullanici_adi = kullanici.get("kullanici_adi") or ""
        # Kasiyer sadece magaza; yonetici magaza ile baslar
        self.magaza_goster()
        yonetici = kullanici.get("rol") == "yonetici"
        self.btn_yonetim.setVisible(yonetici)
        self.btn_guncelle.setVisible(yonetici)
        log_info(f"Giris: {kullanici.get('kullanici_adi')} / {kullanici.get('rol')}")

    def _saat_ust_guncelle(self):
        if hasattr(self, "lbl_saat_ust"):
            simdi = datetime.now()
            self.lbl_saat_ust.setText(
                simdi.strftime("%d.%m.%Y  ·  %H:%M:%S")
            )

    def guncelle(self):
        """Sunucudaki surum manifestini kontrol eder, yeniyse indirip kurar."""
        from core.guncelleme_servis import kontrol, indir, hazirla, uygula

        try:
            ok, mesaj, bilgi = kontrol()
            if not ok:
                QMessageBox.warning(self, "Guncelleme", mesaj)
                return
            if not (bilgi.get("surum") and bilgi.get("url")):
                QMessageBox.information(self, "Guncelleme", mesaj)
                return
            cevap = QMessageBox.question(
                self, "Guncelle",
                f"{mesaj}\n\nIndirilip kurulsun mu? Program yeniden baslatilacak.",
            )
            if cevap != QMessageBox.StandardButton.Yes:
                return
            ok, mesaj, zip_yol = indir(bilgi)
            if not ok:
                QMessageBox.warning(self, "Guncelleme", mesaj)
                return
            ok, mesaj, klasor = hazirla(zip_yol)
            if not ok:
                QMessageBox.warning(self, "Guncelleme", mesaj)
                return
            ok, mesaj = uygula(klasor)
            if not ok:
                QMessageBox.warning(self, "Guncelleme", mesaj)
                return
            QMessageBox.information(self, "Guncelleme", mesaj)
            QApplication.quit()
        except Exception as e:
            log_error("Guncelleme", e, __file__, "MainWindow.guncelle")
            QMessageBox.warning(self, "Guncelleme", f"Hata: {e}")

    def _ekranlari_senkron(self):
        """Acik ekrani veritabanindan yeniler. Iki program acikken kasa satisi yonetimde gorunur."""
        try:
            if self.magaza_ekrani is None:
                return
            guncel = self.stack.currentWidget()
            if guncel is self.magaza_ekrani:
                self.magaza_ekrani.ozet_yenile()
                self.magaza_ekrani.satis_listesi_yenile()
                self.magaza_ekrani.masraf_listesi_yenile()
            elif self.yonetim_ekrani is not None and guncel is self.yonetim_ekrani:
                self.yonetim_ekrani.yenile(sessiz=True)
        except Exception as e:
            log_error("Ekran senkron", e, __file__, "_ekranlari_senkron")

    def magaza_goster(self):
        try:
            if self.magaza_ekrani:
                self.stack.setCurrentWidget(self.magaza_ekrani)
                self.lbl_baslik.setText("KOZMOSIZE foreverunderground  ·  Magaza")
                self.magaza_ekrani.yenile_hepsi()
        except Exception as e:
            log_error("Magaza", e, __file__, "magaza_goster")

    def yonetim_iste(self):
        try:
            if not self.kullanici or self.kullanici.get("rol") != "yonetici":
                QMessageBox.warning(self, "Yetki", "Yonetim sadece yoneticiler icin.")
                return
            # Admin/yonetici zaten giris yapti — ikinci PIN yok
            self.stack.setCurrentWidget(self.yonetim_ekrani)
            self.lbl_baslik.setText("KOZMOSIZE foreverunderground  ·  Yonetim")
            if hasattr(self.yonetim_ekrani, "yenile"):
                self.yonetim_ekrani.yenile()
            log_info("Yonetim acildi")
        except Exception as e:
            log_error("Yonetim", e, __file__, "yonetim_iste")
            QMessageBox.warning(self, "Hata", "Yonetim acilamadi.")

    def cikis_yap(self):
        self.kullanici = None
        self.ust.setVisible(False)
        self.stack.setCurrentWidget(self.giris)
        self.giris.sifre.clear()
        self.lbl_baslik.setText("KOZMOSIZE foreverunderground")

    def closeEvent(self, event):
        try:
            from core.rapor_servis import kapanis_yedek
            from core.yedek_servis import yedek_al
            ok, yol = kapanis_yedek()
            if ok:
                log_info(f"Kapanis excel: {yol}")
            ok2, yol2 = yedek_al("kapanis")
            if ok2:
                log_info(f"Kapanis db: {yol2}")
        except Exception as e:
            log_error("Kapanis", e, __file__, "closeEvent")
        event.accept()
