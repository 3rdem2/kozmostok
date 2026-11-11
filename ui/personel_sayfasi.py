# -*- coding: utf-8 -*-
"""Yonetim > Personel Raporlari — vardiya ozeti + islem gunlugu.

Sadece yonetim bolumunde gorunur: kim ne zaman giris/cikis yapti,
program acilis/kapanis, satis, iade, urun girisi kayitlari.
"""

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QDate, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDateEdit,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QAbstractItemView,
)

from core.database import BASE_DIR
from core.log_servis import ISIMLER, hareketler, vardiya_listesi
from core.logger import log_error

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


class PersonelRaporSayfasi(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#12141a; color:#e8e8e8;")
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        fil = QHBoxLayout()
        fil.addWidget(QLabel("Gun:"))
        self.tarih = QDateEdit()
        self.tarih.setCalendarPopup(True)
        self.tarih.setDisplayFormat("dd.MM.yyyy")
        self.tarih.setDate(QDate.currentDate())
        fil.addWidget(self.tarih)
        btn_bugun = QPushButton("Bugun")
        btn_bugun.clicked.connect(self.bugun)
        fil.addWidget(btn_bugun)
        btn_yenile = QPushButton("Yenile")
        btn_yenile.clicked.connect(self.yenile)
        fil.addWidget(btn_yenile)
        btn_excel = QPushButton("Excel'e aktar")
        btn_excel.clicked.connect(self.excel_aktar)
        fil.addWidget(btn_excel)
        fil.addStretch()
        root.addLayout(fil)

        self.tabs = QTabWidget()

        self.vardiya_tablo = QTableWidget(0, 5)
        self.vardiya_tablo.setHorizontalHeaderLabels(
            ["Kullanici", "Giris Tarihi", "Giris Saati", "Cikis Tarihi", "Cikis Saati"]
        )
        self._tablo_hazirla(self.vardiya_tablo)
        self.tabs.addTab(self.vardiya_tablo, "Vardiya")

        self.hareket_tablo = QTableWidget(0, 5)
        self.hareket_tablo.setHorizontalHeaderLabels(["Tarih", "Saat", "Kim", "Islem", "Detay"])
        self._tablo_hazirla(self.hareket_tablo)
        self.tabs.addTab(self.hareket_tablo, "Islem Gunlugu")

        root.addWidget(self.tabs, 1)
        self.yenile()

    def _tablo_hazirla(self, tablo):
        h = tablo.horizontalHeader()
        for col in range(4):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        tablo.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tablo.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tablo.verticalHeader().setVisible(False)
        tablo.setAlternatingRowColors(True)

    def bugun(self):
        self.tarih.setDate(QDate.currentDate())
        self.yenile()

    def _gun(self) -> str:
        d = self.tarih.date()
        return f"{d.year():04d}-{d.month():02d}-{d.day():02d}"

    def yenile(self):
        try:
            gun = self._gun()
            vardiya = vardiya_listesi(gun)
            self.vardiya_tablo.setRowCount(0)
            self.vardiya_tablo.setRowCount(len(vardiya))
            for i, v in enumerate(vardiya):
                self.vardiya_tablo.setItem(i, 0, QTableWidgetItem(v.get("kullanici") or ""))
                self.vardiya_tablo.setItem(i, 1, QTableWidgetItem(v.get("giris_tarihi") or ""))
                self.vardiya_tablo.setItem(i, 2, QTableWidgetItem(v.get("giris_saati") or ""))
                self.vardiya_tablo.setItem(i, 3, QTableWidgetItem(v.get("cikis_tarihi") or ""))
                self.vardiya_tablo.setItem(i, 4, QTableWidgetItem(v.get("cikis_saati") or ""))
            hareket = hareketler(gun, gun)
            self.hareket_tablo.setRowCount(0)
            self.hareket_tablo.setRowCount(len(hareket))
            for i, h in enumerate(hareket):
                self.hareket_tablo.setItem(i, 0, QTableWidgetItem(h.get("tarih") or ""))
                self.hareket_tablo.setItem(i, 1, QTableWidgetItem(h.get("saat") or ""))
                self.hareket_tablo.setItem(i, 2, QTableWidgetItem(h.get("kullanici") or ""))
                self.hareket_tablo.setItem(
                    i, 3,
                    QTableWidgetItem(ISIMLER.get(h.get("islem") or "", h.get("islem") or "")),
                )
                self.hareket_tablo.setItem(i, 4, QTableWidgetItem(h.get("detay") or ""))
        except Exception as e:
            log_error("Personel rapor", e, __file__, "PersonelRaporSayfasi.yenile")

    def excel_aktar(self):
        try:
            gun = self._gun()
            klasor = BASE_DIR / "raporlar" / "personel"
            klasor.mkdir(parents=True, exist_ok=True)
            yol = klasor / (
                f"personel_{gun.replace('-', '')}_{datetime.now().strftime('%H%M%S')}.xlsx"
            )
            wb = Workbook()
            ws = wb.active
            ws.title = "Vardiya"
            for i, h in enumerate(
                ["Kullanici", "Giris Tarihi", "Giris Saati", "Cikis Tarihi", "Cikis Saati"], 1
            ):
                c = ws.cell(1, i, h)
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor="1A1A1A")
                c.alignment = Alignment(horizontal="center")
            for r, v in enumerate(vardiya_listesi(gun), 2):
                ws.cell(r, 1, v.get("kullanici") or "")
                ws.cell(r, 2, v.get("giris_tarihi") or "")
                ws.cell(r, 3, v.get("giris_saati") or "")
                ws.cell(r, 4, v.get("cikis_tarihi") or "")
                ws.cell(r, 5, v.get("cikis_saati") or "")
            for col, w in (("A", 18), ("B", 14), ("C", 12), ("D", 14), ("E", 12)):
                ws.column_dimensions[col].width = w

            ws2 = wb.create_sheet("Islem Gunlugu")
            for i, h in enumerate(["Tarih", "Saat", "Kim", "Islem", "Detay"], 1):
                c = ws2.cell(1, i, h)
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor="1A1A1A")
                c.alignment = Alignment(horizontal="center")
            for r, h in enumerate(hareketler(gun, gun), 2):
                ws2.cell(r, 1, h.get("tarih") or "")
                ws2.cell(r, 2, h.get("saat") or "")
                ws2.cell(r, 3, h.get("kullanici") or "")
                ws2.cell(r, 4, ISIMLER.get(h.get("islem") or "", h.get("islem") or ""))
                ws2.cell(r, 5, h.get("detay") or "")
            for col, w in (("A", 12), ("B", 10), ("C", 14), ("D", 20), ("E", 40)):
                ws2.column_dimensions[col].width = w

            wb.save(yol)
            QMessageBox.information(self, "Personel raporu", f"Excel kaydedildi:\n{yol}")
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(klasor)))
            except Exception:
                pass
        except Exception as e:
            log_error("Personel excel", e, __file__, "PersonelRaporSayfasi.excel_aktar")
            QMessageBox.warning(self, "Hata", str(e))
