# -*- coding: utf-8 -*-
"""Gun sonu ekrani: kasa sayimi, masraf listesi, fark, sifre onayi."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QDoubleSpinBox, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.gun_sonu_servis import (
    devir_ozeti, gun_ozeti, gun_sonu_kaydet, gun_sonu_var_mi, sayim_kalemleri,
)
from core.logger import log_error


def _tl(v: float) -> str:
    return f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"


class GunSonuDialog(QDialog):
    def __init__(self, parent=None, kullanici_adi: str = "", tarih: str | None = None):
        super().__init__(parent)
        self.kullanici_adi = kullanici_adi or ""
        self.tarih = tarih or date.today().strftime("%Y-%m-%d")
        self.kaydedildi = False
        self.gun_sonu_id = 0
        self.setWindowTitle("Gun Sonu")
        self.resize(760, 660)
        self._ui()
        self._yukle()

    def _ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        bas = QLabel(f"GUN SONU  ·  {self.tarih}")
        bas.setStyleSheet("font-size:15px; font-weight:800; color:#e8e8e8;")
        root.addWidget(bas)
        self.lbl_kullanici = QLabel(f"Gun sonunu alan: {self.kullanici_adi}")
        self.lbl_kullanici.setStyleSheet("color:#c9a66b; font-size:12px;")
        root.addWidget(self.lbl_kullanici)

        ozet = QFrame()
        ozet.setStyleSheet("QFrame { background:#14161c; border:1px solid #2a2f3a; }")
        of = QVBoxLayout(ozet)
        of.setContentsMargins(10, 8, 10, 8)
        of.setSpacing(3)
        self.lbl_ozet = QLabel("")
        self.lbl_ozet.setStyleSheet("background:transparent; color:#cfcfcf; font-size:12px;")
        self.lbl_ozet.setWordWrap(True)
        of.addWidget(self.lbl_ozet)
        root.addWidget(ozet)

        root.addWidget(QLabel("SAYIM LISTESI — tutarlari doldurun"))
        self.tablo = QTableWidget(0, 5)
        self.tablo.setHorizontalHeaderLabels(["Kalem", "Tur", "Tutar", "Adet", "Aciklama"])
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.setAlternatingRowColors(True)
        h = self.tablo.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.tablo, 1)

        alt = QHBoxLayout()
        alt.setSpacing(8)
        alt.addWidget(QLabel("Sayilan nakit"))
        self.sp_nakit = QDoubleSpinBox()
        self.sp_nakit.setRange(0, 10_000_000)
        self.sp_nakit.setDecimals(2)
        self.sp_nakit.setSingleStep(50)
        self.sp_nakit.setSuffix(" TL")
        self.sp_nakit.setMinimumWidth(160)
        self.sp_nakit.valueChanged.connect(self._nakit_degisti)
        alt.addWidget(self.sp_nakit)
        self.lbl_fark = QLabel("Fark: 0,00 TL")
        self.lbl_fark.setStyleSheet("font-weight:800; font-size:13px;")
        alt.addWidget(self.lbl_fark)
        alt.addStretch()
        root.addLayout(alt)

        self.not_edit = QLineEdit()
        self.not_edit.setPlaceholderText("Not (opsiyonel)")
        root.addWidget(self.not_edit)

        sifre_row = QHBoxLayout()
        sifre_row.setSpacing(8)
        sifre_row.addWidget(QLabel("Kendi sifreniz"))
        self.sifre_edit = QLineEdit()
        self.sifre_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.sifre_edit.setPlaceholderText("gun sonunu onaylamak icin sifreniz")
        self.sifre_edit.returnPressed.connect(self.kaydet)
        sifre_row.addWidget(self.sifre_edit, 1)
        root.addLayout(sifre_row)

        btn = QHBoxLayout()
        btn.addStretch()
        b_iptal = QPushButton("Vazgec")
        b_iptal.clicked.connect(self.reject)
        btn.addWidget(b_iptal)
        self.b_kaydet = QPushButton("Gun sonunu al")
        self.b_kaydet.setObjectName("birincil")
        self.b_kaydet.clicked.connect(self.kaydet)
        btn.addWidget(self.b_kaydet)
        root.addLayout(btn)

    def _yukle(self):
        mevcut = gun_sonu_var_mi(self.tarih)
        if mevcut:
            QMessageBox.information(
                self, "Gun Sonu",
                f"{self.tarih} icin gun sonu zaten alinmis.\n"
                f"Alan: {mevcut.get('kullanici')}\n"
                f"Sayilan: {_tl(mevcut.get('sayilan_nakit'))}",
            )
            self.b_kaydet.setEnabled(False)
            self.sifre_edit.setEnabled(False)

        o = gun_ozeti(self.tarih)
        d = devir_ozeti(self.tarih)
        self.lbl_ozet.setText(
            f"Ciro {_tl(o['ciro'])}   ·   Nakit satis {_tl(o['nakit'])}   ·   "
            f"Kart {_tl(o['kart'])}   ·   Masraf {_tl(o['masraf'])}\n"
            f"Onceki nakit devir {_tl(d['onceki_devir'])}"
            + (f" ({d['onceki_tarih']})" if d["onceki_tarih"] else "")
            + f"   ·   Beklenen nakit {_tl(d['beklenen_nakit'])}"
        )
        self._beklenen = float(d["beklenen_nakit"])

        kalemler = sayim_kalemleri()
        self.tablo.setRowCount(len(kalemler))
        for i, k in enumerate(kalemler):
            self.tablo.setItem(i, 0, QTableWidgetItem(str(k.get("ad") or "")))
            self.tablo.setItem(i, 1, QTableWidgetItem(str(k.get("tur") or "diger")))
            sp = QDoubleSpinBox()
            sp.setRange(0, 10_000_000)
            sp.setDecimals(2)
            sp.setSingleStep(10)
            sp.setGroupSeparatorShown(True)
            sp.valueChanged.connect(self._tutar_degisti)
            self.tablo.setCellWidget(i, 2, sp)
            ad = QDoubleSpinBox()
            ad.setRange(0, 100000)
            ad.setDecimals(0)
            self.tablo.setCellWidget(i, 3, ad)
            self.tablo.setItem(i, 4, QTableWidgetItem(""))
        self._nakit_satiri = 0
        for i in range(self.tablo.rowCount()):
            if (self.tablo.item(i, 1).text() or "").lower() == "nakit":
                self._nakit_satiri = i
                break
        self._fark_guncelle()

    def _nakit_satiri_spin(self) -> QDoubleSpinBox | None:
        w = self.tablo.cellWidget(self._nakit_satiri, 2)
        return w if isinstance(w, QDoubleSpinBox) else None

    def _nakit_degisti(self, v: float):
        sp = self._nakit_satiri_spin()
        if sp is not None and abs(sp.value() - v) > 0.001:
            sp.blockSignals(True)
            sp.setValue(v)
            sp.blockSignals(False)
        self._fark_guncelle()

    def _tutar_degisti(self, _v=None):
        sp = self._nakit_satiri_spin()
        if sp is not None and abs(self.sp_nakit.value() - sp.value()) > 0.001:
            self.sp_nakit.blockSignals(True)
            self.sp_nakit.setValue(sp.value())
            self.sp_nakit.blockSignals(False)
        self._fark_guncelle()

    def _fark_guncelle(self):
        fark = float(self.sp_nakit.value()) - float(getattr(self, "_beklenen", 0))
        renk = "#4caf50" if abs(fark) < 0.005 else ("#e53935" if fark < 0 else "#c9a66b")
        self.lbl_fark.setText(f"Fark: {_tl(fark)}")
        self.lbl_fark.setStyleSheet(f"font-weight:800; font-size:13px; color:{renk};")

    def _kalemler(self) -> list[dict]:
        out = []
        for i in range(self.tablo.rowCount()):
            ad = (self.tablo.item(i, 0).text() or "").strip()
            tur = (self.tablo.item(i, 1).text() or "diger").strip()
            sp = self.tablo.cellWidget(i, 2)
            ad_sp = self.tablo.cellWidget(i, 3)
            ac = (self.tablo.item(i, 4).text() or "").strip() if self.tablo.item(i, 4) else ""
            out.append({
                "ad": ad, "tur": tur,
                "tutar": float(sp.value()) if sp else 0.0,
                "adet": float(ad_sp.value()) if ad_sp else 0.0,
                "aciklama": ac,
            })
        return out

    def kaydet(self):
        if not self.b_kaydet.isEnabled():
            return
        sifre = self.sifre_edit.text().strip()
        if not sifre:
            QMessageBox.warning(self, "Sifre", "Gun sonunu onaylamak icin kendi sifrenizi girin.")
            self.sifre_edit.setFocus()
            return
        if QMessageBox.question(
            self, "Onay",
            f"{self.tarih} gun sonu alinsin mi?\nSayilan nakit: {_tl(self.sp_nakit.value())}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            ok, msg, gid = gun_sonu_kaydet(
                self.tarih, self.kullanici_adi, sifre,
                float(self.sp_nakit.value()), self._kalemler(),
                self.not_edit.text().strip(),
            )
        except Exception as e:
            log_error("Gun sonu kaydet", e, __file__, "GunSonuDialog.kaydet")
            QMessageBox.critical(self, "Hata", str(e))
            return
        if ok:
            self.kaydedildi = True
            self.gun_sonu_id = gid
            QMessageBox.information(self, "Gun Sonu", msg)
            self.accept()
        else:
            QMessageBox.warning(self, "Gun Sonu", msg)
            self.sifre_edit.clear()
            self.sifre_edit.setFocus()
