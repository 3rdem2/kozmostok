# -*- coding: utf-8 -*-
"""Kanal stok sayfalari, manuel duzeltme, transfer, hareket, API"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QLineEdit, QHeaderView,
    QAbstractItemView, QFormLayout, QMessageBox, QFrame,
    QDialog, QSpinBox, QComboBox, QDialogButtonBox, QInputDialog,
    QFileDialog, QDoubleSpinBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from core.kanal_servis import (
    kanal_urunleri, kanal_ozet, api_ayarlari_oku, api_ayarlari_kaydet,
    api_hazir_mi, senkron_wix, senkron_etsy, senkron_trendyol, API_KEYS,
    kanal_stok_yaz, kanal_transfer, stok_hareketleri, stok_dogrula, urun_birlestir,
    FAZLA_GIRIS_ESIK, KANAL_KOLON, kritik_kanal_uyarilari, kanal_yayindan_kaldir,
    kanal_satis_bildir, magaza_kritik_uyarilari, son_ayirmalar,
    bekleyen_ayirmalar, bekleyen_ayirma_yap, bekleyen_iptal, bekleyen_onayla,
    bekleyen_ayirma_geri_al, iade_teslim_al, bekleyen_hatirlatmalar,
    kanal_satislari, kanal_satis_iade, kanal_satis_rapor_csv,
    kargo_no_yaz, kargo_teslim_onayla, satis_durumu,
)
from core.rapor_servis import stok_sablon_excel_kanal, stok_excel_yukle_kanal
from core.logger import log_error
from ui.tema import GuvenliSpin

# Gothic Kozmosize — magaza ile ayni
_BORDER, _ACCENT, _TEXT = "#2a1a1a", "#8b0000", "#e8e0e0"


def _kim(w) -> str:
    """Ust parent'lardan giris yapan kullanici adini bulur."""
    while w is not None:
        adi = getattr(w, "kullanici_adi", "")
        if adi:
            return str(adi)
        w = w.parent()
    return "yonetici"


def _kbtn(bg: str = "#2a1a1a", hover: str = "") -> str:
    h = hover or bg
    return (
        f"QPushButton {{ background:{bg}; color:#f0eaea; font-size:11px; font-weight:600; "
        f"border-radius:4px; padding:3px 10px; min-height:24px; max-height:28px; "
        f"border:1px solid {_BORDER}; }}"
        f"QPushButton:hover {{ background:{h}; }}"
    )


def _kctrl() -> str:
    return (
        f"QComboBox {{ background:#1a1a22; color:{_TEXT}; border:1px solid {_BORDER}; "
        f"border-radius:4px; padding:2px 6px; min-height:26px; }}"
        f"QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; "
        f"width:18px; border-left:1px solid {_BORDER}; background:#1a1a22; }}"
        f"QComboBox::down-arrow {{ width:10px; height:10px; }}"
        f"QComboBox QAbstractItemView {{ background:#121218; color:{_TEXT}; "
        f"selection-background-color:{_ACCENT}; border:1px solid {_BORDER}; }}"
    )


def _ktablo() -> str:
    return (
        f"QTableWidget {{ background:#0e0e12; color:{_TEXT}; border:1px solid {_BORDER}; "
        f"gridline-color:#1f1a1a; font-size:12px; alternate-background-color:#121018; }}"
        f"QHeaderView::section {{ background:#1a1212; color:#c9a66b; padding:5px; "
        f"border:none; border-bottom:1px solid {_ACCENT}; font-size:11px; }}"
        f"QTableWidget::item:selected {{ background:{_ACCENT}; }}"
    )




class KanalStokDuzenleDialog(QDialog):
    def __init__(self, parent, urun: dict, kanal: str):
        super().__init__(parent)
        self.urun = urun
        self.kanal = kanal
        self.setWindowTitle(f"Stok duzenle — {kanal}")
        lay = QFormLayout(self)
        lay.addRow(QLabel(f"{urun.get('stok_kodu')} — {urun.get('ad')}"))
        if kanal == "ana":
            self.cmb = QComboBox()
            self.cmb.addItems(["magaza", "wix", "etsy", "trendyol"])
            lay.addRow("Kanal", self.cmb)
            self.spin = GuvenliSpin()
            self.spin.setRange(0, 999999)
            self.spin.setValue(int(urun.get("magaza_stok") or 0))
            self.cmb.currentTextChanged.connect(self._kanal_degisti)
            lay.addRow("Yeni stok", self.spin)
        else:
            self.cmb = None
            key = {"magaza": "magaza_stok", "wix": "wix_stok", "etsy": "etsy_stok", "trendyol": "trendyol_stok"}.get(kanal, "magaza_stok")
            self.spin = GuvenliSpin()
            self.spin.setRange(0, 999999)
            self.spin.setValue(int(urun.get(key) or 0))
            lay.addRow(f"{kanal} yeni stok", self.spin)
        self.ack = QLineEdit()
        self.ack.setPlaceholderText("Aciklama (opsiyonel)")
        lay.addRow("Not", self.ack)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)

    def _kanal_degisti(self, k):
        key = {"magaza": "magaza_stok", "wix": "wix_stok", "etsy": "etsy_stok", "trendyol": "trendyol_stok"}.get(k, "magaza_stok")
        self.spin.setValue(int(self.urun.get(key) or 0))

    def sonuc(self):
        kanal = self.cmb.currentText() if self.cmb else self.kanal
        return kanal, self.spin.value(), self.ack.text().strip()


class TransferDialog(QDialog):
    def __init__(self, parent, urun: dict):
        super().__init__(parent)
        self.urun = urun
        self.setWindowTitle("Kanal transfer")
        lay = QFormLayout(self)
        lay.addRow(QLabel(f"{urun.get('stok_kodu')} — {urun.get('ad')}"))
        self.kaynak = QComboBox()
        self.kaynak.addItems(["magaza", "wix", "etsy", "trendyol"])
        self.hedef = QComboBox()
        self.hedef.addItems(["magaza", "wix", "etsy", "trendyol"])
        self.hedef.setCurrentIndex(1)
        self.adet = GuvenliSpin()
        self.adet.setRange(1, 999999)
        self.adet.setValue(1)
        self.ack = QLineEdit()
        lay.addRow("Kaynak", self.kaynak)
        lay.addRow("Hedef", self.hedef)
        lay.addRow("Adet", self.adet)
        lay.addRow("Not", self.ack)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)


class HareketDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Stok hareket gecmisi")
        self.resize(720, 420)
        lay = QVBoxLayout(self)
        tab = QTableWidget()
        tab.setColumnCount(6)
        tab.setHorizontalHeaderLabels(["Tarih", "Kod", "Urun", "Tip", "Adet", "Aciklama"])
        tab.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        rows = stok_hareketleri(150)
        tab.setRowCount(len(rows))
        for i, h in enumerate(rows):
            tab.setItem(i, 0, QTableWidgetItem(str(h.get("tarih") or "")[-19:]))
            tab.setItem(i, 1, QTableWidgetItem(h.get("stok_kodu") or ""))
            tab.setItem(i, 2, QTableWidgetItem((h.get("urun_adi") or "")[:40]))
            tab.setItem(i, 3, QTableWidgetItem(h.get("hareket_tipi") or ""))
            adet = QTableWidgetItem(str(h.get("adet") or 0))
            adet.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tab.setItem(i, 4, adet)
            tab.setItem(i, 5, QTableWidgetItem(h.get("aciklama") or ""))
        lay.addWidget(tab)
        btn = QPushButton("Kapat")
        btn.clicked.connect(self.accept)
        lay.addWidget(btn)


class KanalSatisDialog(QDialog):
    """Manuel kanal satisi girisi: siparis no, adet, fiyat."""

    def __init__(self, parent, urun: dict):
        super().__init__(parent)
        self.setWindowTitle("Kanal satisi bildir")
        self.setModal(True)
        form = QFormLayout(self)
        lbl = QLabel(
            f"{urun.get('ad') or '?'} — {urun.get('stok_kodu') or '-'}"
            + (f" — Beden/Numara: {urun['beden']}" if urun.get("beden") else "")
        )
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size:10pt; font-weight:700;")
        form.addRow(lbl)
        self.ed_siparis = QLineEdit()
        self.ed_siparis.setPlaceholderText("Orn: TY-1234567")
        form.addRow("Siparis numarasi:", self.ed_siparis)
        self.sp_adet = QSpinBox()
        self.sp_adet.setRange(1, 99)
        form.addRow("Adet:", self.sp_adet)
        self.sp_fiyat = QDoubleSpinBox()
        self.sp_fiyat.setRange(0.0, 999999.0)
        self.sp_fiyat.setDecimals(2)
        self.sp_fiyat.setSuffix(" TL")
        try:
            self.sp_fiyat.setValue(float(urun.get("satis_fiyati") or 0))
        except Exception:
            pass
        form.addRow("Fiyat:", self.sp_fiyat)
        h = QHBoxLayout()
        btn_iptal = QPushButton("Vazgec")
        btn_iptal.clicked.connect(self.reject)
        btn_ok = QPushButton("Satisi bildir")
        btn_ok.clicked.connect(self.accept)
        h.addWidget(btn_iptal)
        h.addWidget(btn_ok)
        form.addRow(h)
        self.ed_siparis.setFocus()

    def sonuc(self) -> tuple[str, int, float]:
        return (
            self.ed_siparis.text().strip() or "-",
            int(self.sp_adet.value()),
            float(self.sp_fiyat.value()),
        )


class KanalStokSayfasi(QWidget):
    def __init__(self, kanal: str, baslik: str, parent=None):
        super().__init__(parent)
        self.kanal = kanal
        self._urunler: list = []
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        ust = QHBoxLayout()
        self.lbl = QLabel(baslik)
        self.lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        ust.addWidget(self.lbl)
        self.lbl_ozet = QLabel("")
        self.lbl_ozet.setStyleSheet("color:#8a7a7a; font-size:12px;")
        ust.addWidget(self.lbl_ozet)
        ust.addStretch()
        self.arama = QLineEdit()
        self.arama.setPlaceholderText("Barkod / ad / kod...")
        self.arama.setClearButtonEnabled(True)
        self.arama.setMinimumWidth(180)
        self.arama.setStyleSheet(
            f"font-size:13px; padding:4px 8px; background:#1a1a22; color:{_TEXT}; "
            f"border:1px solid {_ACCENT}; border-radius:4px; min-height:26px; max-height:32px;"
        )
        self.arama.returnPressed.connect(self.yenile)
        ust.addWidget(self.arama)
        self.cmb_stok_filtre = QComboBox()
        self.cmb_stok_filtre.addItem("Hepsi", "hepsi")
        self.cmb_stok_filtre.addItem("Stoktakiler", "stokta")
        self.cmb_stok_filtre.addItem("Tukenenler", "tukenen")
        self.cmb_stok_filtre.addItem("Kritik stok", "kritik")
        self.cmb_stok_filtre.addItem("Kanal kritik", "kanal_kritik")
        self.cmb_stok_filtre.setStyleSheet(_kctrl())
        self.cmb_stok_filtre.currentIndexChanged.connect(self.yenile)
        ust.addWidget(self.cmb_stok_filtre)
        root.addLayout(ust)
        self.lbl_uyari = QLabel("")
        self.lbl_uyari.setWordWrap(True)
        self.lbl_uyari.setStyleSheet("color:#ffffff; font-size:10pt; font-weight:600;")
        root.addWidget(self.lbl_uyari)
        # Son yapilan kanal ayirmalari (kim ayirdi bilgisiyle)
        self.lbl_ayirma = QLabel("")
        self.lbl_ayirma.setWordWrap(True)
        self.lbl_ayirma.setStyleSheet("color:#ffffff; font-size:10pt; font-weight:600;")
        root.addWidget(self.lbl_ayirma)
        # Bekleyen kanal satislari: OK ile onay (rapora eklenir), Iptal ile geri alinir
        self.bekleyen_kutu = QVBoxLayout()
        self.bekleyen_kutu.setSpacing(4)
        root.addLayout(self.bekleyen_kutu)

        btn_row = QHBoxLayout()
        b1 = QPushButton("Yenile")
        b1.clicked.connect(self.yenile)
        btn_row.addWidget(b1)
        b2 = QPushButton("Stok duzenle")
        b2.clicked.connect(self.stok_duzenle)
        btn_row.addWidget(b2)
        b3 = QPushButton("Transfer")
        b3.clicked.connect(self.transfer)
        btn_row.addWidget(b3)
        if kanal in ("ana", "magaza"):
            b_merge = QPushButton("Urunleri birlestir")
            b_merge.setStyleSheet(_kbtn("#8b0000", "#a52a2a"))
            b_merge.clicked.connect(self.urunleri_birlestir)
            btn_row.addWidget(b_merge)
        b4 = QPushButton("Excel sablon")
        b4.clicked.connect(self.excel_sablon)
        btn_row.addWidget(b4)
        b5 = QPushButton("Excel yukle")
        b5.clicked.connect(self.excel_yukle)
        btn_row.addWidget(b5)
        b6 = QPushButton("Hareketler")
        b6.clicked.connect(lambda: HareketDialog(self).exec())
        btn_row.addWidget(b6)
        if kanal in ("ana", "magaza"):
            b7 = QPushButton("Dogrula")
            b7.clicked.connect(self.dogrula)
            btn_row.addWidget(b7)
        if kanal in ("wix", "etsy", "trendyol"):
            b_yayin = QPushButton("Yayindan kaldir")
            b_yayin.setStyleSheet(_kbtn("#8b0000", "#a52a2a"))
            b_yayin.clicked.connect(self.yayindan_kaldir)
            btn_row.addWidget(b_yayin)
            b_ks = QPushButton("Kanal satisi bildir")
            b_ks.setStyleSheet(_kbtn("#3d2b1f", "#5a4030"))
            b_ks.clicked.connect(self.kanal_satisi_manuel)
            btn_row.addWidget(b_ks)
            b8 = QPushButton("API Senkron")
            b8.setStyleSheet(_kbtn("#2a1a2a", "#3a2a3a"))
            b8.clicked.connect(self.senkron)
            btn_row.addWidget(b8)
        if kanal == "wix":
            b9 = QPushButton("Wix CSV Yukle")
            b9.setStyleSheet(_kbtn("#1a3a2a", "#2d6a4f"))
            b9.clicked.connect(self.wix_csv_yukle)
            btn_row.addWidget(b9)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self.tablo = QTableWidget()
        if kanal == "ana":
            self.tablo.setColumnCount(9)
            self.tablo.setHorizontalHeaderLabels([
                "Stok Kodu", "Urun", "Magaza", "Wix Adet", "Etsy Adet", "TY Adet",
                "Uyari", "Kategori", "Fiyat"
            ])
        else:
            self.tablo.setColumnCount(7)
            self.tablo.setHorizontalHeaderLabels([
                "Stok Kodu", "Urun", "Kanal Adet", "Magaza", "Uyari", "Kategori", "Fiyat"
            ])
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tablo.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tablo.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tablo.setStyleSheet(_ktablo())
        self.tablo.doubleClicked.connect(self.stok_duzenle)
        root.addWidget(self.tablo)
        self.yenile()

    def _secili_urun(self) -> dict | None:
        row = self.tablo.currentRow()
        if row < 0 or row >= len(self._urunler):
            return None
        return self._urunler[row]

    def yenile(self):
        try:
            son = son_ayirmalar(self.kanal)
            if son:
                parcalar = []
                for s in son:
                    parca = (
                        f"{s.get('ad') or '?'} ({s.get('stok_kodu') or '-'})"
                        + (f" beden {s['beden']}" if s.get("beden") else "")
                        + f" — {s.get('adet')} adet — ayiran: {s.get('ayiran') or '-'}"
                    )
                    when = (s.get("ayirilma") or "")[:16]
                    if when:
                        parca += f" ({when})"
                    parcalar.append(parca)
                self.lbl_ayirma.setText("Son ayirmalar:  " + "  |  ".join(parcalar))
            else:
                self.lbl_ayirma.setText("")
        except Exception:
            self.lbl_ayirma.setText("")
        try:
            self._bekleyen_doldur()
        except Exception:
            pass
        try:
            arama = self.arama.text().strip()
            filtre = self.cmb_stok_filtre.currentData() or "hepsi"
            self._urunler = kanal_urunleri(self.kanal, arama=arama, stok_filtre=filtre)
            self.tablo.setRowCount(len(self._urunler))
            for i, u in enumerate(self._urunler):
                ana = int(u.get("magaza_stok") or 0)
                krit = int(u.get("kritik_stok") or 3)
                uyari = "KRITIK+KANAL" if u.get("uyari_kritik_kanal") else (
                    "KRITIK" if ana <= krit else ""
                )
                if self.kanal == "ana":
                    vals = [
                        u.get("stok_kodu") or "",
                        u.get("ad") or "",
                        str(ana),
                        str(int(u.get("wix_stok") or 0)),
                        str(int(u.get("etsy_stok") or 0)),
                        str(int(u.get("trendyol_stok") or 0)),
                        uyari,
                        u.get("kategori_adi") or "",
                        f"{float(u.get('satis_fiyati') or 0):,.0f}",
                    ]
                else:
                    key = f"{self.kanal}_stok"
                    vals = [
                        u.get("stok_kodu") or "",
                        u.get("ad") or "",
                        str(int(u.get(key) or 0)),
                        str(ana),
                        uyari,
                        u.get("kategori_adi") or "",
                        f"{float(u.get('satis_fiyati') or 0):,.0f}",
                    ]
                sayi_kolonlar = (2, 3, 4, 5, 6, 8) if self.kanal == "ana" else (2, 3, 6)
                for c, v in enumerate(vals):
                    item = QTableWidgetItem(v)
                    if c in sayi_kolonlar:
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                        )
                    if uyari and c == (6 if self.kanal == "ana" else 4):
                        item.setForeground(QColor("#e74c3c"))
                    if self.kanal == "ana" and c == 2 and ana <= krit:
                        item.setForeground(QColor("#e74c3c"))
                    self.tablo.setItem(i, c, item)

            # Ozet + uyari bandi
            o = kanal_ozet()
            if self.kanal == "ana":
                self.lbl_ozet.setText(
                    f"Ana stok toplam: {o.get('ana_stok', o.get('magaza', 0))}  |  "
                    f"Wix'te {o.get('wix_urun', 0)}  Etsy'de {o.get('etsy_urun', 0)}  "
                    f"TY'de {o.get('trendyol_urun', 0)} urun"
                )
            else:
                self.lbl_ozet.setText(
                    f"Bu kanalda listelenen: {len(self._urunler)} urun  |  "
                    f"Magaza stogu: {o.get('ana_stok', 0)}"
                )
            uy = kritik_kanal_uyarilari(50)
            if self.kanal in ("wix", "etsy", "trendyol"):
                uy = [x for x in uy if self.kanal in (x.get("kanallar") or [])]
            if uy:
                ornek = ", ".join(
                    f"{x.get('stok_kodu')}({x.get('ana_stok')})" for x in uy[:5]
                )
                self.lbl_uyari.setText(
                    f"Uyari: {len(uy)} urun magaza stogunda kritik ve kanalda satiliyor — {ornek}"
                    + (" ..." if len(uy) > 5 else "")
                )
            else:
                self.lbl_uyari.setText("")
        except Exception as e:
            log_error("Kanal yenile", e, __file__, "KanalStokSayfasi.yenile")


    def yayindan_kaldir(self):
        """Secili urunu bu kanal vitrininden cikar (adet=0). API kancasi hazir."""
        u = self._secili_urun()
        if not u:
            QMessageBox.information(self, "Secim", "Once urun secin")
            return
        if self.kanal not in ("wix", "etsy", "trendyol"):
            return
        if QMessageBox.question(
            self, "Yayindan kaldir",
            f"{u.get('ad')} urunu {self.kanal} listesinden tamamen cikarilsin mi?\n"
            "(Adet 0 + kanaldan kaldirilir. Sadece sifirlamak icin Stok duzenle kullanin.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        ok, msg = kanal_yayindan_kaldir(u["id"], self.kanal)
        QMessageBox.information(self, "Sonuc", msg)
        self.yenile()

    def kanal_satisi_manuel(self):
        """Manuel kanal satisi: siparis no + adet + fiyat sorulur; vitrin adedi duser."""
        u = self._secili_urun()
        if not u or self.kanal not in ("wix", "etsy", "trendyol"):
            QMessageBox.information(self, "Secim", "Kanal sayfasinda urun secin")
            return
        dlg = KanalSatisDialog(self, u)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        sip_no, adet, fiyat = dlg.sonuc()
        ok, msg, uyari = kanal_satis_bildir(
            self.kanal,
            stok_kodu=u.get("stok_kodu") or "",
            adet=adet,
            harici_siparis_no=sip_no,
            fiyat=fiyat,
        )
        if ok and uyari:
            QMessageBox.warning(
                self, "Kanal satisi uyarisi",
                uyari.get("mesaj") + "\n\nAyirma beklemede — mağaza ekranından 'Ayır' veya "
                "bu sayfadaki OK ile onaylayın; İptal ile geri alırsınız.",
            )
        else:
            QMessageBox.information(self, "Sonuc", msg)
        self.yenile()

    def _kim(self) -> str:
        return _kim(self)

    def _bekleyen_doldur(self):
        # Eski satirlar temizlenir
        while self.bekleyen_kutu.count():
            it = self.bekleyen_kutu.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        if self.kanal not in ("wix", "etsy", "trendyol"):
            return
        for b in bekleyen_ayirmalar():
            if b.get("kanal") != self.kanal:
                continue
            onay_bekliyor = b.get("durum") == "ayrildi_bekliyor"
            satir = QFrame()
            renk, kenar = ("#1a3a2a", "#2d6a4f") if onay_bekliyor else ("#3a2a1a", "#c9a66b")
            satir.setStyleSheet(
                f"QFrame {{ background:{renk}; border:1px solid {kenar}; border-radius:2px; }}"
            )
            h = QHBoxLayout(satir)
            h.setContentsMargins(8, 6, 8, 6)
            h.setSpacing(6)
            if onay_bekliyor:
                on = (b.get("ayirilma") or "")[:16]
                metin = (
                    f"AYRILDI — {b.get('ad') or '?'} — {b.get('stok_kodu') or '-'} — "
                    f"Beden/Numara: {b.get('beden_goster') or '-'} — "
                    f"{b.get('kanal')} satisi {b.get('adet')} adet — "
                    f"ayiran: {b.get('ayiran') or '-'} ({on}) — yonetici OK onayi bekleniyor"
                )
                if b.get("siparis_no"):
                    metin += f" — Siparis: {b['siparis_no']}"
            else:
                metin = (
                    f"BEKLEYEN: {b.get('ad') or '?'} — {b.get('stok_kodu') or '-'} — "
                    f"Beden/Numara: {b.get('beden_goster') or '-'} — Barkod: {b.get('barkod') or '-'} — "
                    f"{b.get('kanal')} satisi {b.get('adet')} adet, magaza stoku {b.get('ana_stok')}"
                )
                if b.get("siparis_no"):
                    metin += f" — Siparis: {b['siparis_no']}"
                if b.get("fiyat"):
                    try:
                        metin += f" — Fiyat: {float(b['fiyat']) * int(b.get('adet') or 1):.2f} TL"
                    except Exception:
                        pass
            lbl = QLabel(metin)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color:#ffffff; font-size:10pt; font-weight:700; border:none;")
            h.addWidget(lbl, 1)
            btn_ok = QPushButton("OK")
            if onay_bekliyor:
                btn_ok.setToolTip("Ayirmayi onayla: satis Satilanlar bolumune gecer (sifre gerekir)")
            else:
                btn_ok.setToolTip("Once magaza ekraninda ayirilmali; ayirilinca sifreyle onaylanir")
            btn_ok.setStyleSheet(_kbtn("#1a3a2a", "#2d6a4f"))
            btn_ok.clicked.connect(lambda _, bid=b["id"], od=onay_bekliyor: self._bekleyen_ok(bid, od))
            h.addWidget(btn_ok)
            btn_iptal = QPushButton("İptal")
            if onay_bekliyor:
                btn_iptal.setToolTip("Ayirmayi geri al veya satisi tamamen iptal et")
                btn_iptal.clicked.connect(lambda _, bid=b["id"]: self._ayrildi_iptal(bid))
            else:
                btn_iptal.setToolTip("Satisi geri al: vitrin adedi geri eklenir, rapora eklenmez")
                btn_iptal.clicked.connect(lambda _, bid=b["id"]: self._bekleyen_iptal(bid))
            h.addWidget(btn_iptal)
            self.bekleyen_kutu.addWidget(satir)

    def _ayrildi_iptal(self, bek_id: int):
        kutu = QMessageBox(self)
        kutu.setWindowTitle("Ayirma iptali")
        kutu.setText("Ayirmayi nasil geri almak istiyorsunuz?")
        b_geri = kutu.addButton("Sadece ayirmayi geri al", QMessageBox.ButtonRole.ActionRole)
        b_tam = kutu.addButton("Satisi tamamen iptal et", QMessageBox.ButtonRole.DestructiveRole)
        kutu.addButton("Vazgec", QMessageBox.ButtonRole.RejectRole)
        kutu.exec()
        if kutu.clickedButton() is b_geri:
            ok, msg = bekleyen_ayirma_geri_al(bek_id, kim=_kim(self), tam_iptal=False)
        elif kutu.clickedButton() is b_tam:
            ok, msg = bekleyen_ayirma_geri_al(bek_id, kim=_kim(self), tam_iptal=True)
        else:
            return
        if ok:
            QMessageBox.information(self, "Iptal", msg)
        else:
            QMessageBox.warning(self, "Hata", msg)
        self.yenile()

    def _bekleyen_ok(self, bek_id: int, onay_bekliyor: bool):
        if not onay_bekliyor:
            QMessageBox.information(
                self, "Ayirma bekleniyor",
                "Bu satis magaza ekraninda henuz ayrilmamis. Magaza ekraninda uyari "
                "gosteriliyor; 'Ayir' yapildiktan sonra OK ile onaylayabilirsiniz.",
            )
            return
        from ui.magaza_ekrani import AyirOnayDialog
        bek = next((b for b in bekleyen_ayirmalar() if b.get("id") == bek_id), {})
        dlg = AyirOnayDialog(self, bek, _kim(self))
        dlg.setWindowTitle("Satis onayi (yonetici)")
        dlg.ed_kullanici.setPlaceholderText("Yonetici kullanici adi")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        ok, msg = bekleyen_onayla(bek_id, onaylayan=dlg._onaylanan)
        if ok:
            QMessageBox.information(self, "Onaylandi", msg)
        else:
            QMessageBox.warning(self, "Hata", msg)
        self.yenile()

    def _bekleyen_iptal(self, bek_id: int):
        cevap = QMessageBox.question(
            self, "Satis iptal",
            "Satis geri alinacak: vitrin adedi geri eklenecek, rapora eklenmeyecek. Onayliyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if cevap != QMessageBox.StandardButton.Yes:
            return
        ok, msg = bekleyen_iptal(bek_id, iptal_eden=self._kim())
        if ok:
            QMessageBox.information(self, "Iptal", msg)
        else:
            QMessageBox.warning(self, "Hata", msg)
        self.yenile()

    def stok_duzenle(self):

        u = self._secili_urun()
        if not u:
            QMessageBox.information(self, "Secim", "Once bir urun secin (cift tik da olur).")
            return
        dlg = KanalStokDuzenleDialog(self, u, self.kanal if self.kanal != "ana" else "ana")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        kanal, yeni, ack = dlg.sonuc()
        ok, msg, fazla = kanal_stok_yaz(u["id"], kanal, yeni, ack, fazla_onay=False)
        if fazla:
            if QMessageBox.question(
                self, "Fazla giris", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
            ok, msg, _ = kanal_stok_yaz(u["id"], kanal, yeni, ack, fazla_onay=True)
        if ok:
            QMessageBox.information(self, "Tamam", msg)
            self.yenile()
        else:
            QMessageBox.warning(self, "Hata", msg)

    def urunleri_birlestir(self):
        """Secili urunlerden ilki ana, digerleri ona birlesir."""
        rows = sorted({i.row() for i in self.tablo.selectedIndexes()})
        if len(rows) < 2:
            QMessageBox.information(
                self, "Birleştirme",
                "En az 2 ürün seçin.\n"
                "İlk seçilen (listede en üstteki) ANA ürün olur; "
                "diğerlerinin stoku ona eklenir.",
            )
            return
        urunler = [self._urunler[r] for r in rows if r < len(self._urunler)]
        if len(urunler) < 2:
            return
        ana = urunler[0]
        diger = urunler[1:]
        liste = "\n".join(
            f"- {u.get('stok_kodu')} | {u.get('ad','')[:40]}" for u in diger
        )
        if QMessageBox.question(
            self, "Birleştirme onayı",
            f"ANA ürün:\n{ana.get('stok_kodu')} — {ana.get('ad')}\n\n"
            f"Birleşecekler:\n{liste}\n\n"
            f"Stoklar ANA ürüne toplanır; diğerleri pasife alınır ve "
            f"açıklamaya birleştirme notu yazılır. Devam?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        ok, msg = urun_birlestir(ana["id"], [u["id"] for u in diger])
        if ok:
            QMessageBox.information(self, "Tamam", msg)
            self.yenile()
        else:
            QMessageBox.warning(self, "Hata", msg)

    def transfer(self):
        u = self._secili_urun()
        if not u:
            QMessageBox.information(self, "Secim", "Once urun secin.")
            return
        dlg = TransferDialog(self, u)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        ok, msg = kanal_transfer(
            u["id"], dlg.kaynak.currentText(), dlg.hedef.currentText(),
            dlg.adet.value(), dlg.ack.text().strip(),
        )
        if ok:
            QMessageBox.information(self, "Transfer", msg)
            self.yenile()
        else:
            QMessageBox.warning(self, "Hata", msg)

    def excel_sablon(self):
        kanal = self.kanal if self.kanal in KANAL_KOLON else "magaza"
        ok, yol = stok_sablon_excel_kanal(kanal)
        if ok:
            QMessageBox.information(self, "Sablon", f"Kaydedildi:\n{yol}")
        else:
            QMessageBox.warning(self, "Hata", yol)

    def excel_yukle(self):
        yol, _ = QFileDialog.getOpenFileName(self, "Excel", "", "Excel (*.xlsx)")
        if not yol:
            return
        kanal = self.kanal if self.kanal in KANAL_KOLON else "magaza"
        if QMessageBox.question(
            self, "Onay", f"Stoklar [{kanal}] kanalina yazilacak. Devam?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        r = stok_excel_yukle_kanal(yol, varsayilan_kanal=kanal)
        QMessageBox.information(self, "Sonuc", r.get("mesaj", ""))
        self.yenile()

    def dogrula(self):
        d = stok_dogrula()
        ekstra = ""
        if d.get("negatif"):
            ekstra = "\n\nNegatif stoklu urunler:\n" + "\n".join(
                f"- {x.get('stok_kodu')} {x.get('ad')}" for x in d["negatif"][:15]
            )
        QMessageBox.information(self, "Stok dogrulama", d.get("mesaj", "") + ekstra)

    def wix_csv_yukle(self):
        yol, _ = QFileDialog.getOpenFileName(self, "Wix CSV", "", "CSV (*.csv);;Tum (*.*)")
        if not yol:
            return
        try:
            from core.urun_servis import wix_csv_aktar
            if QMessageBox.question(
                self, "Onay", "Wix katalog CSV aktarilsin mi?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
            r = wix_csv_aktar(yol)
            QMessageBox.information(self, "Wix CSV", r.get("mesaj", str(r)))
            self.yenile()
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))

    def senkron(self):
        fn = {"wix": senkron_wix, "etsy": senkron_etsy, "trendyol": senkron_trendyol}.get(self.kanal)
        if not fn:
            return
        ok, msg = fn()
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Senkron", msg)


class SatisRaporSayfasi(QWidget):
    """Satilanlar: tamamlanan kanal satislari, iade isaretleme ve CSV rapor."""

    BASLIK = ["Siparis No", "Urun", "Varyant", "Kanal", "Adet", "Fiyat",
              "Tarih-Saat", "Ayiran", "Kargo No", "Durum"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:#14141a; color:{_TEXT};")
        root = QVBoxLayout(self)
        ust = QHBoxLayout()
        self.cmb_kanal = QComboBox()
        self.cmb_kanal.addItem("Tum kanallar", "")
        self.cmb_kanal.addItem("Wix", "wix")
        self.cmb_kanal.addItem("Etsy", "etsy")
        self.cmb_kanal.addItem("Trendyol", "trendyol")
        self.cmb_kanal.setStyleSheet(_kctrl())
        self.cmb_kanal.currentIndexChanged.connect(self.yenile)
        ust.addWidget(self.cmb_kanal)
        b1 = QPushButton("Yenile")
        b1.clicked.connect(self.yenile)
        ust.addWidget(b1)
        b2 = QPushButton("Iade (secili)")
        b2.setStyleSheet(_kbtn("#8b0000", "#a52a2a"))
        b2.clicked.connect(self.secili_iade)
        ust.addWidget(b2)
        b6 = QPushButton("Iade teslim al (secili)")
        b6.setStyleSheet(_kbtn("#1a3a2a", "#2d6a4f"))
        b6.clicked.connect(self.iade_teslim)
        ust.addWidget(b6)
        b4 = QPushButton("Kargo No gir (secili)")
        b4.clicked.connect(self.kargo_no_gir)
        ust.addWidget(b4)
        b5 = QPushButton("Teslim edildi (secili)")
        b5.setStyleSheet(_kbtn("#1a3a2a", "#2d6a4f"))
        b5.clicked.connect(self.teslim_onayla)
        ust.addWidget(b5)
        b3 = QPushButton("Excel raporu (CSV)")
        b3.clicked.connect(self.rapor_olustur)
        ust.addWidget(b3)
        ust.addStretch()
        root.addLayout(ust)
        self.tablo = QTableWidget()
        self.tablo.setColumnCount(len(self.BASLIK))
        self.tablo.setHorizontalHeaderLabels(self.BASLIK)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tablo.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tablo.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.verticalHeader().setVisible(False)
        hdr = self.tablo.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setMinimumSectionSize(64)
        # Urun (1) ve Kargo No (8) esner; genislikler yenilemelerde korunur
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for kolon, genislik in ((0, 110), (2, 70), (3, 80), (4, 56),
                                (5, 80), (6, 130), (7, 90), (8, 150), (9, 120)):
            self.tablo.setColumnWidth(kolon, genislik)
        root.addWidget(self.tablo)
        self.yenile()

    def yenile(self):
        try:
            rows = kanal_satislari(self.cmb_kanal.currentData() or "")
            self._rows = rows
            self.tablo.setRowCount(len(rows))
            for i, r in enumerate(rows):
                try:
                    tutar = float(r.get("fiyat") or 0) * int(r.get("adet") or 1)
                except Exception:
                    tutar = 0.0
                vals = [
                    r.get("siparis_no") or "",
                    r.get("ad") or "",
                    r.get("beden_goster") or "-",
                    r.get("kanal") or "",
                    str(r.get("adet") or 0),
                    f"{float(r.get('fiyat') or 0):.2f}",
                    (r.get("ayirilma") or "")[:16],
                    r.get("ayiran") or "-",
                    r.get("kargo_no") or "",
                    satis_durumu(r),
                ]
                for j, v in enumerate(vals):
                    it = QTableWidgetItem(str(v))
                    if r.get("durum") == "iade":
                        it.setForeground(QColor("#d9534f"))
                    elif r.get("durum") == "teslim":
                        it.setForeground(QColor("#6ee7a0"))
                    elif r.get("durum") == "kargoda" or (r.get("durum") == "ayrildi" and r.get("kargo_no")):
                        it.setForeground(QColor("#f0c36d"))
                    self.tablo.setItem(i, j, it)
        except Exception as e:
            log_error("Satis rapor", e, __file__, "SatisRaporSayfasi.yenile")

    def secili_iade(self):
        row = self.tablo.currentRow()
        if row < 0 or row >= len(self._rows):
            QMessageBox.information(self, "Secim", "Once bir satis secin")
            return
        r = self._rows[row]
        if r.get("durum") not in ("ayrildi", "kargoda", "teslim"):
            if r.get("durum") == "iade_bekliyor":
                QMessageBox.information(self, "Iade", "Bu satis icin iade zaten beklemede — 'Iade teslim al' kullanin")
            else:
                QMessageBox.information(self, "Iade", "Bu satis iade edilemez")
            return
        cevap = QMessageBox.question(
            self, "Iade onayi",
            f"{r.get('ad')} ({r.get('stok_kodu')}) — {r.get('adet')} adet icin iade kaydi olusturulacak. "
            "Iade kargosu magazaya ulasinca 'Iade teslim al' ile stoga giris yapacaksiniz. Onayliyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if cevap != QMessageBox.StandardButton.Yes:
            return
        ok, msg = kanal_satis_iade(r["id"], iade_eden=_kim(self))
        if ok:
            QMessageBox.information(self, "Iade", msg)
        else:
            QMessageBox.warning(self, "Hata", msg)
        self.yenile()

    def iade_teslim(self):
        row = self.tablo.currentRow()
        if row < 0 or row >= len(self._rows):
            QMessageBox.information(self, "Secim", "Once bir satis secin")
            return
        r = self._rows[row]
        if r.get("durum") != "iade_bekliyor":
            QMessageBox.information(self, "Iade", "Teslim alinacak iade bulunamadi")
            return
        cevap = QMessageBox.question(
            self, "Iade teslim al",
            f"{r.get('ad')} — {r.get('adet')} adet iade kargosu magazaya ulasti mi? "
            "Onayda urun magaza stoguna giris yapar.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if cevap != QMessageBox.StandardButton.Yes:
            return
        ok, msg = iade_teslim_al(r["id"], alan=_kim(self))
        if ok:
            QMessageBox.information(self, "Iade", msg)
        else:
            QMessageBox.warning(self, "Hata", msg)
        self.yenile()

    def kargo_no_gir(self):
        row = self.tablo.currentRow()
        if row < 0 or row >= len(self._rows):
            QMessageBox.information(self, "Secim", "Once bir satis secin")
            return
        r = self._rows[row]
        if r.get("durum") not in ("ayrildi", "kargoda"):
            QMessageBox.information(self, "Kargo", "Kargo numarasi onaylanmis satisa eklenebilir")
            return
        mevcut = r.get("kargo_no") or ""
        no, ok_ = QInputDialog.getText(
            self, "Kargo takip numarasi",
            f"{r.get('ad')} — Siparis {r.get('siparis_no') or '-'}\nKargo takip numarasi:",
            text=mevcut,
        )
        if not ok_:
            return
        ok, msg = kargo_no_yaz(r["id"], no.strip(), yazan=_kim(self))
        if ok:
            self.yenile()
            QMessageBox.information(self, "Kargo", msg)
        else:
            QMessageBox.warning(self, "Hata", msg)

    def teslim_onayla(self):
        row = self.tablo.currentRow()
        if row < 0 or row >= len(self._rows):
            QMessageBox.information(self, "Secim", "Once bir satis secin")
            return
        r = self._rows[row]
        if r.get("durum") not in ("ayrildi", "kargoda"):
            QMessageBox.information(self, "Teslim", "Bu satis teslim olarak isaretlenemez")
            return
        cevap = QMessageBox.question(
            self, "Teslim onayi",
            f"{r.get('ad')} — Siparis {r.get('siparis_no') or '-'} kargo varisi onaylandi mi? "
            "Durum 'Teslim edildi' olarak degisecek.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if cevap != QMessageBox.StandardButton.Yes:
            return
        ok, msg = kargo_teslim_onayla(r["id"], onaylayan=_kim(self))
        if ok:
            QMessageBox.information(self, "Teslim", msg)
        else:
            QMessageBox.warning(self, "Hata", msg)
        self.yenile()

    def rapor_olustur(self):
        try:
            yol = kanal_satis_rapor_csv(self.cmb_kanal.currentData() or "")
            QMessageBox.information(self, "Rapor", f"Rapor olusturuldu:\n{yol}")
        except Exception as e:
            QMessageBox.warning(self, "Hata", str(e))


class ApiAyarSayfasi(QWidget):
    LABELS = {
        "wix_api_key": "Wix API Key",
        "wix_site_id": "Wix Site ID",
        "wix_account_id": "Wix Account ID",
        "etsy_api_key": "Etsy API Key",
        "etsy_shared_secret": "Etsy Shared Secret",
        "etsy_shop_id": "Etsy Shop ID",
        "etsy_access_token": "Etsy Access Token",
        "trendyol_supplier_id": "Trendyol Supplier ID",
        "trendyol_api_key": "Trendyol API Key",
        "trendyol_api_secret": "Trendyol API Secret",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        baslik = QLabel("API Baglanti Ayarlari")
        baslik.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        lay.addWidget(baslik)
        bilgi = QLabel(
            "Anahtarlari girip kaydedin. Canli senkron sonraki adimda; "
            "simdilik kanal sayfalarindan manuel / Excel kullanin."
        )
        bilgi.setWordWrap(True)
        bilgi.setStyleSheet("color:#95a5a6;")
        lay.addWidget(bilgi)
        self.edits = {}
        for kanal, keys in API_KEYS.items():
            fr = QFrame()
            fr.setStyleSheet("QFrame { background:#1a1a1a; border:1px solid #2c3e50; border-radius:6px; }")
            fl = QFormLayout(fr)
            fl.setContentsMargins(12, 10, 12, 10)
            bas = QLabel(kanal.upper())
            bas.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            fl.addRow(bas)
            ay = api_ayarlari_oku(kanal)
            for k in keys:
                e = QLineEdit()
                e.setText(ay.get(k, ""))
                e.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
                self.edits[k] = e
                fl.addRow(self.LABELS.get(k, k), e)
            lay.addWidget(fr)
        btn = QPushButton("API Ayarlarini Kaydet")
        btn.setStyleSheet(
            "QPushButton { background:#27ae60; color:white; font-weight:bold; padding:8px 16px; border-radius:4px; }"
        )
        btn.clicked.connect(self.kaydet)
        lay.addWidget(btn)
        lay.addStretch()

    def kaydet(self):
        try:
            for kanal, keys in API_KEYS.items():
                api_ayarlari_kaydet(kanal, {k: self.edits[k].text().strip() for k in keys})
            QMessageBox.information(self, "Kaydedildi", "API ayarlari kaydedildi.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))
