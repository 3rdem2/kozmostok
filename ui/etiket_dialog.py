# -*- coding: utf-8 -*-
"""Barkod etiketi penceresi: ArgoDesigner (.axpx) uretimi, onizleme, PRN/CSV."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from core.etiket_axpx import (
    etiketler_uret, sablon_ayarla, sablon_kopyala, sablon_olcusu, sablon_oku,
    sablonlar, varsayilan_sablon,
)
from core.etiket_servis import (
    Etiket, csv_kaydet, etiket_ayarlari, etiket_ayarlari_kaydet, ham_yazdir,
    prn_kaydet, urun_etiketleri, yazicilar, zpl_olustur,
)
from core.logger import log_error

_ONBELLEK: dict[str, QPixmap] = {}
_LOGO_PIX: QPixmap | None = None


def _logo_pixmap() -> QPixmap | None:
    global _LOGO_PIX
    if _LOGO_PIX is not None:
        return _LOGO_PIX if not _LOGO_PIX.isNull() else None
    try:
        from core.etiket_axpx import LOGO_YOLU

        if not LOGO_YOLU.exists():
            _LOGO_PIX = QPixmap()
            return None
        _LOGO_PIX = QPixmap(str(LOGO_YOLU))
        return _LOGO_PIX if not _LOGO_PIX.isNull() else None
    except Exception as e:
        log_error("Logo onizleme", e, __file__, "_logo_pixmap")
        _LOGO_PIX = QPixmap()
        return None


def _barkod_pixmap(barkod: str) -> QPixmap | None:
    if barkod in _ONBELLEK:
        return _ONBELLEK[barkod]
    try:
        import barcode
        from barcode.writer import ImageWriter

        kod = barcode.get("code128", barkod, writer=ImageWriter())
        yol = os.path.join(tempfile.gettempdir(), f"kz_bc_{abs(hash(barkod))}.png")
        kod.save(
            yol[:-4],
            options={
                "module_width": 0.33,
                "module_height": 12,
                "write_text": False,
                "quiet_zone": 1,
                "background": "white",
                "foreground": "black",
            },
        )
        pix = QPixmap(yol)
        _ONBELLEK[barkod] = pix
        return pix
    except Exception as e:
        log_error("Barkod cizim", e, __file__, "_barkod_pixmap")
        return None


def etiket_ciz(qp: QPainter, e: Etiket, ayar: dict, px_mm: float, cerceve: bool = True):
    """Onizleme cizimi. Olcu sablondan gelir."""
    w = float(ayar.get("genislik_mm", 30)) * px_mm
    h = float(ayar.get("yukseklik_mm", 40)) * px_mm
    qp.fillRect(QRectF(0, 0, w, h), QColor("white"))
    if cerceve:
        qp.setPen(QPen(QColor("#bbbbbb"), max(1.0, px_mm * 0.1)))
        qp.drawRect(QRectF(0, 0, w, h))

    qp.setPen(QColor("black"))
    sol = w * 0.04
    logo = _logo_pixmap()
    metin_w = w * 0.92
    if logo:
        lh = h * 0.13
        lw = min(w * 0.30, lh * (logo.width() / max(1, logo.height())))
        qp.drawPixmap(
            QRectF(w - sol - lw, h * 0.02, lw, lh), logo, QRectF(logo.rect())
        )
        metin_w = w * 0.92 - lw - w * 0.02
    f_ad = QFont("Arial", max(5, int(h * 0.055)))
    f_ad.setBold(True)
    qp.setFont(f_ad)
    qp.drawText(
        QRectF(sol, h * 0.02, metin_w, h * 0.10),
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        (e.ad or "")[:34],
    )

    if e.beden:
        f_b = QFont("Arial", max(4, int(h * 0.045)))
        qp.setFont(f_b)
        qp.drawText(
            QRectF(sol, h * 0.11, w * 0.92, h * 0.07),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            f"Beden: {e.beden}",
        )

    pix = _barkod_pixmap(e.barkod)
    bc_y = h * 0.20
    bc_h = h * 0.42
    if pix and not pix.isNull():
        qp.drawPixmap(QRectF(sol, bc_y, w * 0.92, bc_h), pix, QRectF(pix.rect()))
    else:
        qp.setPen(QPen(QColor("black"), 1))
        qp.drawRect(QRectF(sol, bc_y, w * 0.92, bc_h))
        qp.drawText(QRectF(sol, bc_y, w * 0.92, bc_h), int(Qt.AlignmentFlag.AlignCenter), e.barkod)

    f_k = QFont("Arial", max(4, int(h * 0.040)))
    qp.setFont(f_k)
    qp.drawText(
        QRectF(sol, h * 0.63, w * 0.92, h * 0.06),
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        e.barkod,
    )
    if e.fiyat:
        f_f = QFont("Arial", max(5, int(h * 0.075)))
        f_f.setBold(True)
        qp.setFont(f_f)
        qp.drawText(
            QRectF(sol, h * 0.80, w * 0.92, h * 0.16),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            f"{e.fiyat:,.0f}".replace(",", ".") + " TL",
        )


class EtiketDialog(QDialog):
    def __init__(self, parent=None, urun_id: int = 0):
        super().__init__(parent)
        self.urun_id = urun_id
        self.ayar = etiket_ayarlari()
        self.etiketler: list[Etiket] = []
        self.sablon: dict | None = None
        self.sablon_yolu = None
        self.setWindowTitle("Barkod Etiketi")
        self.resize(900, 640)
        self._ui()
        self._sablonlari_doldur()
        self._yukle()

    def _ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        ust = QHBoxLayout()
        ust.setSpacing(6)
        ust.addWidget(QLabel("Etiket sablonu"))
        self.cmb_sablon = QComboBox()
        self.cmb_sablon.setMinimumWidth(240)
        self.cmb_sablon.currentIndexChanged.connect(self._sablon_degisti)
        ust.addWidget(self.cmb_sablon, 1)
        b_ekle = QPushButton("Sablon ekle...")
        b_ekle.clicked.connect(self._sablon_ekle)
        ust.addWidget(b_ekle)
        b_yenile = QPushButton("Yenile")
        b_yenile.setToolTip("Sablon klasorunu yeniden tara")
        b_yenile.clicked.connect(self._sablon_yenile)
        ust.addWidget(b_yenile)
        self.lbl_olcu = QLabel("")
        self.lbl_olcu.setStyleSheet("color:#c9a66b; font-weight:600;")
        ust.addWidget(self.lbl_olcu)
        root.addLayout(ust)

        govde = QHBoxLayout()
        govde.setSpacing(10)

        self.tablo = QTableWidget(0, 3)
        self.tablo.setHorizontalHeaderLabels(["Beden / Varyant", "Barkod", "Adet"])
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tablo.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tablo.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tablo.itemSelectionChanged.connect(self._onizleme_yenile)
        govde.addWidget(self.tablo, 3)

        sag = QVBoxLayout()
        sag.setSpacing(6)
        self.onizleme = QLabel()
        self.onizleme.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.onizleme.setMinimumSize(300, 240)
        self.onizleme.setStyleSheet("background:#151515; border:1px solid #2a1a1a;")
        sag.addWidget(self.onizleme, 1)
        self.lbl_bilgi = QLabel("")
        self.lbl_bilgi.setWordWrap(True)
        self.lbl_bilgi.setStyleSheet("color:#8a7a7a; font-size:11px;")
        sag.addWidget(self.lbl_bilgi)
        govde.addLayout(sag, 2)
        root.addLayout(govde, 1)

        alt = QHBoxLayout()
        alt.setSpacing(6)
        alt.addWidget(QLabel("Yazici"))
        self.cmb_yazici = QComboBox()
        yz = yazicilar()
        self.cmb_yazici.addItems(yz)
        if self.ayar.get("yazici") in yz:
            self.cmb_yazici.setCurrentText(self.ayar["yazici"])
        elif yz:
            for i, ad in enumerate(yz):
                if "argox" in ad.lower():
                    self.cmb_yazici.setCurrentIndex(i)
                    break
        self.cmb_yazici.setMinimumWidth(200)
        alt.addWidget(self.cmb_yazici, 1)
        self.cmb_mod = QComboBox()
        self.cmb_mod.addItems(["ZPL ham (PPLZ)", "Surucu (GDI)"])
        alt.addWidget(self.cmb_mod)
        root.addLayout(alt)

        btn = QHBoxLayout()
        btn.setSpacing(6)
        b_axpx = QPushButton("AXPX uret")
        b_axpx.setObjectName("birincil")
        b_axpx.clicked.connect(self.axpx_uret)
        btn.addWidget(b_axpx)
        b_ac = QPushButton("Klasoru ac")
        b_ac.clicked.connect(self._klasor_ac)
        btn.addWidget(b_ac)
        b_prn = QPushButton("PRN kaydet")
        b_prn.clicked.connect(self.prn)
        btn.addWidget(b_prn)
        b_csv = QPushButton("CSV")
        b_csv.clicked.connect(self.csv)
        btn.addWidget(b_csv)
        b_yaz = QPushButton("Yazdir")
        b_yaz.clicked.connect(self.yazdir)
        btn.addWidget(b_yaz)
        btn.addStretch()
        b_kapat = QPushButton("Kapat")
        b_kapat.clicked.connect(self.accept)
        btn.addWidget(b_kapat)
        root.addLayout(btn)

    def _sablonlari_doldur(self, sec: str = ""):
        onceki = sec or (self.cmb_sablon.currentData() or "")
        self.cmb_sablon.blockSignals(True)
        self.cmb_sablon.clear()
        for p in sablonlar():
            self.cmb_sablon.addItem(p.name, str(p))
        hedef = ""
        if onceki and self.cmb_sablon.findData(onceki) >= 0:
            hedef = onceki
        if not hedef:
            vars_ = varsayilan_sablon()
            if vars_:
                hedef = str(vars_)
        if hedef:
            i = self.cmb_sablon.findData(hedef)
            if i >= 0:
                self.cmb_sablon.setCurrentIndex(i)
        self.cmb_sablon.blockSignals(False)
        self._sablon_degisti()

    def _sablon_degisti(self, *_):
        yol = self.cmb_sablon.currentData()
        self.sablon_yolu = yol
        self.sablon = sablon_oku(yol) if yol else None
        if self.sablon:
            w, h = sablon_olcusu(self.sablon)
            self.ayar["genislik_mm"] = w
            self.ayar["yukseklik_mm"] = h
            self.lbl_olcu.setText(f"{w:.0f} x {h:.0f} mm")
            sablon_ayarla(self.cmb_sablon.currentText())
        else:
            self.lbl_olcu.setText("sablon yok")
        self._onizleme_yenile()

    def _sablon_ekle(self):
        yol, _ = QFileDialog.getOpenFileName(
            self, "ArgoDesigner sablonu sec", "", "ArgoDesigner (*.axpx);;Tum (*.*)"
        )
        if not yol:
            return
        ok, msg, hedef = sablon_kopyala(yol)
        if not ok:
            QMessageBox.warning(self, "Sablon", msg)
            return
        sablon_ayarla(Path(hedef).name)
        self._sablonlari_doldur(hedef)
        QMessageBox.information(
            self, "Sablon", f"{msg}\n\nSablon secildi ve onizleme yenilendi."
        )

    def _sablon_yenile(self):
        """Klasordeki sablonlari yeniden tarar, secili sablonu korur."""
        self._sablonlari_doldur()
        QMessageBox.information(
            self, "Sablon",
            f"{self.cmb_sablon.count()} sablon bulundu.\nSecili: {self.cmb_sablon.currentText()}",
        )

    def _yukle(self):
        self.etiketler = urun_etiketleri(self.urun_id, 1)
        self.tablo.setRowCount(len(self.etiketler))
        for i, e in enumerate(self.etiketler):
            self.tablo.setItem(i, 0, QTableWidgetItem(e.beden or "Tek urun"))
            self.tablo.setItem(i, 1, QTableWidgetItem(e.barkod))
            sp = QSpinBox()
            sp.setRange(1, 999)
            sp.setValue(int(e.adet))
            sp.valueChanged.connect(lambda v, idx=i: self._adet(idx, v))
            self.tablo.setCellWidget(i, 2, sp)
        if self.etiketler:
            self.tablo.selectRow(0)
        self._onizleme_yenile()

    def _adet(self, idx: int, v: int):
        if 0 <= idx < len(self.etiketler):
            self.etiketler[idx].adet = max(1, int(v))

    def _secili(self) -> Etiket | None:
        r = self.tablo.currentRow()
        if 0 <= r < len(self.etiketler):
            return self.etiketler[r]
        return self.etiketler[0] if self.etiketler else None

    def _onizleme_yenile(self):
        e = self._secili()
        if not e:
            self.onizleme.setText("Etiket verisi yok")
            return
        px_mm = 6.0
        w = int(self.ayar.get("genislik_mm", 30) * px_mm)
        h = int(self.ayar.get("yukseklik_mm", 40) * px_mm)
        pix = QPixmap(w, h)
        pix.fill(QColor("white"))
        qp = QPainter(pix)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        qp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        etiket_ciz(qp, e, self.ayar, px_mm)
        qp.end()
        self.onizleme.setPixmap(pix)
        toplam = sum(x.adet for x in self.etiketler)
        self.lbl_bilgi.setText(
            f"{len(self.etiketler)} varyant · toplam {toplam} etiket · "
            f"{self.ayar.get('genislik_mm', 30):.0f}x{self.ayar.get('yukseklik_mm', 40):.0f} mm"
        )

    def axpx_uret(self):
        if not self.etiketler:
            QMessageBox.information(self, "Etiket", "Uretilecek etiket yok.")
            return
        if not self.sablon_yolu:
            QMessageBox.warning(self, "Sablon", "Once bir .axpx sablonu secin.")
            return
        ok, sonuc, dosyalar = etiketler_uret(self.etiketler, self.sablon_yolu)
        if ok:
            QMessageBox.information(
                self, "AXPX",
                f"{len(dosyalar)} dosya uretildi:\n{sonuc}\n\n"
                "Dosyalari ArgoDesigner/ArgoBar ile acip yazdirabilirsiniz.",
            )
            self._son_klasor = sonuc
        else:
            QMessageBox.warning(self, "Hata", sonuc)

    def _klasor_ac(self):
        yol = getattr(self, "_son_klasor", "")
        if not yol or not os.path.isdir(yol):
            QMessageBox.information(self, "Klasor", "Once AXPX uretin.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(yol)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", yol])
            else:
                subprocess.Popen(["xdg-open", yol])
        except Exception as e:
            log_error("Klasor ac", e, __file__, "_klasor_ac")

    def _guncel_ayar(self) -> dict:
        a = dict(self.ayar)
        a["yazici"] = self.cmb_yazici.currentText()
        return a

    def yazdir(self):
        if not self.etiketler:
            QMessageBox.information(self, "Etiket", "Yazdirilacak etiket yok.")
            return
        yazici = self.cmb_yazici.currentText().strip()
        if not yazici:
            QMessageBox.warning(self, "Yazici", "Yazici secilmedi.")
            return
        a = self._guncel_ayar()
        if self.cmb_mod.currentIndex() == 0:
            ok, msg = ham_yazdir(yazici, zpl_olustur(self.etiketler, a))
        else:
            ok, msg = self._gdi_yazdir(yazici, a)
        if ok:
            etiket_ayarlari_kaydet(yazici=yazici)
            QMessageBox.information(self, "Etiket", msg)
        else:
            QMessageBox.warning(self, "Hata", msg)

    def _gdi_yazdir(self, yazici: str, a: dict, cikti: str = "") -> tuple[bool, str]:
        try:
            from PyQt6.QtCore import QMarginsF, QSizeF
            from PyQt6.QtGui import QPageLayout, QPageSize

            bilgi = QPrinterInfo.printerInfo(yazici)
            if bilgi.isNull():
                return False, f"Yazici bulunamadi: {yazici}"
            pr = QPrinter(bilgi, QPrinter.PrinterMode.HighResolution)
            pr.setResolution(int(a["dpi"]))
            if cikti:
                pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                pr.setOutputFileName(cikti)
            sayfa = QPageSize(
                QSizeF(float(a["genislik_mm"]), float(a["yukseklik_mm"])),
                QPageSize.Unit.Millimeter,
                "Etiket",
                QPageSize.SizeMatchPolicy.ExactMatch,
            )
            pr.setPageLayout(
                QPageLayout(
                    sayfa, QPageLayout.Orientation.Portrait,
                    QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter,
                )
            )
            pr.setFullPage(True)
            qp = QPainter()
            if not qp.begin(pr):
                return False, "Yazici baslatilamadi"
            try:
                px_mm = pr.resolution() / 25.4
                ilk = True
                for e in self.etiketler:
                    for _ in range(max(1, int(e.adet))):
                        if not ilk:
                            pr.newPage()
                        etiket_ciz(qp, e, a, px_mm, cerceve=False)
                        ilk = False
            finally:
                qp.end()
            return True, f"{sum(x.adet for x in self.etiketler)} etiket gonderildi: {yazici}"
        except Exception as e:
            log_error("GDI yazdirma", e, __file__, "_gdi_yazdir")
            return False, str(e)

    def prn(self):
        if not self.etiketler:
            QMessageBox.information(self, "Etiket", "Etiket yok.")
            return
        ok, yol = prn_kaydet(zpl_olustur(self.etiketler, self._guncel_ayar()), "etiket")
        if ok:
            QMessageBox.information(self, "PRN", f"Kaydedildi:\n{yol}")
        else:
            QMessageBox.warning(self, "Hata", yol)

    def csv(self):
        if not self.etiketler:
            QMessageBox.information(self, "Etiket", "Etiket yok.")
            return
        ok, yol = csv_kaydet(self.etiketler, "etiket")
        if ok:
            QMessageBox.information(self, "CSV", f"Kaydedildi:\n{yol}")
        else:
            QMessageBox.warning(self, "Hata", yol)
