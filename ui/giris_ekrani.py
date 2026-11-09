# -*- coding: utf-8 -*-
"""Program giris ekrani"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QMessageBox, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from pathlib import Path
from PyQt6.QtGui import QFont, QPixmap

from core.kullanici_servis import giris_yap, sifre_unuttum, sifre_sifirla_kurtarma, kullanici_kayit
from core.logger import log_error
from core.yollar import varlik


class GirisEkrani(QWidget):
    # Tema global; ek stil gerekmez
    giris_ok = pyqtSignal(dict)  # kullanici dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ui()

    def _ui(self):
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        kutu = QFrame()
        kutu.setFixedWidth(380)
        kutu.setStyleSheet(
            "QFrame { background:#1a1a1a; border:1px solid #2c3e50; border-radius:10px; }"
            "QLineEdit { background:#111; color:#ecf0f1; border:1px solid #34495e; "
            "padding:8px; border-radius:4px; font-size:14px; }"
            "QPushButton { padding:8px; border-radius:4px; font-weight:bold; }"
        )
        lay = QVBoxLayout(kutu)
        lay.setSpacing(10)
        lay.setContentsMargins(24, 24, 24, 24)

        logo_row = QHBoxLayout()
        logo_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_logo = QLabel()
        logo_yol = varlik("logo_kozmosize.png")
        if logo_yol.exists():
            pix = QPixmap(str(logo_yol))
            if not pix.isNull():
                lbl_logo.setPixmap(
                    pix.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                )
        logo_row.addWidget(lbl_logo)
        baslik = QLabel("KOZMOSIZE foreverunderground")
        baslik.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        logo_row.addWidget(baslik)
        lay.addLayout(logo_row)
        alt = QLabel("Giris")
        alt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        alt.setStyleSheet("color:#95a5a6;")
        lay.addWidget(alt)

        self.kullanici = QLineEdit()
        self.kullanici.setPlaceholderText("Kullanici adi")
        lay.addWidget(self.kullanici)

        self.sifre = QLineEdit()
        self.sifre.setPlaceholderText("Sifre")
        self.sifre.setEchoMode(QLineEdit.EchoMode.Password)
        self.sifre.returnPressed.connect(self.giris)
        lay.addWidget(self.sifre)

        btn = QPushButton("Giris yap")
        btn.setStyleSheet("background:#e74c3c; color:white;")
        btn.clicked.connect(self.giris)
        lay.addWidget(btn)

        btn_unuttum = QPushButton("Sifremi unuttum (e-posta)")
        btn_unuttum.setStyleSheet("background:#34495e; color:white;")
        btn_unuttum.clicked.connect(self.unuttum)
        lay.addWidget(btn_unuttum)

        btn_kurtar = QPushButton("Kurtarma kodu ile sifirla")
        btn_kurtar.setStyleSheet("background:#2c3e50; color:white;")
        btn_kurtar.clicked.connect(self.kurtar)
        lay.addWidget(btn_kurtar)

        btn_yeni = QPushButton("Yeni kullanici / Sifre olustur")
        btn_yeni.setStyleSheet("background:#27ae60; color:white;")
        btn_yeni.clicked.connect(self.yeni_kullanici)
        lay.addWidget(btn_yeni)

        self.mesaj = QLabel("")
        self.mesaj.setWordWrap(True)
        self.mesaj.setStyleSheet("color:#95a5a6; font-size:12px;")
        lay.addWidget(self.mesaj)

        bil = QLabel("")
        bil.setVisible(False)
        bil.setStyleSheet("color:#7f8c8d; font-size:11px;")
        bil.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(bil)

        root.addWidget(kutu)

    def giris(self):
        try:
            k = self.kullanici.text().strip()
            s = self.sifre.text()
            if not k or not s:
                self.mesaj.setText("Kullanici adi ve sifre zorunlu.")
                return
            ok, sonuc = giris_yap(k, s)
            if not ok:
                self.mesaj.setStyleSheet("color:#e74c3c;")
                self.mesaj.setText(str(sonuc))
                return
            self.mesaj.setStyleSheet("color:#27ae60;")
            self.mesaj.setText("Giris basarili...")
            self.giris_ok.emit(sonuc)
        except Exception as e:
            log_error("Giris UI", e, __file__, "GirisEkrani.giris")
            self.mesaj.setText(str(e))

    def unuttum(self):
        k = self.kullanici.text().strip()
        if not k:
            QMessageBox.warning(self, "Eksik", "Once kullanici adini yazin.")
            return
        ok, msg = sifre_unuttum(k)
        if ok:
            QMessageBox.information(self, "E-posta", msg)
        else:
            QMessageBox.warning(self, "Sifre sifirlama", msg)

    def kurtar(self):
        from PyQt6.QtWidgets import QInputDialog
        k = self.kullanici.text().strip()
        if not k:
            k, ok = QInputDialog.getText(self, "Kullanici", "Kullanici adi:")
            if not ok or not k.strip():
                return
            k = k.strip()
        kod, ok = QInputDialog.getText(self, "Kurtarma", "Kurtarma kodu:")
        if not ok or not kod:
            return
        yeni, ok = QInputDialog.getText(self, "Yeni sifre", "Yeni sifre (min 4):")
        if not ok or not yeni:
            return
        ok2, msg = sifre_sifirla_kurtarma(k, kod, yeni)
        QMessageBox.information(self, "Sonuc", msg)

    def yeni_kullanici(self):
        from PyQt6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Yeni kullanici - sifre olustur")
        dlg.setMinimumWidth(340)
        form = QFormLayout(dlg)
        adi = QLineEdit()
        email = QLineEdit()
        email.setPlaceholderText("ornek@mail.com")
        s1 = QLineEdit()
        s1.setEchoMode(QLineEdit.EchoMode.Password)
        s2 = QLineEdit()
        s2.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Kullanici adi", adi)
        form.addRow("E-posta", email)
        form.addRow("Sifre (min 4)", s1)
        form.addRow("Sifre tekrar", s2)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        while dlg.exec() == QDialog.DialogCode.Accepted:
            ok, msg = kullanici_kayit(adi.text(), s1.text(), s2.text(), email.text())
            if ok:
                self.kullanici.setText(adi.text().strip())
                self.sifre.clear()
                self.mesaj.setStyleSheet("color:#27ae60;")
                self.mesaj.setText("Hesap olusturuldu. Sifrenizle giris yapin.")
                return
            QMessageBox.warning(self, "Hata", msg)
