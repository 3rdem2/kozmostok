# -*- coding: utf-8 -*-
"""Gun sonlari arsivi: arama, detay, Excel acma."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QDateEdit, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from core.gun_sonu_servis import excel_dosyasi, gun_sonu_getir, gun_sonu_listele
from core.logger import log_error


def _tl(v) -> str:
    try:
        return f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00"


class GunSonlariSayfasi(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.kayitlar: list[dict] = []
        lay = QVBoxLayout(self)
        lay.setSpacing(6)

        ust = QHBoxLayout()
        ust.setSpacing(6)
        ust.addWidget(QLabel("Baslangic"))
        self.dt_bas = QDateEdit()
        self.dt_bas.setCalendarPopup(True)
        self.dt_bas.setDisplayFormat("dd.MM.yyyy")
        self.dt_bas.setDate(date.today() - timedelta(days=90))
        ust.addWidget(self.dt_bas)
        ust.addWidget(QLabel("Bitis"))
        self.dt_bit = QDateEdit()
        self.dt_bit.setCalendarPopup(True)
        self.dt_bit.setDisplayFormat("dd.MM.yyyy")
        self.dt_bit.setDate(date.today())
        ust.addWidget(self.dt_bit)
        ust.addWidget(QLabel("Kullanici"))
        self.ed_ara = QLineEdit()
        self.ed_ara.setPlaceholderText("kasiyer / yonetici adi")
        self.ed_ara.returnPressed.connect(self.yenile)
        ust.addWidget(self.ed_ara, 1)
        b_ara = QPushButton("Ara")
        b_ara.clicked.connect(self.yenile)
        ust.addWidget(b_ara)
        b_excel = QPushButton("Excel ac")
        b_excel.clicked.connect(self.excel_ac)
        ust.addWidget(b_excel)
        b_kaydet = QPushButton("Excel kaydet")
        b_kaydet.clicked.connect(self.excel_kaydet)
        ust.addWidget(b_kaydet)
        lay.addLayout(ust)

        self.tablo = QTableWidget(0, 9)
        self.tablo.setHorizontalHeaderLabels([
            "Tarih", "Alan", "Ciro", "Nakit satis", "Masraf",
            "Onceki devir", "Beklenen", "Sayilan", "Fark",
        ])
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tablo.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tablo.itemSelectionChanged.connect(self._detay)
        lay.addWidget(self.tablo, 1)

        self.lbl_detay = QLabel("")
        self.lbl_detay.setWordWrap(True)
        self.lbl_detay.setStyleSheet("color:#9a9a9a; font-size:11px;")
        lay.addWidget(self.lbl_detay)

        self.yenile()

    def yenile(self):
        try:
            bas = self.dt_bas.date().toString("yyyy-MM-dd")
            bit = self.dt_bit.date().toString("yyyy-MM-dd")
            self.kayitlar = gun_sonu_listele(bas, bit, self.ed_ara.text().strip())
            self.tablo.setRowCount(len(self.kayitlar))
            for i, r in enumerate(self.kayitlar):
                degerler = [
                    r.get("tarih") or "",
                    r.get("kullanici") or "",
                    _tl(r.get("ciro")),
                    _tl(r.get("nakit_satis")),
                    _tl(r.get("masraf")),
                    _tl(r.get("onceki_devir")),
                    _tl(r.get("beklenen_nakit")),
                    _tl(r.get("sayilan_nakit")),
                    _tl(r.get("fark")),
                ]
                for j, v in enumerate(degerler):
                    it = QTableWidgetItem(str(v))
                    if j >= 2:
                        it.setTextAlignment(
                            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        )
                    if j == 8:
                        try:
                            f = float(r.get("fark") or 0)
                        except Exception:
                            f = 0.0
                        if abs(f) >= 0.005:
                            it.setForeground(Qt.GlobalColor.red if f < 0 else Qt.GlobalColor.yellow)
                    self.tablo.setItem(i, j, it)
            self.lbl_detay.setText(f"{len(self.kayitlar)} gun sonu kaydi")
        except Exception as e:
            log_error("Gun sonlari listesi", e, __file__, "GunSonlariSayfasi.yenile")

    def _secili_id(self) -> int:
        row = self.tablo.currentRow()
        if 0 <= row < len(self.kayitlar):
            return int(self.kayitlar[row].get("id") or 0)
        return 0

    def _detay(self):
        gid = self._secili_id()
        if not gid:
            return
        k = gun_sonu_getir(gid)
        if not k:
            return
        kalemler = ", ".join(
            f"{x.get('ad')}: {_tl(x.get('tutar'))}" for x in (k.get("kalemler") or [])
        ) or "kalem yok"
        self.lbl_detay.setText(
            f"{k.get('tarih')} · {k.get('kullanici')} · devir {_tl(k.get('devir'))} · "
            f"kayit {k.get('olusturma')}\n{kalemler}"
            + (f"\nNot: {k.get('notlar')}" if k.get("notlar") else "")
        )

    def excel_ac(self):
        gid = self._secili_id()
        if not gid:
            QMessageBox.information(self, "Gun Sonu", "Once bir gun sonu secin.")
            return
        ok, yol = excel_dosyasi(gid)
        if not ok:
            QMessageBox.warning(self, "Excel", yol)
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(yol)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", yol])
            else:
                subprocess.Popen(["xdg-open", yol])
        except Exception as e:
            log_error("Excel ac", e, __file__, "excel_ac")
            QMessageBox.information(self, "Excel", f"Dosya: {yol}")

    def excel_kaydet(self):
        gid = self._secili_id()
        if not gid:
            QMessageBox.information(self, "Gun Sonu", "Once bir gun sonu secin.")
            return
        from PyQt6.QtWidgets import QFileDialog

        ok, yol = excel_dosyasi(gid)
        if not ok:
            QMessageBox.warning(self, "Excel", yol)
            return
        hedef, _ = QFileDialog.getSaveFileName(
            self, "Excel kaydet", os.path.basename(yol), "Excel (*.xlsx)"
        )
        if not hedef:
            return
        try:
            with open(yol, "rb") as f:
                veri = f.read()
            with open(hedef, "wb") as f:
                f.write(veri)
            QMessageBox.information(self, "Excel", f"Kaydedildi:\n{hedef}")
        except Exception as e:
            log_error("Excel kaydet", e, __file__, "excel_kaydet")
            QMessageBox.warning(self, "Hata", str(e))
