# -*- coding: utf-8 -*-
"""
Yonetim paneli - Urun, stok, kanallar, raporlar
"""

import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QLineEdit, QComboBox,
    QFileDialog, QGridLayout, QGroupBox, QScrollArea, QMessageBox, QHeaderView, QAbstractItemView,
    QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit,
    QDialogButtonBox, QTabWidget, QMenu, QInputDialog,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QPixmap
from ui.tema import BG, PANEL, PANEL_2, BORDER, BORDER_2, ACCENT, ACCENT_H, TEXT, TEXT_2, MUTED, OK, DANGER, WARN, btn_qss, kontrol_qss, tablo_qss

from core.urun_servis import (
    urunleri_listele, kategorileri_listele, wix_csv_aktar, urun_sayisi,
    urun_getir, urun_ekle, urun_guncelle, stok_duzelt, kategori_getir_veya_olustur,
    kritik_stok_listesi,
)
try:
    from core.urun_servis import (
        urun_sil, urun_gorsel_ata, urun_cogalt, varyant_ekle, varyantlari_listele,
        barkod_yenile_onayli, barkod_uyumsuz_liste, barkod_toplu_duzelt,
        barkod_stok_uyumlu_mu, barkodlari_yeni_formata_cevir, varyantlari_listele, varyant_ekle,
        varyant_sil, barkod_olustur_toplu,
    )
except ImportError:
    def urun_sil(urun_id, kalici=False):
        return False, "urun_sil eksik — core/urun_servis.py guncelleyin"
    def urun_gorsel_ata(urun_id, kaynak_yol):
        return False, "urun_gorsel_ata eksik"
    def urun_cogalt(*a, **k):
        return False, "urun_cogalt eksik"
    def varyant_ekle(*a, **k):
        return False, "varyant_ekle eksik"
    def varyantlari_listele(*a, **k):
        return []
    def varyant_sil(*a, **k):
        return False, "varyant_sil eksik — core/urun_servis.py guncelleyin"
    def barkod_yenile_onayli(*a, **k):
        return False, "barkod_yenile eksik"
    def barkod_uyumsuz_liste():
        return []
    def barkod_toplu_duzelt(*a, **k):
        return {"ok": False}
    def barkod_stok_uyumlu_mu(*a, **k):
        return True
    def barkodlari_yeni_formata_cevir():
        return {"ok": False, "mesaj": "guncelle urun_servis"}
    def barkod_olustur_toplu(urun_ids=None):
        return {"ok": False, "mesaj": "barkod_olustur_toplu eksik — core/urun_servis.py guncelleyin"}
try:
    from core.urun_servis import ayni_isim_gruplari, urunleri_birlestir
except ImportError:
    def ayni_isim_gruplari(min_adet=2):
        return []
    def urunleri_birlestir(ana_id, diger_idler):
        return {"ok": False, "mesaj": "birlestir eksik"}
from core.rapor_servis import gun_sonu_excel, stok_listesi_excel, stok_excel_yukle, stok_sablon_excel
from core.gorsel_servis import gorselleri_esle, gorsel_klasoru
from core.logger import log_error, log_info
from ui.kanal_sayfalari import KanalStokSayfasi, ApiAyarSayfasi, SatisRaporSayfasi
from core.kanal_servis import bekleyen_hatirlatmalar
from ui.sistem_sayfalari import YedekSayfasi, SayimSayfasi, KullaniciSayfasi, SistemSayfasi
from ui.personel_sayfasi import PersonelRaporSayfasi
from ui.gun_sonlari_sayfasi import GunSonlariSayfasi


def _gbtn(variant: str = "ikincil") -> str:
    return btn_qss(variant=variant)


def _gctrl() -> str:
    return kontrol_qss()


def _gtablo() -> str:
    return tablo_qss()


class UrunFormDialog(QDialog):
    def __init__(self, parent=None, urun_id=None):
        super().__init__(parent)
        self.urun_id = urun_id
        self._bekleyen_gorsel = None
        self._gorsel_yolu = ""
        self.setWindowTitle("Urun Duzenle" if urun_id else "Yeni Urun")
        self.setMinimumWidth(780)
        self.resize(820, 560)
        self._ui()
        if urun_id:
            self._doldur()

    def _ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        ust = QHBoxLayout()
        ust.setSpacing(16)

        # ---- SOL: ad → marka + aciklama + foto ----
        sol = QFormLayout()
        sol.setSpacing(8)
        self.ad = QLineEdit()
        self.stok_kodu = QLineEdit()
        self.stok_kodu.setPlaceholderText("Bos birakilirsa otomatik")
        self.barkod = QLineEdit()
        self.barkod.setPlaceholderText("Bos birakilirsa otomatik KZM-...")
        self.kategori = QComboBox()
        self.kategori.setEditable(True)
        for k in kategorileri_listele():
            self.kategori.addItem(k["ad"], k["id"])
        self.marka = QLineEdit()
        self.marka.setText("KOZMOSIZE")
        self.aciklama = QTextEdit()
        self.aciklama.setMinimumHeight(80)
        self.aciklama.setMaximumHeight(120)
        sol.addRow("Urun adi *", self.ad)
        sol.addRow("Stok kodu", self.stok_kodu)
        sol.addRow("Barkod", self.barkod)
        sol.addRow("Kategori", self.kategori)
        sol.addRow("Marka", self.marka)
        sol.addRow("Aciklama", self.aciklama)

        gorsel_row = QHBoxLayout()
        self.lbl_gorsel = QLabel("Foto yok")
        self.lbl_gorsel.setFixedSize(100, 100)
        self.lbl_gorsel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_gorsel.setStyleSheet(
            "background:#080808; border:1px solid #2a1a1a; color:#8a7a7a; font-size:11px;"
        )
        gorsel_row.addWidget(self.lbl_gorsel)
        gbtns = QVBoxLayout()
        btn_foto = QPushButton("Fotograf sec")
        btn_foto.setObjectName("birincil")
        btn_foto.clicked.connect(self._foto_sec)
        gbtns.addWidget(btn_foto)
        btn_foto_temiz = QPushButton("Fotoyu kaldir")
        btn_foto_temiz.setObjectName("ikincil")
        btn_foto_temiz.clicked.connect(self._foto_temizle)
        gbtns.addWidget(btn_foto_temiz)
        gbtns.addStretch()
        gorsel_row.addLayout(gbtns)
        gorsel_row.addStretch()
        sol.addRow("Fotograf", gorsel_row)
        self._gorsel_yolu = ""
        # gizli alanlar (kayit icin varsayilan)
        self.beden = QLineEdit()
        self.beden.hide()
        self.renk = QLineEdit()
        self.renk.hide()

        # ---- SAG: fiyat + stok kanallari ----
        sag = QFormLayout()
        sag.setSpacing(8)
        self.alis = QDoubleSpinBox()
        self.alis.setRange(0, 9999)
        self.alis.setDecimals(0)
        self.satis = QDoubleSpinBox()
        self.satis.setRange(0, 9999)
        self.satis.setDecimals(0)
        self.stok = QSpinBox()
        self.stok.setRange(0, 9999)
        self.kritik = QSpinBox()
        self.kritik.setRange(0, 9999)
        self.kritik.setValue(3)
        self.wix = QSpinBox()
        self.wix.setRange(0, 9999)
        self.etsy = QSpinBox()
        self.etsy.setRange(0, 9999)
        self.trendyol = QSpinBox()
        self.trendyol.setRange(0, 9999)
        sag.addRow("Alis fiyati", self.alis)
        sag.addRow("Satis fiyati", self.satis)
        sag.addRow("Magaza stok", self.stok)
        sag.addRow("Kritik stok", self.kritik)
        sag.addRow("Wix stok", self.wix)
        sag.addRow("Etsy stok", self.etsy)
        sag.addRow("Trendyol stok", self.trendyol)
        for kutu in (self.alis, self.satis, self.stok, self.kritik, self.wix, self.etsy, self.trendyol):
            kutu.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        ust.addLayout(sol, 3)
        ust.addLayout(sag, 2)
        root.addLayout(ust)

        # ---- ALT: varyant listesi tam genislik ----
        var_lbl = QLabel("Varyantlar (beden / barkod / adet / kanallar)")
        var_lbl.setStyleSheet("color:#e0e0e0; font-weight:600; font-size:12px;")
        root.addWidget(var_lbl)
        self.var_tablo = QTableWidget(0, 6)
        self.var_tablo.setHorizontalHeaderLabels(
            ["Beden", "Barkod", "Adet", "Wix", "Etsy", "Trendyol"]
        )
        self.var_tablo.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.var_tablo.setMinimumHeight(160)
        self.var_tablo.setAlternatingRowColors(True)
        root.addWidget(self.var_tablo, 1)

        var_btn_row = QHBoxLayout()
        self.btn_var_ekle = QPushButton("Varyant ekle")
        self.btn_var_ekle.setObjectName("ikincil")
        self.btn_var_ekle.clicked.connect(self._form_varyant_ekle)
        var_btn_row.addWidget(self.btn_var_ekle)
        self.btn_var_sil = QPushButton("Varyant sil")
        self.btn_var_sil.setObjectName("danger")
        self.btn_var_sil.clicked.connect(self._form_varyant_sil)
        var_btn_row.addWidget(self.btn_var_sil)
        self.btn_var_kaydet = QPushButton("Varyantlari kaydet")
        self.btn_var_kaydet.setObjectName("ok")
        self.btn_var_kaydet.clicked.connect(self._form_varyant_kaydet)
        var_btn_row.addWidget(self.btn_var_kaydet)
        self.btn_etiket = QPushButton("Barkod etiketi")
        self.btn_etiket.setObjectName("ikincil")
        self.btn_etiket.clicked.connect(self._etiket_ac)
        var_btn_row.addWidget(self.btn_etiket)
        var_btn_row.addStretch()
        root.addLayout(var_btn_row)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.kaydet)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _doldur(self):
        u = urun_getir(self.urun_id)
        if not u:
            return
        self.ad.setText(u.get("ad") or "")
        self.stok_kodu.setText(u.get("stok_kodu") or "")
        self.barkod.setText(u.get("barkod") or "")
        self.marka.setText(u.get("marka") or "")
        self.beden.setText(u.get("beden") or "")
        self.renk.setText(u.get("renk") or "")
        self.alis.setValue(float(u.get("alis_fiyati") or 0))
        self.satis.setValue(float(u.get("satis_fiyati") or 0))
        self.stok.setValue(int(u.get("stok_adedi") or 0))
        self.kritik.setValue(int(u.get("kritik_stok") or 3))
        if hasattr(self, "wix"):
            self.wix.setValue(int(u.get("wix_stok") or 0))
        self.etsy.setValue(int(u.get("etsy_stok") or 0))
        self.trendyol.setValue(int(u.get("trendyol_stok") or 0))
        self.aciklama.setPlainText(u.get("aciklama") or "")
        kat = u.get("kategori_adi") or ""
        idx = self.kategori.findText(kat)
        if idx >= 0:
            self.kategori.setCurrentIndex(idx)
        elif kat:
            self.kategori.setEditText(kat)
        yol = u.get("gorsel_yolu") or ""
        if not yol:
            try:
                from core.gorsel_servis import gorsel_yolu_bul
                yol = gorsel_yolu_bul(u.get("stok_kodu") or "", u.get("barkod") or "") or ""
            except Exception:
                yol = ""
        self._gorsel_goster(yol)
        self._varyantlari_yukle()
        self._varyant_kilidi_uygula()

    def _gorsel_goster(self, yol: str):
        self._gorsel_yolu = yol or ""
        self.lbl_gorsel.setPixmap(QPixmap())
        if yol:
            pix = QPixmap(yol)
            if not pix.isNull():
                self.lbl_gorsel.setPixmap(
                    pix.scaled(
                        96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.lbl_gorsel.setText("")
                return
        self.lbl_gorsel.setText("Foto yok")

    def _foto_sec(self):
        yol, _ = QFileDialog.getOpenFileName(
            self, "Urun fotografi sec", "",
            "Resimler (*.png *.jpg *.jpeg *.webp *.gif *.bmp);;Tum (*.*)"
        )
        if not yol:
            return
        if self.urun_id:
            ok, msg = urun_gorsel_ata(self.urun_id, yol)
            if ok:
                self._gorsel_goster(msg)
            else:
                QMessageBox.warning(self, "Hata", msg)
        else:
            # yeni urun — once kaydet, sonra ata; simdilik onizleme
            self._gorsel_goster(yol)
            self._bekleyen_gorsel = yol

    def _foto_temizle(self):
        self._gorsel_yolu = ""
        self._bekleyen_gorsel = None
        self.lbl_gorsel.setPixmap(QPixmap())
        self.lbl_gorsel.setText("Foto yok")
        if self.urun_id:
            urun_guncelle(self.urun_id, gorsel_yolu="")

    def _varyantlari_yukle(self):
        if not hasattr(self, "var_tablo"):
            return
        self.var_tablo.setRowCount(0)
        if not self.urun_id:
            return
        try:
            for v in varyantlari_listele(self.urun_id):
                if v.get("id") == self.urun_id:
                    continue  # ana satiri atla — sadece alt varyantlar
                r = self.var_tablo.rowCount()
                self.var_tablo.insertRow(r)
                self.var_tablo.setItem(r, 0, QTableWidgetItem(v.get("beden") or ""))
                self.var_tablo.setItem(r, 1, QTableWidgetItem(v.get("barkod") or ""))
                self.var_tablo.setItem(r, 2, QTableWidgetItem(str(int(v.get("stok_adedi") or 0))))
                self.var_tablo.setItem(r, 3, QTableWidgetItem(str(int(v.get("wix_stok") or 0))))
                self.var_tablo.setItem(r, 4, QTableWidgetItem(str(int(v.get("etsy_stok") or 0))))
                self.var_tablo.setItem(r, 5, QTableWidgetItem(str(int(v.get("trendyol_stok") or 0))))
                # id gizle
                self.var_tablo.item(r, 0).setData(Qt.ItemDataRole.UserRole, v.get("id"))
        except Exception as e:
            log_error("Varyant yukle form", e, __file__, "_varyantlari_yukle")

    def _etiket_ac(self):
        if not self.urun_id:
            QMessageBox.information(
                self, "Etiket", "Once urunu kaydedin, sonra barkod etiketi olusturun."
            )
            return
        try:
            from ui.etiket_dialog import EtiketDialog

            EtiketDialog(self, self.urun_id).exec()
        except Exception as e:
            log_error("Etiket penceresi", e, __file__, "_etiket_ac")
            QMessageBox.warning(self, "Hata", str(e))

    def _varyant_kilidi_uygula(self):
        if not hasattr(self, "var_tablo"):
            return
        if self.urun_id and self.var_tablo.rowCount() > 0:
            self.stok.setEnabled(False)
            self.stok.setToolTip("Varyantli urun: ana adet varyant toplamindan otomatik hesaplanir")
        else:
            self.stok.setEnabled(True)
            self.stok.setToolTip("")

    def _form_varyant_ekle(self):
        if not self.urun_id:
            QMessageBox.information(self, "Kaydet", "Once urunu kaydedin, sonra varyant ekleyin")
            return
        beden, ok = QInputDialog.getText(self, "Varyant", "Beden (S/M/L/XL):")
        if not ok:
            return
        ok2, msg = varyant_ekle(self.urun_id, beden=beden.strip(), stok_adedi=0)
        if ok2:
            self._varyantlari_yukle()
            QMessageBox.information(self, "Tamam", msg)
        else:
            QMessageBox.warning(self, "Hata", msg)

    def _form_varyant_sil(self):
        if not self.urun_id:
            return
        row = self.var_tablo.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Uyari", "Silinecek varyanti secin")
            return
        it0 = self.var_tablo.item(row, 0)
        vid = it0.data(Qt.ItemDataRole.UserRole) if it0 else None
        if not vid:
            QMessageBox.warning(self, "Uyari", "Varyant ID bulunamadi")
            return
        beden = it0.text() if it0 else "?"
        cevap = QMessageBox.question(
            self, "Varyant Sil",
            f"'{beden}' varyanti listeden kaldirilsin mi?\n"
            "Satis gecmisi korunur, sadece listeden cikarilir.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if cevap != QMessageBox.StandardButton.Yes:
            return
        ok, msg = varyant_sil(int(vid), self.urun_id)
        if ok:
            self._varyantlari_yukle()
            QMessageBox.information(self, "Tamam", msg)
        else:
            QMessageBox.warning(self, "Hata", msg)

    def _varyant_stoklarini_yaz(self) -> list:
        """Tablodaki varyantlari kaydeder; hata mesajlarinin listesini dondurur."""
        hatalar = []
        if not self.urun_id:
            return hatalar
        adet_degisti = False
        for r in range(self.var_tablo.rowCount()):
            it0 = self.var_tablo.item(r, 0)
            vid = it0.data(Qt.ItemDataRole.UserRole) if it0 else None
            if not vid:
                continue
            beden = (self.var_tablo.item(r, 0).text() if self.var_tablo.item(r, 0) else "")
            barkod = (self.var_tablo.item(r, 1).text() if self.var_tablo.item(r, 1) else "")
            def _sayi(kolon):
                it = self.var_tablo.item(r, kolon)
                return int((it.text() or "0").strip() or "0") if it else 0
            try:
                adet = _sayi(2)
                wix = _sayi(3)
                etsy = _sayi(4)
                ty = _sayi(5)
            except ValueError:
                hatalar.append(f"{beden or '?'}: gecersiz sayi girisi")
                continue
            once = urun_getir(int(vid)) or {}
            ok_u, msg_u = urun_guncelle(
                int(vid),
                beden=beden,
                barkod=barkod.strip() or None,
                wix_stok=wix,
                etsy_stok=etsy,
                trendyol_stok=ty,
            )
            if not ok_u:
                hatalar.append(f"{beden or '?'}: {msg_u}")
                continue
            ok_s, msg_s = stok_duzelt(int(vid), yeni_stok=adet, aciklama="Form varyant", kanal="magaza")
            if not ok_s:
                hatalar.append(f"{beden or '?'}: {msg_s}")
                continue
            if int(once.get("stok_adedi") or 0) != adet:
                adet_degisti = True
        if adet_degisti:
            ana = urun_getir(self.urun_id)
            if ana:
                self.stok.setValue(int(ana.get("stok_adedi") or 0))
        return hatalar

    def _form_varyant_kaydet(self):
        if not self.urun_id:
            return
        try:
            hatalar = self._varyant_stoklarini_yaz()
            if hatalar:
                QMessageBox.warning(
                    self, "Kaydedilemedi",
                    "Bazi varyantlar kaydedilemedi:\n" + "\n".join(hatalar),
                )
            else:
                QMessageBox.information(
                    self, "Tamam",
                    f"Varyantlar guncellendi. Magaza stok: {self.stok.value()}",
                )
            self._varyantlari_yukle()
            self._varyant_kilidi_uygula()
        except Exception as e:
            log_error("Varyant kaydet form", e, __file__, "_form_varyant_kaydet")
            QMessageBox.warning(self, "Hata", str(e))

    def kaydet(self):
        try:
            ad = self.ad.text().strip()
            if not ad:
                QMessageBox.warning(self, "Eksik", "Urun adi zorunlu")
                return
            kat_text = self.kategori.currentText().strip() or "Genel"
            kat_id = kategori_getir_veya_olustur(kat_text)

            if self.urun_id and self.var_tablo.rowCount():
                self._varyant_stoklarini_yaz()

            if self.urun_id:
                ok, msg = urun_guncelle(
                    self.urun_id,
                    ad=ad,
                    stok_kodu=self.stok_kodu.text().strip() or None,
                    barkod=self.barkod.text().strip() or None,
                    kategori_id=kat_id,
                    marka=self.marka.text().strip(),
                    beden=self.beden.text().strip(),
                    renk=self.renk.text().strip(),
                    alis_fiyati=self.alis.value(),
                    satis_fiyati=self.satis.value(),
                    kritik_stok=self.kritik.value(),
                    etsy_stok=self.etsy.value(),
                    trendyol_stok=self.trendyol.value(),
                    wix_stok=getattr(self, "wix", None).value() if hasattr(self, "wix") else 0,
                    aciklama=self.aciklama.toPlainText().strip(),
                )
                if ok:
                    if self.var_tablo.rowCount() > 0:
                        ana2 = urun_getir(self.urun_id) or {}
                        self.stok.setValue(int(ana2.get("stok_adedi") or 0))
                    else:
                        stok_duzelt(
                            self.urun_id,
                            yeni_stok=self.stok.value(),
                            aciklama="Formdan stok",
                            kanal="magaza",
                        )
            else:
                ok, msg = urun_ekle(
                    stok_kodu=self.stok_kodu.text().strip(),
                    ad=ad,
                    barkod=self.barkod.text().strip() or None,
                    kategori_id=kat_id,
                    marka=self.marka.text().strip(),
                    beden=self.beden.text().strip(),
                    renk=self.renk.text().strip(),
                    alis_fiyati=self.alis.value(),
                    satis_fiyati=self.satis.value(),
                    stok_adedi=self.stok.value(),
                    kritik_stok=self.kritik.value(),
                    aciklama=self.aciklama.toPlainText().strip(),
                )
                if ok:
                    from core.database import get_connection
                    c = get_connection()
                    cur = c.cursor()
                    cur.execute(
                        "SELECT id FROM urunler WHERE ad = ? ORDER BY id DESC LIMIT 1",
                        (ad,),
                    )
                    row = cur.fetchone()
                    c.close()
                    if row:
                        urun_guncelle(
                            row["id"],
                            etsy_stok=self.etsy.value(),
                            trendyol_stok=self.trendyol.value(),
                        )
                        if getattr(self, "_bekleyen_gorsel", None):
                            urun_gorsel_ata(row["id"], self._bekleyen_gorsel)

            if ok:
                if not self.urun_id:
                    from core.log_servis import islem_kaydet
                    islem_kaydet(
                        getattr(self.parent(), "kullanici_adi", "") or "-",
                        "urun_giris",
                        f"{ad} / {self.stok_kodu.text().strip()}",
                    )
                ekstra = ""
                if self.urun_id:
                    u2 = urun_getir(self.urun_id)
                    if u2:
                        sk = u2.get("stok_kodu") or ""
                        bk = u2.get("barkod") or ""
                        if not bk or not barkod_stok_uyumlu_mu(sk, bk):
                            from core.database import barkod_stoktan
                            oneri = barkod_stoktan(sk)
                            metin = (
                                "Barkod sistem formatinda degil veya yok.\n"
                                "Mevcut: {bk}\nOneri: {oneri}\n\n"
                                "Yeni barkod olusturulsun mu?\n"
                                "(Hayir = eski barkod kalsin)"
                            ).format(bk=bk or "(yok)", oneri=oneri)
                            cevap = QMessageBox.question(
                                self, "Barkod Uyumu", metin,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            )
                            if cevap == QMessageBox.StandardButton.Yes:
                                bok, bmsg = barkod_yenile_onayli(self.urun_id, True)
                                ekstra = "\n" + bmsg
                                if not bok:
                                    QMessageBox.warning(self, "Barkod", bmsg)
                                else:
                                    u3 = urun_getir(self.urun_id)
                                    if u3 and hasattr(self, "barkod"):
                                        self.barkod.setText(u3.get("barkod") or "")
                QMessageBox.information(self, "Tamam", msg + ekstra)
                self.accept()
            else:
                QMessageBox.warning(self, "Hata", msg)
        except Exception as e:
            log_error("Urun form kayit hatasi", e, __file__, "UrunFormDialog.kaydet")
            QMessageBox.critical(self, "Hata", str(e))


class StokDuzeltDialog(QDialog):
    def __init__(self, parent, urun_id, urun_ad):
        super().__init__(parent)
        self.urun_id = urun_id
        self.setWindowTitle(f"Stok: {urun_ad[:40]}")
        self.setMinimumWidth(360)
        form = QFormLayout(self)
        self.kanal = QComboBox()
        self.kanal.addItems(["Magaza", "Wix", "Etsy", "Trendyol"])
        self.mod = QComboBox()
        self.mod.addItems(["Mutlak deger ata", "Ekle (+)", "Cikar (-)"])
        self.miktar = QSpinBox()
        self.miktar.setRange(0, 9999)
        self.miktar.setValue(1)
        self.notu = QLineEdit()
        self.notu.setPlaceholderText("Aciklama")
        form.addRow("Kanal", self.kanal)
        form.addRow("Islem", self.mod)
        form.addRow("Miktar", self.miktar)
        form.addRow("Not", self.notu)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.uygula)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def uygula(self):
        kanal_map = {"Magaza": "magaza", "Wix": "wix", "Etsy": "etsy", "Trendyol": "trendyol"}
        kanal = kanal_map[self.kanal.currentText()]
        miktar = self.miktar.value()
        mod = self.mod.currentIndex()
        if mod == 0:
            ok, msg = stok_duzelt(
                self.urun_id, yeni_stok=miktar, aciklama=self.notu.text(), kanal=kanal
            )
        elif mod == 1:
            ok, msg = stok_duzelt(
                self.urun_id, fark=miktar, aciklama=self.notu.text(), kanal=kanal
            )
        else:
            ok, msg = stok_duzelt(
                self.urun_id, fark=-miktar, aciklama=self.notu.text(), kanal=kanal
            )
        if ok:
            from core.log_servis import islem_kaydet
            islem_kaydet(
                getattr(self.parent(), "kullanici_adi", "") or "-",
                "stok_giris",
                f"{getattr(self, 'urun_ad', '') or ''} / {msg}",
            )
            QMessageBox.information(self, "Tamam", msg)
            self.accept()
        else:
            QMessageBox.warning(self, "Hata", msg)


class VaryantDialog(QDialog):
    def __init__(self, parent, parent_id: int):
        super().__init__(parent)
        self.parent_id = parent_id
        self.setWindowTitle("Varyant Ekle")
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        u = urun_getir(parent_id)
        lay.addWidget(QLabel(f"Ana: {(u or {}).get('stok_kodu')} — {(u or {}).get('ad')}"))
        form = QFormLayout()
        self.beden = QLineEdit()
        self.beden.setPlaceholderText("L, XL, M...")
        self.renk = QLineEdit()
        self.stok = QSpinBox()
        self.stok.setRange(0, 9999)
        self.stok.setValue(0)
        self.stok.setToolTip("0 ise kod atanmaz; stok girilince atanir")
        form.addRow("Beden / varyant eki *", self.beden)
        form.addRow("Renk", self.renk)
        form.addRow("Stok adedi", self.stok)
        lay.addLayout(form)
        lay.addWidget(QLabel("Stok 0: kod yok. Stok > 0: KZM-xxxxL + barkod uretilir."))
        # mevcut varyantlar
        self.liste = QTableWidget(0, 4)
        self.liste.setHorizontalHeaderLabels(["Kod", "Beden", "Stok", "Barkod"])
        self.liste.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for v in varyantlari_listele(parent_id):
            r = self.liste.rowCount()
            self.liste.insertRow(r)
            self.liste.setItem(r, 0, QTableWidgetItem(v.get("stok_kodu") or ""))
            self.liste.setItem(r, 1, QTableWidgetItem(v.get("beden") or ""))
            self.liste.setItem(r, 2, QTableWidgetItem(str(v.get("stok_adedi") or 0)))
            self.liste.setItem(r, 3, QTableWidgetItem(v.get("barkod") or ""))
        lay.addWidget(self.liste)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._kaydet)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _kaydet(self):
        beden = self.beden.text().strip()
        if not beden:
            QMessageBox.warning(self, "Eksik", "Beden / varyant eki zorunlu")
            return
        ok, msg = varyant_ekle(
            self.parent_id, beden=beden, renk=self.renk.text().strip(),
            stok_adedi=self.stok.value(), varyant_eki=beden,
        )
        if ok:
            QMessageBox.information(self, "Tamam", msg)
            self.accept()
        else:
            QMessageBox.warning(self, "Hata", msg)


class YonetimPaneli(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{BG}; color:{TEXT};")
        ana = QVBoxLayout(self)
        ana.setContentsMargins(12, 10, 12, 12)
        self.lbl_aktif = QLabel("Aktif kullanicilar: -")
        self.lbl_aktif.setStyleSheet("background:transparent; color:#c9a66b; font-size:11px;")
        ana.addWidget(self.lbl_aktif)
        self.tabs = QTabWidget()
        # Sekme stilleri global tema (ui/tema.py) ile gelir
        self.tabs.setDocumentMode(True)
        # Urun yonetimi (mevcut ekran)
        self.urun_sayfa = QWidget()
        self._ui_olustur(self.urun_sayfa)
        self.tabs.addTab(self.urun_sayfa, "Urunler")
        self.ana_stok = KanalStokSayfasi("ana", "Ana Stok (Magaza / fiziksel)")
        self.tabs.addTab(self.ana_stok, "Ana Stok")
        self.magaza_stok = KanalStokSayfasi("magaza", "Magaza Stok (fiziksel)")
        self.tabs.addTab(self.magaza_stok, "Magaza")
        self.wix_stok = KanalStokSayfasi("wix", "Wix — satilan urunler")
        self.tabs.addTab(self.wix_stok, "Wix")
        self.etsy_stok = KanalStokSayfasi("etsy", "Etsy — satilan urunler")
        self.tabs.addTab(self.etsy_stok, "Etsy")
        self.ty_stok = KanalStokSayfasi("trendyol", "Trendyol — satilan urunler")
        self.tabs.addTab(self.ty_stok, "Trendyol")
        self.satis_rapor = SatisRaporSayfasi()
        self.tabs.addTab(self.satis_rapor, "Satılanlar")
        self.personel_rapor = PersonelRaporSayfasi()
        self.tabs.addTab(self.personel_rapor, "Personel Raporlari")
        self.api_sayfa = ApiAyarSayfasi()
        self.tabs.addTab(self.api_sayfa, "API Ayarlari")
        self.tabs.addTab(SayimSayfasi(), "Sayim")
        self.tabs.addTab(GunSonlariSayfasi(), "Gun Sonlari")
        self.tabs.addTab(YedekSayfasi(), "Yedek")
        self.tabs.addTab(KullaniciSayfasi(), "Kullanicilar")
        self.tabs.addTab(SistemSayfasi(), "Sistem")
        self.tabs.currentChanged.connect(self._tab_degisti)
        ana.addWidget(self.tabs)
        self._urun_cache = None
        self._cache_zaman = 0.0
        QTimer.singleShot(0, self.yenile)
        self._hatirlatma_gosterildi = False

    def showEvent(self, event):
        super().showEvent(event)
        # Yonetim bolumu her acildiginda yapilmayan isler hatirlatilir;
        # carpı ile o oturum icin kapatilir, program yeniden acilinca tekrar cikar.
        if not self._hatirlatma_gosterildi:
            self._hatirlatma_gosterildi = True
            QTimer.singleShot(400, self._hatirlatma_goster)

    def _hatirlatma_goster(self):
        try:
            satirlar = bekleyen_hatirlatmalar(esik_gun=1)
        except Exception:
            return
        if not satirlar:
            return
        kutu = QDialog(self)
        kutu.setWindowTitle("Yapilmayan isler hatirlatmasi")
        kutu.setModal(True)
        kutu.resize(640, 420)
        v = QVBoxLayout(kutu)
        baslik = QLabel("Bekleyen isler — lutfen kontrol edin")
        baslik.setStyleSheet("font-size:11pt; font-weight:800;")
        v.addWidget(baslik)
        liste = QPlainTextEdit()
        liste.setReadOnly(True)
        liste.setPlainText("\n".join(satirlar))
        v.addWidget(liste, 1)
        ip = QLabel("Bu pencereyi kapattiktan sonra program yeniden acilincada tekrar gosterilir.")
        ip.setStyleSheet("color:#8a8a8a; font-size:9pt;")
        v.addWidget(ip)
        btn = QPushButton("Anladim")
        btn.clicked.connect(kutu.accept)
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(btn)
        v.addLayout(h)
        kutu.exec()

    def _tab_degisti(self, idx):
        w = self.tabs.widget(idx)
        if hasattr(w, "yenile"):
            try:
                w.yenile()
            except Exception:
                pass

    def _ui_olustur(self, host=None):
        layout = QVBoxLayout(host if host is not None else self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        baslik = QLabel("YONETIM  ·  Urunler")
        baslik.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        baslik.setStyleSheet(f"color:{TEXT};")
        layout.addWidget(baslik)

        ust = QHBoxLayout()
        ust.setSpacing(6)
        self.arama = QLineEdit()
        self.arama.setPlaceholderText("Urun adi, stok kodu, barkod veya eski barkod ara...")
        self.arama.setClearButtonEnabled(True)
        self.arama.setMinimumWidth(240)
        self.arama.setStyleSheet(_gctrl())
        self.arama.returnPressed.connect(lambda: self.yenile(yerel=True))
        self._arama_timer = __import__("PyQt6.QtCore", fromlist=["QTimer"]).QTimer(self)
        self._arama_timer.setSingleShot(True)
        self._arama_timer.timeout.connect(lambda: self.yenile(yerel=True))
        self.arama.textChanged.connect(lambda _: self._arama_timer.start(250))
        ust.addWidget(self.arama, 1)

        self.cmb_kategori = QComboBox()
        self.cmb_kategori.setMinimumWidth(140)
        self.cmb_kategori.setStyleSheet(_gctrl())
        self.cmb_kategori.currentIndexChanged.connect(lambda: self.yenile(yerel=True))
        ust.addWidget(self.cmb_kategori)

        btn_ara = QPushButton("Ara")
        btn_ara.setObjectName("birincil")
        btn_ara.clicked.connect(lambda: self.yenile(yerel=True))
        ust.addWidget(btn_ara)
        ust.addStretch()
        self.lbl_sayac = QLabel("0 urun")
        self.lbl_sayac.setStyleSheet(f"color:{MUTED};")
        ust.addWidget(self.lbl_sayac)
        layout.addLayout(ust)

        # Ana ürün eylemleri ve toplu araçlar ayrı satırlarda: dar ekranda sıkışmaz.
        aksiyon = QHBoxLayout()
        aksiyon.setSpacing(8)
        for etiket, islem, stil in (
            ("Yeni Ürün", self.yeni_urun, "ok"),
            ("Düzenle", self.duzenle_urun, "ikincil"),
            ("Ürünü Sil", self.urun_sil_ui, "tehlike"),
            ("Ürünü Çoğalt", self.urun_cogalt_ui, "ikincil"),
            ("Yenile", self._sunucu_yenile, "ikincil"),
            ("Excel çıktı", self.stok_excel, "ikincil"),
        ):
            btn = QPushButton(etiket)
            btn.setObjectName(stil)
            btn.setStyleSheet(btn_qss(stil) + "QPushButton { font-size:14px; letter-spacing:0px; }")
            btn.clicked.connect(islem)
            aksiyon.addWidget(btn)
        aksiyon.addStretch()
        layout.addLayout(aksiyon)

        araclar = QHBoxLayout()
        araclar.setSpacing(8)
        for etiket, secenekler in (
            ("İçe aktar (Excel/CSV)", (
                ("Wix CSV", self.csv_aktar),
                ("Excel stok", self.stok_excel_yukle_ui),
            )),
        ):
            btn = QPushButton(etiket)
            btn.setObjectName("ikincil")
            btn.setStyleSheet(btn_qss() + "QPushButton { font-size:14px; letter-spacing:0px; }")
            menu = QMenu(btn)
            menu.setStyleSheet(
                f"QMenu {{ background:{PANEL}; color:{TEXT}; font-size:14px; }}"
                "QMenu::item { padding:10px 20px; }"
                f"QMenu::item:selected {{ background:{ACCENT}; }}"
            )
            for ad, islem in secenekler:
                menu.addAction(ad).triggered.connect(islem)
            btn.setMenu(menu)
            araclar.addWidget(btn)
        btn_barkod = QPushButton("Barkod Oluştur")
        btn_barkod.setObjectName("ikincil")
        btn_barkod.setStyleSheet(btn_qss() + "QPushButton { font-size:14px; letter-spacing:0px; }")
        btn_barkod.clicked.connect(self.barkod_olustur_ui)
        araclar.addWidget(btn_barkod)
        btn_denetci = QPushButton("Denetci")
        btn_denetci.setObjectName("ikincil")
        btn_denetci.setStyleSheet(btn_qss() + "QPushButton { font-size:14px; letter-spacing:0px; }")
        btn_denetci.clicked.connect(self.denetci_ac)
        araclar.addWidget(btn_denetci)
        btn_kritik = QPushButton("Kritik Liste")
        btn_kritik.setObjectName("ikincil")
        btn_kritik.setStyleSheet(btn_qss() + "QPushButton { font-size:14px; letter-spacing:0px; }")
        btn_kritik.clicked.connect(self.kritik_stok_goster)
        araclar.addWidget(btn_kritik)
        araclar.addStretch()
        layout.addLayout(araclar)
        # Varyantlar Düzenle formunda; Gün Sonu Excel mağaza ekranında kalır.

        self.tablo = QTableWidget()
        self.tablo.setColumnCount(12)
        self.tablo.setHorizontalHeaderLabels([
            "ID", "Stok Kodu", "Barkod", "Urun Adi", "Kategori",
            "Satis", "Magaza", "Wix", "Etsy", "Trendyol", "Kritik", "Beden",
        ])
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tablo.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tablo.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.setShowGrid(True)
        self.tablo.doubleClicked.connect(self.duzenle_urun)
        header = self.tablo.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(56)
        header.setStretchLastSection(False)
        # Urun Adi (3) esneyerek kalan alani doldurur; tablo yatay kaydirmaya ihtiyac duymaz
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        # Kolon genislikleri kolon sirasiyla birebir: 0 ID, 1 Stok Kodu, 2 Barkod, 4 Kategori,
        # 5 Satis, 6 Magaza, 7 Wix, 8 Etsy, 9 Trendyol, 10 Kritik, 11 Beden
        for kolon, genislik in ((0, 56), (1, 112), (2, 132), (4, 96),
                                (5, 84), (6, 84), (7, 56), (8, 56),
                                (9, 78), (10, 60), (11, 96)):
            self.tablo.setColumnWidth(kolon, genislik)
        self.tablo.verticalHeader().setDefaultSectionSize(38)
        self.tablo.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tablo.setStyleSheet(_gtablo())
        self.tablo.setAlternatingRowColors(True)
        layout.addWidget(self.tablo)

        alt = QLabel(
            "Etsy / Trendyol stok sutunlari manuel girilebilir. "
            "API baglantisi icin Etsy ve Trendyol API anahtarlariniz hazirsa sonraki adimda eklenir."
        )
        alt.setStyleSheet(f"color: {TEXT_2}; font-size: 12px;")
        alt.setWordWrap(True)
        layout.addWidget(alt)

    def _kategorileri_doldur(self, koru_secim: bool = True):
        """Kategori listesini doldur. Secili kategori korunur (filtre sifirlanmaz)."""
        onceki = self.cmb_kategori.currentData() if koru_secim else None
        self.cmb_kategori.blockSignals(True)
        self.cmb_kategori.clear()
        self.cmb_kategori.addItem("Tum Kategoriler", None)
        for k in kategorileri_listele():
            self.cmb_kategori.addItem(k["ad"], k["id"])
        # Onceki secimi geri yukle
        if onceki is not None:
            idx = self.cmb_kategori.findData(onceki)
            if idx >= 0:
                self.cmb_kategori.setCurrentIndex(idx)
            else:
                self.cmb_kategori.setCurrentIndex(0)
        self.cmb_kategori.blockSignals(False)

    def _urun_cache_yukle(self):
        self._urun_cache = urunleri_listele()
        self._cache_zaman = time.time()

    def _urunleri_yerel_filtrele(self, arama: str, kat_id):
        """Onbellekte ad/kod/barkod + kategori filtresi; DB'deki aile mantigini taklit eder."""
        satirlar = self._urun_cache or []
        metin = (arama or "").strip().lower()
        eslesen = set()
        for u in satirlar:
            if metin:
                saman = " ".join(filter(None, [u.get("ad"), u.get("stok_kodu"), u.get("barkod")])).lower()
                b_norm = (u.get("barkod") or "").replace("KZM-", "").replace(" ", "").lower()
                if metin not in saman and metin not in b_norm:
                    continue
            eslesen.add(int(u.get("id") or 0))
            if u.get("parent_id"):
                eslesen.add(int(u["parent_id"]))
        sonuc = []
        for u in satirlar:
            pid = u.get("parent_id")
            if int(u.get("id") or 0) not in eslesen and not (pid and int(pid) in eslesen):
                continue
            if kat_id and int(u.get("kategori_id") or 0) != int(kat_id):
                continue
            sonuc.append(u)
        return sonuc

    def _sunucu_yenile(self):
        """Urunleri yenile: once sunucu senkronu (cek + gonder), sonra tazele."""
        from PyQt6.QtWidgets import QApplication
        try:
            from core.sync_servis import senkronize
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                snc = senkronize()
            finally:
                QApplication.restoreOverrideCursor()
            if isinstance(snc, dict) and snc.get("ok"):
                log_info(
                    f"Sunucu senkronu: +{snc.get('gonderilen', 0)} gonderildi, "
                    f"+{snc.get('alinan', 0)} alindi"
                )
        except Exception as e:
            log_error("Sunucu senkronu", e, __file__, "_sunucu_yenile")
        finally:
            self.yenile(zorla=True)

    def aktif_yenile(self):
        try:
            from core.log_servis import aktif_kullanicilar
            satirlar = aktif_kullanicilar()
            adlar = sorted({(r.get("kullanici") or "").strip() for r in satirlar} - {""})
            self.lbl_aktif.setText("Aktif kullanicilar: " + (" · ".join(adlar) or "-"))
        except Exception:
            pass

    def yenile(self, sessiz: bool = False, yerel: bool = False, zorla: bool = False):
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            self.aktif_yenile()
            yasa = time.time() - self._cache_zaman
            yukle = zorla or self._urun_cache is None or (not yerel and yasa > 60.0)
            if yukle:
                self._urun_cache_yukle()
                self._kategorileri_doldur(koru_secim=True)
            arama = self.arama.text().strip() if hasattr(self, "arama") else ""
            kat_id = self.cmb_kategori.currentData() if hasattr(self, "cmb_kategori") else None
            urunler = self._urunleri_yerel_filtrele(arama, kat_id)
            if not urunler and arama and not yerel:
                # Eski barkod / birlesmis kayit ailesi sadece DB'de bulunur
                urunler = urunleri_listele(arama=arama, kategori_id=kat_id)
            # Ana barkod altinda topla: parent_id olanlari gizle, ana satira varyant ozeti
            cocuklar = {}
            for u in urunler:
                pid = u.get("parent_id")
                if pid:
                    cocuklar.setdefault(int(pid), []).append(u)
            ana_urunler = []
            for u in urunler:
                if u.get("parent_id"):
                    continue
                kids = cocuklar.get(int(u["id"]), [])
                if kids:
                    u = dict(u)
                    u["_varyant_sayisi"] = len(kids)
                    u["_varyant_stok"] = sum(int(k.get("stok_adedi") or 0) for k in kids)
                ana_urunler.append(u)
            urunler = ana_urunler
            self.tablo.clearContents()
            self.tablo.setRowCount(0)
            self.tablo.setRowCount(len(urunler))
            for i, u in enumerate(urunler):
                id_it = QTableWidgetItem(str(u.get("id") or ""))
                id_it.setData(Qt.ItemDataRole.UserRole, int(u.get("id") or 0))
                self.tablo.setItem(i, 0, id_it)
                self.tablo.setItem(i, 1, QTableWidgetItem(u.get("stok_kodu") or ""))
                self.tablo.setItem(i, 2, QTableWidgetItem(u.get("barkod") or ""))
                self.tablo.setItem(i, 3, QTableWidgetItem(u.get("ad") or ""))
                self.tablo.setItem(i, 4, QTableWidgetItem(u.get("kategori_adi") or ""))
                self.tablo.setItem(
                    i, 5, QTableWidgetItem(f"{float(u.get('satis_fiyati') or 0):,.0f}")
                )
                stok = int(u.get("stok_adedi") or 0)
                kritik = int(u.get("kritik_stok") or 0)
                stok_item = QTableWidgetItem(str(stok))
                if stok <= kritik:
                    stok_item.setForeground(QColor(DANGER))
                self.tablo.setItem(i, 6, stok_item)
                self.tablo.setItem(i, 7, QTableWidgetItem(str(int(u.get("wix_stok") or 0))))
                self.tablo.setItem(i, 8, QTableWidgetItem(str(int(u.get("etsy_stok") or 0))))
                self.tablo.setItem(i, 9, QTableWidgetItem(str(int(u.get("trendyol_stok") or 0))))
                self.tablo.setItem(i, 10, QTableWidgetItem(str(kritik)))
                beden_txt = u.get("beden") or ""
                if u.get("_varyant_sayisi"):
                    beden_txt = f"{u['_varyant_sayisi']} varyant / stok {u.get('_varyant_stok', 0)}"
                self.tablo.setItem(i, 11, QTableWidgetItem(beden_txt))
                for col in (5, 6, 7, 8, 9, 10):
                    hucre = self.tablo.item(i, col)
                    if hucre:
                        hucre.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_sayac.setText(f"{len(urunler)} urun  (toplam {urun_sayisi()})")
        except Exception as e:
            log_error("Urun listesi yenilenemedi", e, __file__, "YonetimPaneli.yenile")
            if not sessiz:
                QMessageBox.warning(self, "Hata", f"Liste yenilenemedi.\n{e}")

    def _secili_id(self):
        rows = self.tablo.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.tablo.item(rows[0].row(), 0)
        if not item:
            return None
        try:
            return int(item.data(Qt.ItemDataRole.UserRole))
        except (TypeError, ValueError):
            return None

    def _secili_idler(self) -> list:
        ids = []
        for idx in self.tablo.selectionModel().selectedRows():
            it = self.tablo.item(idx.row(), 0)
            if not it:
                continue
            try:
                uid = it.data(Qt.ItemDataRole.UserRole)
                ids.append(int(uid if uid is not None else it.text()))
            except (TypeError, ValueError):
                pass
        return ids

    def yeni_urun(self):
        dlg = UrunFormDialog(self)
        if dlg.exec():
            self.yenile(zorla=True)

    def urun_cogalt_ui(self):
        try:
            uid = self._secili_id()
            if not uid:
                QMessageBox.information(self, "Secim", "Once urun secin")
                return
            ek, ok = QInputDialog.getText(
                self, "Urunu Cogalt",
                "Varyant olcusu (bos birakirsaniz L/XL/M eklenmez;\nornegin L yazarsaniz KZM-1445L olur):",
            )
            if not ok:
                return
            ok2, msg = urun_cogalt(uid, beden=ek.strip(), varyant_eki=ek.strip())
            if ok2:
                QMessageBox.information(self, "Tamam", msg)
                self.yenile(zorla=True)
            else:
                QMessageBox.warning(self, "Hata", msg)
        except Exception as e:
            log_error("Cogalt UI", e, __file__, "urun_cogalt_ui")
            QMessageBox.critical(self, "Hata", str(e))

    def varyant_ekle_ui(self):
        try:
            uid = self._secili_id()
            if not uid:
                QMessageBox.information(self, "Secim", "Ana urunu secin")
                return
            dlg = VaryantDialog(self, uid)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.yenile(zorla=True)
        except Exception as e:
            log_error("Varyant UI", e, __file__, "varyant_ekle_ui")
            QMessageBox.critical(self, "Hata", str(e))

    def barkod_kontrol_ui(self):
        try:
            liste = barkod_uyumsuz_liste()
            if not liste:
                QMessageBox.information(self, "Barkod", "Tum barkodlar stok kodu ile uyumlu.")
                return
            msg = f"{len(liste)} urunde barkod eksik veya uyumsuz.\n\n"
            for u in liste[:8]:
                msg += f"- {u.get('stok_kodu')}: {u.get('barkod') or '(yok)'} → {u.get('oneri_barkod')}\n"
            if len(liste) > 8:
                msg += "...\n"
            msg += "\nToplu duzeltme yapilsin mi?"
            cevap = QMessageBox.question(
                self, "Barkod Kontrol", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if cevap == QMessageBox.StandardButton.Yes:
                r = barkod_toplu_duzelt()
                QMessageBox.information(
                    self, "Tamam",
                    f"Duzeltilen: {r.get('duzeltilen', 0)} / {r.get('toplam', 0)}"
                )
                self.yenile(zorla=True)
        except Exception as e:
            log_error("Barkod kontrol", e, __file__, "barkod_kontrol_ui")
            QMessageBox.critical(self, "Hata", str(e))

    def urun_sil_ui(self):
        try:
            ids = self._secili_idler()
            if not ids:
                QMessageBox.information(
                    self, "Secim",
                    "Once listeden urun secin (sol taraftaki kutucugu isaretleyin)."
                )
                return
            adlar = []
            for uid in ids[:10]:
                u = urun_getir(uid)
                if u:
                    adlar.append(u.get("ad") or u.get("stok_kodu") or str(uid))
            liste = "\n".join(adlar) + (" ..." if len(ids) > 10 else "")
            cevap = QMessageBox.question(
                self, "Urun Sil",
                f"{len(ids)} urun listeden cikarilsin mi?\n{liste}\n\n"
                "(Varyantli urunler varyantlariyla birlikte cikarilir. "
                "Satis gecmisi korunur, urunler pasif olur.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if cevap != QMessageBox.StandardButton.Yes:
                return
            silinen = 0
            for uid in ids:
                ok, msg = urun_sil(uid, kalici=False)
                if ok:
                    silinen += 1
            QMessageBox.information(self, "Tamam", f"{silinen}/{len(ids)} urun cikarildi")
            self.yenile(zorla=True)
        except Exception as e:
            log_error("Urun sil UI", e, __file__, "urun_sil_ui")
            QMessageBox.critical(self, "Hata", str(e))

    def denetci_ac(self):
        from ui.denetci_ekrani import DenetciDialog
        DenetciDialog(self).exec()
        self.yenile(sessiz=True, zorla=True)

    def barkod_olustur_ui(self):
        try:
            ids = self._secili_idler()
            if ids:
                soru = (
                    f"Secili {len(ids)} urun icin stok kodu / barkod kontrol edilecek.\n"
                    "Eksik veya uyumsuz olanlar KZM-YYMM{stok}{beden} formatina cevrilecek.\n"
                    "Ornek: KZM-26111455 / KZM-26111455L\nDevam?"
                )
            else:
                soru = (
                    "Hic urun isaretlenmedi.\n"
                    "TUM aktif urunler icin stok kodu / barkod kontrol edilecek;\n"
                    "eksik veya uyumsuz olanlar KZM-YYMM{stok}{beden} formatina cevrilecek.\nDevam?"
                )
            cevap = QMessageBox.question(
                self, "Barkod Olustur", soru,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if cevap != QMessageBox.StandardButton.Yes:
                return
            r = barkod_olustur_toplu(ids if ids else None)
            msg = r.get("mesaj") or str(r)
            if r.get("hatalar"):
                msg += "\n" + "\n".join(r["hatalar"][:10])
            (QMessageBox.information if r.get("ok") else QMessageBox.warning)(
                self, "Barkod Olustur", msg
            )
            self.yenile(zorla=True)
        except Exception as e:
            log_error("Barkod olustur UI", e, __file__, "barkod_olustur_ui")
            QMessageBox.critical(self, "Hata", str(e))

    def duzenle_urun(self):
        uid = self._secili_id()
        if not uid:
            QMessageBox.information(self, "Secim", "Once bir urun secin")
            return
        dlg = UrunFormDialog(self, urun_id=uid)
        if dlg.exec():
            self.yenile(zorla=True)

    def stok_duzelt_ac(self):
        uid = self._secili_id()
        if not uid:
            QMessageBox.information(self, "Secim", "Once bir urun secin")
            return
        ad = self.tablo.item(self.tablo.selectionModel().selectedRows()[0].row(), 5)
        dlg = StokDuzeltDialog(self, uid, ad.text() if ad else "")
        if dlg.exec():
            self.yenile(zorla=True)

    def gun_sonu(self):
        try:
            ok, yol = gun_sonu_excel()
            if ok:
                QMessageBox.information(self, "Rapor", f"Gun sonu Excel olusturuldu:\n{yol}")
            else:
                QMessageBox.critical(self, "Hata", yol)
        except Exception as e:
            log_error("Gun sonu UI", e, __file__, "YonetimPaneli.gun_sonu")
            QMessageBox.critical(self, "Hata", str(e))

    def stok_excel(self):
        try:
            ok, yol = stok_listesi_excel()
            if ok:
                QMessageBox.information(self, "Rapor", f"Stok listesi Excel:\n{yol}")
            else:
                QMessageBox.critical(self, "Hata", yol)
        except Exception as e:
            log_error("Stok excel UI", e, __file__, "YonetimPaneli.stok_excel")
            QMessageBox.critical(self, "Hata", str(e))

    def barkod_yeni_format_ui(self):
        try:
            cevap = QMessageBox.question(
                self,
                "Barkod Formati",
                "Tum barkodlar KZM-YYMM{stok}{vv} formatina cevrilecek.\n"
                "Ornek: KZM-1422 -> KZM-2610142200\n"
                "Devam?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if cevap != QMessageBox.StandardButton.Yes:
                return
            r = barkodlari_yeni_formata_cevir()
            QMessageBox.information(self, "Sonuc", r.get("mesaj") or str(r))
            self.yenile(zorla=True)
        except Exception as e:
            log_error("Barkod format UI", e, __file__, "barkod_yeni_format_ui")
            QMessageBox.critical(self, "Hata", str(e))

    def gorsel_esle(self):
        try:
            klasor = gorsel_klasoru()
            sonuc = gorselleri_esle()
            QMessageBox.information(
                self,
                "Gorsel",
                f"{sonuc['mesaj']}\n\nKlasor:\n{klasor}\n\n"
                "Dosya adini stok kodu veya barkod yapin.\nOrnek: KZM-1026001.jpg"
            )
            self.yenile(zorla=True)
        except Exception as e:
            log_error("Gorsel esle UI", e, __file__, "YonetimPaneli.gorsel_esle")
            QMessageBox.critical(self, "Hata", str(e))

    def stok_excel_yukle_ui(self):
        try:
            yol, _ = QFileDialog.getOpenFileName(
                self, "Stok Excel Sec", "", "Excel (*.xlsx *.xlsm);;Tum (*.*)"
            )
            if not yol:
                return
            cevap = QMessageBox.question(
                self, "Onay",
                "Excel'deki stok degerleri urunlere yazilacak.\n"
                "Kolonlar: stok_kodu (veya barkod), yeni_stok\nDevam?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if cevap != QMessageBox.StandardButton.Yes:
                return
            sonuc = stok_excel_yukle(yol)
            QMessageBox.information(self, "Sonuc", sonuc.get("mesaj", ""))
            self.yenile(zorla=True)
        except Exception as e:
            log_error("Stok excel UI", e, __file__, "stok_excel_yukle_ui")
            QMessageBox.critical(self, "Hata", str(e))

    def kritik_stok_goster(self):
        try:
            liste = kritik_stok_listesi()
            if not liste:
                QMessageBox.information(self, "Kritik Stok", "Kritik seviyede urun yok.")
                return
            dlg = QDialog(self)
            dlg.setWindowTitle(f"Kritik Stok ({len(liste)} urun)")
            dlg.resize(640, 400)
            lay = QVBoxLayout(dlg)
            tab = QTableWidget()
            tab.setColumnCount(5)
            tab.setHorizontalHeaderLabels(["Stok Kodu", "Urun", "Stok", "Kritik", "Kategori"])
            tab.setRowCount(len(liste))
            tab.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            for i, u in enumerate(liste):
                tab.setItem(i, 0, QTableWidgetItem(u.get("stok_kodu") or ""))
                tab.setItem(i, 1, QTableWidgetItem(u.get("ad") or ""))
                tab.setItem(i, 2, QTableWidgetItem(str(u.get("stok_adedi", 0))))
                tab.setItem(i, 3, QTableWidgetItem(str(u.get("kritik_stok", 0))))
                tab.setItem(i, 4, QTableWidgetItem(u.get("kategori_adi") or ""))
            lay.addWidget(tab)
            btn = QPushButton("Kapat")
            btn.clicked.connect(dlg.accept)
            lay.addWidget(btn)
            dlg.exec()
        except Exception as e:
            log_error("Kritik stok UI", e, __file__, "kritik_stok_goster")
            QMessageBox.critical(self, "Hata", str(e))

    def csv_aktar(self):
        try:
            yol, _ = QFileDialog.getOpenFileName(
                self, "Wix Katalog CSV Sec", "", "CSV Dosyalari (*.csv);;Tum Dosyalar (*.*)"
            )
            if not yol:
                return
            cevap = QMessageBox.question(
                self,
                "Onay",
                "CSV aktarilacak. Mevcut stok kodlari korunur.\nDevam?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if cevap != QMessageBox.StandardButton.Yes:
                return
            sonuc = wix_csv_aktar(yol)
            if sonuc["ok"]:
                QMessageBox.information(self, "Aktarim", sonuc["mesaj"])
                self.yenile(zorla=True)
            else:
                QMessageBox.critical(self, "Hata", sonuc["mesaj"])
        except Exception as e:
            log_error("CSV aktar", e, __file__, "YonetimPaneli.csv_aktar")
            QMessageBox.critical(self, "Hata", str(e))
