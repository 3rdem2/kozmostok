# -*- coding: utf-8 -*-
"""Denetci ekrani: ayni urun birlestirme + stok kodu standardi + bos kod havuzu."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, QWidget,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from core.denetci_servis import (
    ayni_isim_gruplari, urunleri_birlestir, standart_onizle, standart_uygula, havuz_listele,
)
from ui.tema import BG, TEXT, MUTED, btn_qss, tablo_qss


class DenetciDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Denetci - Urun Birlestirme ve Stok Kodu")
        self.resize(1000, 640)
        self.setStyleSheet(f"background:{BG}; color:{TEXT};")
        self._ana_item = {}
        lay = QVBoxLayout(self)
        self.sekmeler = QTabWidget()
        lay.addWidget(self.sekmeler)
        self.sekmeler.addTab(self._sekme_birlestir(), "Ayni urunler")
        self.sekmeler.addTab(self._sekme_standart(), "Stok kodu standardi")
        self.sekmeler.addTab(self._sekme_havuz(), "Bos kod havuzu")
        self._grup_yukle()
        self._standart_yukle()
        self._havuz_yukle()

    def _btn(self, ad, fn):
        b = QPushButton(ad)
        b.setStyleSheet(btn_qss() + "QPushButton { font-size:13px; letter-spacing:0px; }")
        b.clicked.connect(fn)
        return b

    def _sekme_birlestir(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel(
            "Adi birebir ayni urunler. Birlestirilecekleri isaretleyin, ANA kalacak satiri secip "
            "'Ana yap' deyin, sonra 'Birlestir'. Isaretlenenler ana urunun varyanti olur."))
        self.agac = QTreeWidget()
        self.agac.setColumnCount(7)
        self.agac.setHeaderLabels(["Urun", "ID", "Stok kodu", "Barkod", "Beden", "Stok", "Varyant"])
        self.agac.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.agac.setStyleSheet(tablo_qss())
        l.addWidget(self.agac, 1)
        h = QHBoxLayout()
        h.addWidget(self._btn("Ana yap", self._ana_yap))
        h.addWidget(self._btn("Birlestir", self._birlestir))
        h.addWidget(self._btn("Yenile", self._grup_yukle))
        self.lbl_grup = QLabel("")
        self.lbl_grup.setStyleSheet(f"color:{MUTED};")
        h.addWidget(self.lbl_grup)
        h.addStretch()
        l.addLayout(h)
        return w

    def _grup_yukle(self):
        self.agac.clear()
        self._ana_item = {}
        gruplar = ayni_isim_gruplari()
        for g in gruplar:
            ust = QTreeWidgetItem([f"{g['ad']}  ({len(g['urunler'])} kayit)"])
            f = QFont()
            f.setBold(True)
            ust.setFont(0, f)
            self.agac.addTopLevelItem(ust)
            for u in g["urunler"]:
                it = QTreeWidgetItem([
                    "", str(u["id"]), u["stok_kodu"] or "", u["barkod"] or "",
                    u["beden"] or (u["beden_tahmin"] + " (tahmin)" if u["beden_tahmin"] else ""), str(u["stok_adedi"]), str(u["varyant_sayisi"]),
                ])
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(0, Qt.CheckState.Unchecked)
                it.setData(0, Qt.ItemDataRole.UserRole, int(u["id"]))
                ust.addChild(it)
            ust.setExpanded(True)
        self.lbl_grup.setText(f"{len(gruplar)} grup")

    def _ana_yap(self):
        it = self.agac.currentItem()
        if not it or not it.parent():
            QMessageBox.information(self, "Ana yap", "Once bir urun satiri secin")
            return
        ust = it.parent()
        for i in range(ust.childCount()):
            c = ust.child(i)
            c.setText(0, "")
        it.setText(0, "ANA")
        it.setCheckState(0, Qt.CheckState.Unchecked)
        self._ana_item[id(ust)] = it

    def _birlestir(self):
        it = self.agac.currentItem()
        ust = it.parent() if it and it.parent() else it
        if not ust or ust.parent():
            QMessageBox.information(self, "Birlestir", "Bir grup secin")
            return
        ana = None
        diger = []
        for i in range(ust.childCount()):
            c = ust.child(i)
            if c.text(0) == "ANA":
                ana = c
            elif c.checkState(0) == Qt.CheckState.Checked:
                diger.append(c)
        if ana is None:
            QMessageBox.warning(self, "Birlestir", "Ana urunu secip 'Ana yap' deyin")
            return
        if not diger:
            QMessageBox.warning(self, "Birlestir", "Birlestirilecek satirlari isaretleyin")
            return
        ozet = "\n".join(f"  {c.text(1)}  {c.text(2)}  beden:{c.text(4)}  stok:{c.text(5)}" for c in diger)
        if QMessageBox.question(
            self, "Onay",
            f"ANA: {ana.text(1)} {ana.text(2)}\n\nVaryant olarak eklenecek:\n{ozet}\n\n"
            "Satis gecmisi korunur, bosalan KZM kodlari havuza eklenir. Onayliyor musunuz?",
        ) != QMessageBox.StandardButton.Yes:
            return
        sonuc = urunleri_birlestir(
            ana.data(0, Qt.ItemDataRole.UserRole),
            [c.data(0, Qt.ItemDataRole.UserRole) for c in diger],
        )
        if sonuc["ok"]:
            QMessageBox.information(self, "Tamam", sonuc["mesaj"])
        else:
            QMessageBox.critical(self, "Hata", sonuc["mesaj"])
        self._grup_yukle()
        self._standart_yukle()
        self._havuz_yukle()

    def _sekme_standart(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel(
            "KZM-0000 formatinda olmayan stok kodlari. Once havuzdaki bos kodlar, sonra yeni "
            "numaralar atanir. Varyant kodlari ana ile ayni olur, barkod soneki degismez."))
        self.tb_std = QTableWidget(0, 5)
        self.tb_std.setHorizontalHeaderLabels(["ID", "Urun", "Eski kod", "Yeni kod", "Islem"])
        self.tb_std.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tb_std.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tb_std.setStyleSheet(tablo_qss())
        l.addWidget(self.tb_std, 1)
        h = QHBoxLayout()
        h.addWidget(self._btn("Secilileri uygula", lambda: self._standart_uygula(False)))
        h.addWidget(self._btn("Tumunu uygula", lambda: self._standart_uygula(True)))
        h.addWidget(self._btn("Yenile", self._standart_yukle))
        h.addStretch()
        l.addLayout(h)
        return w

    def _standart_yukle(self):
        liste = standart_onizle()
        self.tb_std.setRowCount(0)
        for d in liste:
            r = self.tb_std.rowCount()
            self.tb_std.insertRow(r)
            for k, v in enumerate([d["id"], d["ad"], d["eski"], d["yeni"], d["tur"]]):
                self.tb_std.setItem(r, k, QTableWidgetItem(str(v)))

    def _standart_uygula(self, tumu: bool):
        if tumu:
            idler = None
            adet = self.tb_std.rowCount()
        else:
            satirlar = sorted({i.row() for i in self.tb_std.selectedItems()})
            idler = [int(self.tb_std.item(r, 0).text()) for r in satirlar]
            adet = len(idler)
        if not adet:
            QMessageBox.information(self, "Standart", "Uygulanacak kayit yok")
            return
        if QMessageBox.question(
            self, "Onay", f"{adet} kayit icin stok kodu/barkod degisecek. Eski degerler saklanir. Devam?"
        ) != QMessageBox.StandardButton.Yes:
            return
        sonuc = standart_uygula(idler)
        (QMessageBox.information if sonuc["ok"] else QMessageBox.critical)(
            self, "Sonuc", sonuc["mesaj"])
        self._standart_yukle()
        self._havuz_yukle()

    def _sekme_havuz(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("Birlestirme sonrasi bosalan stok kodlari. Yeni urunlere siradaki bu kodlar atanir."))
        self.tb_havuz = QTableWidget(0, 3)
        self.tb_havuz.setHorizontalHeaderLabels(["Stok kodu", "Eklenme", "Kaynak"])
        self.tb_havuz.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tb_havuz.setStyleSheet(tablo_qss())
        l.addWidget(self.tb_havuz, 1)
        return w

    def _havuz_yukle(self):
        self.tb_havuz.setRowCount(0)
        for d in havuz_listele():
            r = self.tb_havuz.rowCount()
            self.tb_havuz.insertRow(r)
            for k, key in enumerate(("stok_kodu", "eklenme", "kaynak")):
                self.tb_havuz.setItem(r, k, QTableWidgetItem(str(d.get(key) or "")))
