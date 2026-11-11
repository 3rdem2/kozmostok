# -*- coding: utf-8 -*-
"""
Magaza kasa — gothic Kozmosize UI
Sol: kategori+arama, sepet, odeme, indirim, satis
Sag: satilanlar, masraflar, ciro + gun sonu
"""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QComboBox,
    QMessageBox, QHeaderView, QAbstractItemView,
    QDoubleSpinBox, QSpinBox, QListWidget, QListWidgetItem,
    QDialog, QDialogButtonBox, QFrame, QSizePolicy,
    QCheckBox, QRadioButton, QButtonGroup, QInputDialog,
    QScrollArea, QGridLayout,
)
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPixmap, QIcon, QCursor

from core.satis_servis import (
    urun_bul_kod, urun_ara_isim, satis_yap, masraf_ekle,
    gunluk_ozet, bugunku_satislar, yeni_fis_no,
    bugunku_masraflar, masraf_sil, fis_iade,
)
from core.urun_servis import (
    kategorileri_listele, varyantlari_listele,
    urun_cache_tazele_async, ana_urunleri_yerel, urun_cache_satirlari,
    urun_cache_stok_dus, urun_cache_sifirla,
)
from core.rapor_servis import gun_sonu_excel
from core.kullanici_servis import giris_yap, pin_dogrula
from core.log_servis import (
    aktif_kullanicilar, islem_kaydet, vardiya_ac, vardiya_kapat_adi,
)
from core.logger import log_error
from core.kanal_servis import magaza_kritik_uyarilari, kritik_kanal_uyarilari, bekleyen_ayirmalar, bekleyen_ayirma_yap


from ui.tema import (
    BG, PANEL, PANEL_2, BORDER, BORDER_2, ACCENT, ACCENT_H, ACCENT_D, TEXT, TEXT_2, MUTED,
    OK, WARN, DANGER, INFO, btn_qss, kontrol_qss, tablo_qss,
)

CTRL_H = 36
CARD_BG = PANEL_2
CARD_TEXT = TEXT
CARD_MUTED = TEXT_2


def _btn(variant: str = "ikincil") -> str:
    return btn_qss(variant=variant)


def _ctrl_ss() -> str:
    return kontrol_qss()


class AyirOnayDialog(QDialog):
    """Kanal ayirmasi icin sifre onayi: dogru sifreyle 'Ayir' basilirsa ayrilan kullanici kaydedilir."""

    def __init__(self, parent, kayit: dict, onaylanan: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Kanal ayirma onayi")
        self.setModal(True)
        self._onaylanan = (onaylanan or "").strip()
        v = QVBoxLayout(self)
        metin = (
            f"{kayit.get('ad') or '?'} — {kayit.get('stok_kodu') or '-'}\n"
            f"Beden/Numara: {kayit.get('beden_goster') or '-'}   ·   Barkod: {kayit.get('barkod') or '-'}\n"
            f"{kayit.get('kanal')} satisi {kayit.get('adet')} adet — magaza stokundan ayrilacak"
        )
        lbl = QLabel(metin)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size:10pt; font-weight:700;")
        v.addWidget(lbl)
        self.ed_kullanici = QLineEdit(self._onaylanan)
        self.ed_kullanici.setPlaceholderText("Kullanici adi")
        self.ed_sifre = QLineEdit()
        self.ed_sifre.setPlaceholderText("Sifre")
        self.ed_sifre.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_sifre.returnPressed.connect(self._onayla)
        v.addWidget(self.ed_kullanici)
        v.addWidget(self.ed_sifre)
        self.lbl_hata = QLabel("")
        self.lbl_hata.setStyleSheet("color:#8b0000; font-weight:700;")
        v.addWidget(self.lbl_hata)
        h = QHBoxLayout()
        btn_iptal = QPushButton("İptal")
        btn_iptal.clicked.connect(self.reject)
        btn_ok = QPushButton("Ayır")
        btn_ok.setStyleSheet(_btn("birincil"))
        btn_ok.clicked.connect(self._onayla)
        h.addWidget(btn_iptal)
        h.addWidget(btn_ok)
        v.addLayout(h)
        if not self._onaylanan:
            self.ed_kullanici.setFocus()
        else:
            self.ed_sifre.setFocus()

    def _onayla(self):
        from core.kullanici_servis import giris_yap
        ad = self.ed_kullanici.text().strip()
        ok, _ = giris_yap(ad, self.ed_sifre.text())
        if not ok:
            self.lbl_hata.setText("Kullanici adi veya sifre hatali")
            self.ed_sifre.clear()
            self.ed_sifre.setFocus()
            return
        self._onaylanan = ad
        self.accept()


class PersonelDialog(QDialog):
    """Personel giris/cikisi — cercevesiz koyu pencere, sag ustte X ile kapanir."""

    giris_ok = pyqtSignal(str)
    cikis_ok = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Personel giris / cikis")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(440, 360)
        self.setStyleSheet(f"QDialog {{ background:{PANEL}; border:1px solid {BORDER_2}; }}")
        self._drag_pos = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(10)

        # Baslik + X
        bas = QHBoxLayout()
        bas.setSpacing(8)
        lbl_bas = QLabel("PERSONEL GIRIS / CIKIS")
        lbl_bas.setStyleSheet(f"background:transparent; color:{TEXT}; font-size:13px; font-weight:700;")
        bas.addWidget(lbl_bas)
        bas.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(26, 26)
        btn_x.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_x.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_2}; font-size:14px; border:none; }}"
            f"QPushButton:hover {{ color:{ACCENT_H}; }}"
        )
        btn_x.clicked.connect(self.close)
        bas.addWidget(btn_x)
        root.addLayout(bas)

        # Aktif kullanicilar
        self.lbl_aktif = QLabel("Aktif: -")
        self.lbl_aktif.setWordWrap(True)
        self.lbl_aktif.setStyleSheet(f"background:transparent; color:{MUTED}; font-size:11px;")
        root.addWidget(self.lbl_aktif)

        # GIRIS paneli
        p_in = QFrame()
        p_in.setStyleSheet(f"QFrame {{ background:{PANEL_2}; border:1px solid {BORDER}; border-radius:2px; }}")
        fi = QVBoxLayout(p_in)
        fi.setContentsMargins(10, 8, 10, 10)
        fi.setSpacing(6)
        t1 = QLabel("GIRIS")
        t1.setStyleSheet(f"background:transparent; color:{TEXT_2}; font-size:11px; font-weight:700;")
        fi.addWidget(t1)
        g1 = QGridLayout()
        g1.setHorizontalSpacing(8)
        g1.setVerticalSpacing(6)
        self.ed_adi = QLineEdit()
        self.ed_adi.setPlaceholderText("Kullanici adi")
        self.ed_adi.setFixedHeight(CTRL_H)
        self.ed_adi.setStyleSheet(_ctrl_ss())
        self.ed_sifre = QLineEdit()
        self.ed_sifre.setPlaceholderText("Sifre")
        self.ed_sifre.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_sifre.setFixedHeight(CTRL_H)
        self.ed_sifre.setStyleSheet(_ctrl_ss())
        self.ed_sifre.returnPressed.connect(self._giris)
        lbl_a = QLabel("Kullanici adi")
        lbl_a.setStyleSheet(f"background:transparent; color:{TEXT_2}; font-size:12px;")
        lbl_a.setFixedHeight(CTRL_H)
        lbl_a.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_b = QLabel("Sifre")
        lbl_b.setStyleSheet(f"background:transparent; color:{TEXT_2}; font-size:12px;")
        lbl_b.setFixedHeight(CTRL_H)
        lbl_b.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        g1.addWidget(lbl_a, 0, 0)
        g1.addWidget(self.ed_adi, 0, 1)
        g1.addWidget(lbl_b, 1, 0)
        g1.addWidget(self.ed_sifre, 1, 1)
        g1.setColumnStretch(1, 1)
        fi.addLayout(g1)
        h1 = QHBoxLayout()
        btn_giris = QPushButton("GIRIS")
        btn_giris.setStyleSheet(_btn("ok"))
        btn_giris.setFixedHeight(CTRL_H)
        btn_giris.clicked.connect(self._giris)
        h1.addStretch()
        h1.addWidget(btn_giris)
        fi.addLayout(h1)
        root.addWidget(p_in)

        # CIKIS paneli (ayni yapi — esit genislik)
        p_out = QFrame()
        p_out.setStyleSheet(f"QFrame {{ background:{PANEL_2}; border:1px solid {BORDER}; border-radius:2px; }}")
        fo = QVBoxLayout(p_out)
        fo.setContentsMargins(10, 8, 10, 10)
        fo.setSpacing(6)
        t2 = QLabel("CIKIS")
        t2.setStyleSheet(f"background:transparent; color:{TEXT_2}; font-size:11px; font-weight:700;")
        fo.addWidget(t2)
        g2 = QGridLayout()
        g2.setHorizontalSpacing(8)
        g2.setVerticalSpacing(6)
        self.cmb_kullanici = QComboBox()
        self.cmb_kullanici.setFixedHeight(CTRL_H)
        self.cmb_kullanici.setStyleSheet(_ctrl_ss())
        self.ed_cikis_sifre = QLineEdit()
        self.ed_cikis_sifre.setPlaceholderText("Sifre")
        self.ed_cikis_sifre.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_cikis_sifre.setFixedHeight(CTRL_H)
        self.ed_cikis_sifre.setStyleSheet(_ctrl_ss())
        self.ed_cikis_sifre.returnPressed.connect(self._cikis)
        lbl_c = QLabel("Kullanici")
        lbl_c.setStyleSheet(f"background:transparent; color:{TEXT_2}; font-size:12px;")
        lbl_c.setFixedHeight(CTRL_H)
        lbl_c.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_d = QLabel("Sifre")
        lbl_d.setStyleSheet(f"background:transparent; color:{TEXT_2}; font-size:12px;")
        lbl_d.setFixedHeight(CTRL_H)
        lbl_d.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        g2.addWidget(lbl_c, 0, 0)
        g2.addWidget(self.cmb_kullanici, 0, 1)
        g2.addWidget(lbl_d, 1, 0)
        g2.addWidget(self.ed_cikis_sifre, 1, 1)
        g2.setColumnStretch(1, 1)
        fo.addLayout(g2)
        h2 = QHBoxLayout()
        btn_cikis = QPushButton("CIKIS")
        btn_cikis.setStyleSheet(_btn("tehlike"))
        btn_cikis.setFixedHeight(CTRL_H)
        btn_cikis.clicked.connect(self._cikis)
        h2.addStretch()
        h2.addWidget(btn_cikis)
        fo.addLayout(h2)
        root.addWidget(p_out)

        root.addStretch()

        # Durum satiri
        self.lbl_durum = QLabel("")
        self.lbl_durum.setWordWrap(True)
        self.lbl_durum.setStyleSheet(f"background:transparent; color:{MUTED}; font-size:11px;")
        root.addWidget(self.lbl_durum)

        self._aktif_yenile()

    def _aktif_yenile(self):
        try:
            satirlar = aktif_kullanicilar()
            adlar = sorted({(r.get("kullanici") or "").strip() for r in satirlar} - {""})
            self.lbl_aktif.setText("Aktif: " + (" · ".join(adlar) or "-"))
            secim = self.cmb_kullanici.currentText()
            self.cmb_kullanici.clear()
            self.cmb_kullanici.addItem("")
            for ad in adlar:
                self.cmb_kullanici.addItem(ad)
            i = self.cmb_kullanici.findText(secim)
            if i >= 0:
                self.cmb_kullanici.setCurrentIndex(i)
        except Exception as e:
            log_error("Aktif liste", e, __file__, "PersonelDialog._aktif_yenile")

    def _durum(self, metin: str, ok: bool):
        self.lbl_durum.setText(metin)
        self.lbl_durum.setStyleSheet(
            f"background:transparent; color:{OK if ok else DANGER}; font-size:11px; font-weight:600;"
        )

    def _giris(self):
        adi = self.ed_adi.text().strip()
        sifre = self.ed_sifre.text().strip()
        if not adi or not sifre:
            self._durum("Kullanici adi ve sifre girin", False)
            return
        ok, sonuc = giris_yap(adi, sifre)
        if not ok:
            self._durum(str(sonuc), False)
            return
        vardiya_ac(adi, sonuc.get("id"))
        islem_kaydet(adi, "ek_giris", "Magaza ek kullanici girisi", sonuc.get("id"))
        p = self.parent()
        if p is not None and hasattr(p, "aktif_kullanici"):
            p.aktif_kullanici = adi
        self.ed_adi.clear()
        self.ed_sifre.clear()
        self._aktif_yenile()
        self._durum(f"{adi} magaza oturumuna eklendi", True)
        self.ed_adi.setFocus()
        self.giris_ok.emit(adi)

    def _cikis(self):
        adi = self.cmb_kullanici.currentText().strip()
        sifre = self.ed_cikis_sifre.text().strip()
        if not adi:
            self._durum("Cikis yapacak kullaniciyi secin", False)
            return
        if not pin_dogrula(sifre, adi):
            self._durum("Sifre yanlis", False)
            self.ed_cikis_sifre.clear()
            return
        vardiya_kapat_adi(adi)
        islem_kaydet(adi, "cikis", "Magaza kullanici cikisi")
        self.ed_cikis_sifre.clear()
        p = self.parent()
        if p is not None and hasattr(p, "aktif_kullanici") and getattr(p, "aktif_kullanici", "") == adi:
            p.aktif_kullanici = getattr(p, "kullanici_adi", "")
        self._aktif_yenile()
        self._durum(f"{adi} cikis yapti", True)
        self.cikis_ok.emit(adi)

    # cercevesiz pencereyi tasima
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_pos)
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        super().mouseReleaseEvent(e)


class MagazaEkrani(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sepet: list[dict] = []  # {urun_id, ad, fiyat, adet, barkod, secili}
        self._ind_lock = False
        self.kullanici_adi = ""
        self.aktif_kullanici = ""
        self._bekleyen: list[dict] = []
        self._uyari_timer = QTimer(self)
        self._uyari_timer.setInterval(10000)
        self._uyari_timer.timeout.connect(self._bekleyen_yenile)
        self._arama_timer = QTimer(self)
        self._arama_timer.setSingleShot(True)
        self._arama_timer.timeout.connect(self._otomatik_ara)
        self._ui_olustur()
        try:
            urun_cache_tazele_async(maks_yas=0)
        except Exception:
            pass
        self._uyari_timer.start()
        QTimer.singleShot(200, self.arama_edit.setFocus)

    # ---- UI
    def _ui_olustur(self):
        self.setStyleSheet(f"background:{BG}; color:{TEXT};")
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # ==== SOL ====
        sol = QVBoxLayout()
        sol.setSpacing(8)
        sol.setContentsMargins(0, 0, 8, 0)

        # Kategori + arama tek satir — ayni yukseklik
        ust_ara = QHBoxLayout()
        ust_ara.setSpacing(8)
        ust_ara.setContentsMargins(0, 0, 0, 0)
        lbl_kat = QLabel("Kategori")
        lbl_kat.setFixedHeight(CTRL_H)
        lbl_kat.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        ust_ara.addWidget(lbl_kat)
        self.cmb_kategori = QComboBox()
        self.cmb_kategori.setFixedSize(160, CTRL_H)
        self.cmb_kategori.setStyleSheet(_ctrl_ss())
        ust_ara.addWidget(self.cmb_kategori)

        self.arama_edit = QLineEdit()
        self.arama_edit.setPlaceholderText("Barkod / ad / kod...")
        self.arama_edit.setFixedHeight(CTRL_H)
        self.arama_edit.setStyleSheet(
            f"QLineEdit {{ font-size:13px; padding:0 10px; background:{PANEL_2}; color:{TEXT}; "
            f"border:1px solid {ACCENT}; border-radius:2px; min-height:{CTRL_H}px; max-height:{CTRL_H}px; }}"
        )
        self.arama_edit.returnPressed.connect(self._enter_ara)
        self.arama_edit.textChanged.connect(self._arama_yazildi)
        self.arama_edit.installEventFilter(self)
        self.cmb_kategori.currentIndexChanged.connect(self._kategori_degisti)
        ust_ara.addWidget(self.arama_edit, 1)

        btn_ara = QPushButton("Ara")
        btn_ara.setStyleSheet(
            _btn("birincil")
            + f"QPushButton {{ min-height:{CTRL_H}px; max-height:{CTRL_H}px; padding:0 12px; }}"
        )
        btn_ara.setFixedSize(88, CTRL_H)
        btn_ara.clicked.connect(self._enter_ara)
        ust_ara.addWidget(btn_ara)
        # Hos geldin notu — manuel kapanir, 5 sn sonra kendiliginden kapanir
        self.hosgeldin_bandi = QFrame()
        self.hosgeldin_bandi.setStyleSheet(
            f"QFrame {{ background:{OK}; border:1px solid {BORDER}; border-radius:2px; }}"
        )
        hg = QHBoxLayout(self.hosgeldin_bandi)
        hg.setContentsMargins(10, 6, 6, 6)
        self.lbl_hosgeldin = QLabel("")
        self.lbl_hosgeldin.setStyleSheet(
            "color:#000000; font-size:11pt; font-weight:800; border:none;"
        )
        hg.addWidget(self.lbl_hosgeldin)
        hg.addStretch()
        btn_hg = QPushButton("Kapat")
        btn_hg.setFixedSize(64, 24)
        btn_hg.setStyleSheet(_btn("ikincil"))
        btn_hg.clicked.connect(self.hosgeldin_kapat)
        hg.addWidget(btn_hg)
        self.hosgeldin_bandi.hide()
        sol.addWidget(self.hosgeldin_bandi)

        # Bekleyen kanal ayirma uyarilari: "Ayir" ile stok dusulmeden kapanmaz
        self.uyari_bandi = QFrame()
        self.uyari_bandi.setStyleSheet(
            f"QFrame {{ background:{WARN}; border:1px solid {DANGER}; border-radius:2px; }}"
        )
        self.uyari_kutu = QVBoxLayout(self.uyari_bandi)
        self.uyari_kutu.setContentsMargins(8, 6, 8, 6)
        self.uyari_kutu.setSpacing(4)
        _ub = QLabel("Bekleyen kanal satislari — magaza stokundan ayrilmasi gerekiyor")
        _ub.setWordWrap(True)
        _ub.setStyleSheet(f"color:#000000; font-size:10pt; font-weight:800; border:none;")
        self.uyari_kutu.addWidget(_ub)
        self.uyari_bandi.hide()
        sol.addWidget(self.uyari_bandi)
        sol.addLayout(ust_ara)

        # Arama cubuguna bagli anlik oneri listesi (modal degil)
        # Google tarzi: oneri listesi layout disinda, arama altinda overlay
        self.oneri_liste = QListWidget(self)
        self.oneri_liste.setWindowFlags(Qt.WindowType.Widget)
        self.oneri_liste.setStyleSheet(
            f"QListWidget {{ background:{PANEL}; color:{TEXT}; border:1px solid {ACCENT}; "
            f"border-radius:0 0 2px 2px; font-size:12px; }}"
            f"QListWidget::item {{ padding:7px 10px; }}"
            f"QListWidget::item:selected {{ background:{ACCENT}; }}"
            f"QListWidget::item:hover {{ background:{PANEL_2}; }}"
        )
        self.oneri_liste.itemClicked.connect(self._oneri_tiklandi)
        self.oneri_liste.setIconSize(QSize(36, 36))
        self.oneri_liste.setMouseTracking(True)
        self.oneri_liste.itemEntered.connect(self._oneri_hover)
        self.oneri_liste.viewport().installEventFilter(self)
        self.oneri_liste.hide()
        self.oneri_liste.raise_()
        self._oneri_urunler = []

        self.lbl_mesaj = QLabel("")
        self.lbl_mesaj.setStyleSheet(f"color:{MUTED}; font-size:11px;")
        self.lbl_mesaj.setWordWrap(True)
        sol.addWidget(self.lbl_mesaj)

        # Hover buyuk onizleme
        self._hover_lbl = QLabel(self)
        self._hover_lbl.setFixedSize(140, 140)
        self._hover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hover_lbl.setStyleSheet(
            f"background:{PANEL}; border:1px solid {ACCENT}; border-radius:2px;"
        )
        self._hover_lbl.setVisible(False)
        self._hover_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # Sepet — urun kartlari (Kozmosize)
        sol.addWidget(self._baslik("SEPET"))
        self.sepet_scroll = QScrollArea()
        self.sepet_scroll.setWidgetResizable(True)
        self.sepet_scroll.setMinimumHeight(220)
        self.sepet_scroll.setStyleSheet(
            f"QScrollArea {{ background:{BG}; border:1px solid {BORDER}; border-radius:0px; }}"
        )
        self.sepet_host = QWidget()
        self.sepet_host.setStyleSheet(f"background:{BG};")
        self.sepet_grid = QGridLayout(self.sepet_host)
        self.sepet_grid.setContentsMargins(10, 10, 10, 10)
        self.sepet_grid.setSpacing(10)
        self.sepet_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.sepet_scroll.setWidget(self.sepet_host)
        sol.addWidget(self.sepet_scroll, 1)

        # Odeme, banka, indirim — ayni yukseklik ve ayni kutu genisligi
        KUTU_W = 140
        od_row = QHBoxLayout()
        od_row.setSpacing(8)
        od_row.setContentsMargins(0, 0, 0, 0)
        lbl_od = QLabel("Odeme")
        lbl_od.setFixedHeight(CTRL_H)
        lbl_od.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        od_row.addWidget(lbl_od)
        self.cmb_odeme = QComboBox()
        self.cmb_odeme.addItems(["Nakit", "Kart"])
        self.cmb_odeme.setFixedSize(KUTU_W, CTRL_H)
        self.cmb_odeme.setStyleSheet(_ctrl_ss())
        self.cmb_odeme.currentIndexChanged.connect(self._odeme_degisti)
        od_row.addWidget(self.cmb_odeme)
        lbl_bn = QLabel("Banka")
        lbl_bn.setFixedHeight(CTRL_H)
        lbl_bn.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        od_row.addWidget(lbl_bn)
        self.cmb_banka = QComboBox()
        self.cmb_banka.addItems(["—", "Akbank", "Yapikredi"])
        self.cmb_banka.setFixedSize(KUTU_W, CTRL_H)
        self.cmb_banka.setStyleSheet(_ctrl_ss())
        self.cmb_banka.setEnabled(False)
        od_row.addWidget(self.cmb_banka)
        od_row.addStretch()
        sol.addLayout(od_row)

        # Indirim — odeme sonrasi; kutular odeme ile ayni boy
        ind_row = QHBoxLayout()
        ind_row.setSpacing(8)
        ind_row.setContentsMargins(0, 0, 0, 0)
        lbl_ind = QLabel("Indirim")
        lbl_ind.setFixedHeight(CTRL_H)
        lbl_ind.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ind_row.addWidget(lbl_ind)
        self.rad_toplam = QRadioButton("Toplam")
        self.rad_tekil = QRadioButton("Tekil urun")
        self.rad_toplam.setChecked(True)
        self.rad_toplam.setFixedHeight(CTRL_H)
        self.rad_tekil.setFixedHeight(CTRL_H)
        self._ind_grp = QButtonGroup(self)
        self._ind_grp.addButton(self.rad_toplam)
        self._ind_grp.addButton(self.rad_tekil)
        self.rad_toplam.toggled.connect(self._indirim_mod_degisti)
        ind_row.addWidget(self.rad_toplam)
        ind_row.addWidget(self.rad_tekil)

        self.spin_indirim = QDoubleSpinBox()
        self.spin_indirim.setRange(0, 9999)
        self.spin_indirim.setDecimals(0)
        self.spin_indirim.setPrefix("TL ")
        self.spin_indirim.setFixedSize(KUTU_W, CTRL_H)
        self.spin_indirim.setStyleSheet(_ctrl_ss())
        self.spin_indirim.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin_indirim.valueChanged.connect(self._indirim_tl_degisti)
        ind_row.addWidget(self.spin_indirim)

        self.spin_yuzde = QDoubleSpinBox()
        self.spin_yuzde.setRange(0, 100)
        self.spin_yuzde.setDecimals(1)
        self.spin_yuzde.setSuffix(" %")
        self.spin_yuzde.setFixedSize(KUTU_W, CTRL_H)
        self.spin_yuzde.setStyleSheet(_ctrl_ss())
        self.spin_yuzde.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin_yuzde.valueChanged.connect(self._indirim_yuzde_degisti)
        ind_row.addWidget(self.spin_yuzde)
        ind_row.addStretch()
        sol.addLayout(ind_row)

        self.lbl_ara = QLabel("Ara toplam: 0 TL")
        self.lbl_ara.setStyleSheet(f"color:{MUTED}; font-size:11px;")
        sol.addWidget(self.lbl_ara)
        self.lbl_toplam = QLabel("TOPLAM: 0 TL")
        self.lbl_toplam.setStyleSheet(
            f"color:{ACCENT_H}; font-size:16px; font-weight:700; background:transparent;"
        )
        sol.addWidget(self.lbl_toplam)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_tamam = QPushButton("SATIS TAMAMLA")
        btn_tamam.setStyleSheet(_btn("birincil"))
        btn_tamam.clicked.connect(self.satisi_tamamla)
        btn_row.addWidget(btn_tamam)
        btn_sil = QPushButton("SEPETI SIL")
        btn_sil.setStyleSheet(_btn("ikincil"))
        btn_sil.clicked.connect(self.sepet_temizle)
        btn_row.addWidget(btn_sil)
        btn_row.addStretch()
        sol.addLayout(btn_row)

        root.addLayout(sol, 5)

        # ==== SAG ====
        sag = QVBoxLayout()
        sag.setSpacing(6)

        # Satilanlar tablosu
        sag.addWidget(self._baslik("Bugun satilanlar"))
        self.satis_tablo = QTableWidget(0, 5)
        self.satis_tablo.setHorizontalHeaderLabels(
            ["Barkod", "Urun", "Adet", "Tutar", "Odeme"]
        )
        sh = self.satis_tablo.horizontalHeader()
        sh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        sh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        sh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        sh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        sh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.satis_tablo.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.satis_tablo.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.satis_tablo.verticalHeader().setVisible(False)
        self.satis_tablo.setAlternatingRowColors(True)
        self._tablo_stili(self.satis_tablo)
        sag.addWidget(self.satis_tablo, 3)

        iade_row = QHBoxLayout()
        btn_iade = QPushButton("Secili fisi iade")
        btn_iade.setStyleSheet(_btn("tehlike"))
        btn_iade.clicked.connect(self.satis_secili_iade)
        iade_row.addWidget(btn_iade)
        iade_row.addStretch()
        sag.addLayout(iade_row)

        # Masraflar tablosu (bitisik)
        sag.addWidget(self._baslik("Masraflar / Giderler"))
        self.masraf_tablo = QTableWidget(0, 3)
        self.masraf_tablo.setHorizontalHeaderLabels(["Saat", "Aciklama", "Tutar"])
        mh = self.masraf_tablo.horizontalHeader()
        mh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        mh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        mh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.masraf_tablo.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.masraf_tablo.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.masraf_tablo.verticalHeader().setVisible(False)
        self.masraf_tablo.setMaximumHeight(140)
        self.masraf_tablo.setAlternatingRowColors(True)
        self._tablo_stili(self.masraf_tablo)
        sag.addWidget(self.masraf_tablo)

        # Masraf giris
        mrow = QHBoxLayout()
        mrow.setSpacing(6)
        self.masraf_tutar = QDoubleSpinBox()
        self.masraf_tutar.setRange(0, 9999)
        self.masraf_tutar.setDecimals(0)
        self.masraf_tutar.setFixedSize(90, CTRL_H)
        self.masraf_tutar.setStyleSheet(_ctrl_ss())
        self.masraf_tutar.setPrefix("TL ")
        mrow.addWidget(self.masraf_tutar)
        self.masraf_not = QLineEdit()
        self.masraf_not.setPlaceholderText("Masraf aciklamasi")
        self.masraf_not.setStyleSheet(_ctrl_ss())
        self.masraf_not.setFixedHeight(CTRL_H)
        mrow.addWidget(self.masraf_not, 1)
        btn_m = QPushButton("Ekle")
        btn_m.setStyleSheet(_btn("ok"))
        btn_m.setFixedHeight(CTRL_H)
        btn_m.clicked.connect(self.masraf_kaydet)
        mrow.addWidget(btn_m)
        btn_msil = QPushButton("Sil")
        btn_msil.setStyleSheet(_btn("tehlike"))
        btn_msil.setFixedHeight(CTRL_H)
        btn_msil.clicked.connect(self.masraf_secili_sil)
        mrow.addWidget(btn_msil)
        sag.addLayout(mrow)

        # Ciro + gun sonu (alt)
        ozet = QFrame()
        ozet.setStyleSheet(
            f"QFrame {{ background:{PANEL}; border:1px solid {BORDER}; border-radius:2px; }}"
        )
        of = QVBoxLayout(ozet)
        of.setContentsMargins(8, 6, 8, 6)
        of.setSpacing(2)
        self.lbl_ciro = QLabel("Ciro: 0 TL")
        self.lbl_nakit = QLabel("Nakit: 0 TL")
        self.lbl_kart = QLabel("Kart: 0 TL")
        self.lbl_masraf = QLabel("Masraf: 0 TL")
        self.lbl_net = QLabel("Net: 0 TL")
        self.lbl_devir = QLabel("Dunku devir: 0 TL")
        for lbl, col in (
            (self.lbl_ciro, TEXT),
            (self.lbl_nakit, OK),
            (self.lbl_kart, INFO),
            (self.lbl_masraf, DANGER),
            (self.lbl_net, TEXT),
            (self.lbl_devir, ACCENT),
        ):
            lbl.setStyleSheet(f"background:transparent; color:{col}; font-weight:600; font-size:12px;")
            of.addWidget(lbl)
        sag.addWidget(ozet)

        btn_gun = QPushButton("Gun Sonu")
        btn_gun.setStyleSheet(_btn("ikincil"))
        btn_gun.clicked.connect(self.gun_sonu)
        sag.addWidget(btn_gun)

        # Personel: tek tus + aktif kullanicilar (detay pencerede)
        p_row = QHBoxLayout()
        p_row.setSpacing(8)
        self.btn_personel = QPushButton("PERSONEL")
        self.btn_personel.setStyleSheet(_btn("birincil"))
        self.btn_personel.setFixedHeight(CTRL_H)
        self.btn_personel.clicked.connect(self.personel_pencere)
        p_row.addWidget(self.btn_personel)
        self.lbl_aktif = QLabel("Aktif: -")
        self.lbl_aktif.setStyleSheet(f"background:transparent; color:{MUTED}; font-size:11px;")
        p_row.addWidget(self.lbl_aktif, 1)
        sag.addLayout(p_row)

        root.addLayout(sag, 2)
        self._kategorileri_doldur(False)

    def _baslik(self, t):
        lbl = QLabel(t)
        lbl.setStyleSheet(f"color:{TEXT}; font-size:12px; font-weight:700; border:none; padding:2px 0;")
        return lbl

    def _tablo_stili(self, tablo):
        tablo.setShowGrid(True)
        tablo.setStyleSheet(
            f"QTableWidget {{ background:{PANEL}; color:{TEXT}; border:1px solid {BORDER}; "
            "gridline-color:#3A3A3A; font-size:12px; alternate-background-color:" + PANEL_2 + "; }}"
            "QTableWidget::item { padding:4px 6px; border-right:1px solid #2E2E2E; "
            "border-bottom:1px solid #2E2E2E; }"
            f"QHeaderView::section {{ background:{PANEL_2}; color:{TEXT}; padding:6px; "
            f"border:none; border-right:1px solid #3A3A3A; border-bottom:1px solid {ACCENT}; font-size:11px; }}"
            f"QTableWidget::item:selected {{ background:{ACCENT_D}; }}"
        )

    # ---- arama
    def _arama_yazildi(self, _text):
        self._arama_timer.stop()
        metin = self.arama_edit.text().strip()
        if len(metin) < 1:
            self._oneri_gizle()
            return
        self._arama_timer.start(180)

    def _kod_benzeri(self, metin: str) -> bool:
        """Barkod/stok koduna benzeyen giris (varyant barkodu icin DB yedegi)."""
        metin = (metin or "").strip()
        return len(metin) >= 6 and " " not in metin

    def _yerel_kod_eslesmesi(self, metin: str):
        """Onbellekte barkod/stok kodu tam eslesmesi (0 ag gezisi); yoksa None."""
        metin = (metin or "").strip().lower()
        if not metin:
            return None
        m_norm = metin.replace("kzm-", "").replace(" ", "")
        for u in (urun_cache_satirlari() or []):
            b = (u.get("barkod") or "").strip().lower()
            k = (u.get("stok_kodu") or "").strip().lower()
            if metin in (b, k):
                return u
            if m_norm and m_norm == b.replace("KZM-", "").replace(" ", "").lower():
                return u
        return None

    def _otomatik_ara(self):
        """Yazarken anlik: cubugun altinda oneri listesi (modal yok)."""
        try:
            metin = self.arama_edit.text().strip()
            if not metin:
                self._oneri_gizle()
                return
            # Tam barkod/kod eslesmesi — listeye de koy, Enter ile eklenir
            try:
                urun_cache_tazele_async(maks_yas=60)
            except Exception:
                pass
            kat = self.cmb_kategori.currentData()
            u = self._yerel_kod_eslesmesi(metin)
            if u is None and self._kod_benzeri(metin):
                u = urun_bul_kod(metin)
            if u:
                # Varyant barkodu okutulduysa ana urune cevir
                oneriler = [self._ana_urune_cevir(u)]
            else:
                oneriler = ana_urunleri_yerel(arama=metin, kategori_id=kat)
            self._oneri_doldur(oneriler)
        except Exception as e:
            log_error("Otomatik arama", e, __file__, "MagazaEkrani._otomatik_ara")

    def _oneri_konumla(self):
        """Arama kutusunun hemen altinda, layout'u itmeden goster."""
        try:
            r = self.arama_edit.rect()
            top_left = self.arama_edit.mapTo(self, r.bottomLeft())
            w = max(self.arama_edit.width(), 280)
            self.oneri_liste.setFixedWidth(w)
            h = min(200, max(40, self.oneri_liste.sizeHintForRow(0) * min(8, self.oneri_liste.count()) + 8))
            if self.oneri_liste.count() == 0:
                h = 40
            self.oneri_liste.setFixedHeight(h)
            self.oneri_liste.move(top_left.x(), top_left.y() + 1)
            self.oneri_liste.raise_()
        except Exception:
            pass

    def _oneri_doldur(self, oneriler: list):
        self._oneri_urunler = oneriler or []
        self.oneri_liste.clear()
        self._hover_gizle()
        if not self._oneri_urunler:
            self._oneri_gizle()
            return
        for u in self._oneri_urunler:
            stok = int(u.get("stok_adedi") or 0)
            fiyat = float(u.get("satis_fiyati") or 0)
            kod = u.get("stok_kodu") or ""
            beden = u.get("beden") or ""
            metin = f"{u.get('ad', '')}  |  {fiyat:,.0f} TL  |  Stok:{stok}"
            if beden:
                metin += f"  |  {beden}"
            if kod:
                metin += f"  [{kod}]"
            item = QListWidgetItem(metin)
            if stok <= 0:
                item.setForeground(QColor(DANGER))
            self.oneri_liste.addItem(item)
        self.oneri_liste.show()
        self.oneri_liste.setCurrentRow(0)
        self._oneri_konumla()

    def _oneri_hover(self, item):
        row = self.oneri_liste.row(item)
        if row < 0 or row >= len(self._oneri_urunler):
            self._hover_gizle()
            return
        u = self._oneri_urunler[row]
        yol = u.get("gorsel_yolu") or ""
        if not yol:
            try:
                from core.gorsel_servis import gorsel_yolu_bul
                yol = gorsel_yolu_bul(u.get("stok_kodu") or "", u.get("barkod") or "") or ""
            except Exception:
                yol = ""
        if not yol:
            self._hover_gizle()
            return
        pix = QPixmap(yol)
        if pix.isNull():
            self._hover_gizle()
            return
        self._hover_lbl.setPixmap(pix.scaled(
            136, 136, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))
        # liste saginda konumla
        pos = self.oneri_liste.mapTo(self, self.oneri_liste.rect().topRight())
        self._hover_lbl.move(min(pos.x() + 8, self.width() - 150), max(40, pos.y()))
        self._hover_lbl.setVisible(True)
        self._hover_lbl.raise_()

    def _hover_gizle(self):
        if hasattr(self, "_hover_lbl"):
            self._hover_lbl.setVisible(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.oneri_liste.isVisible():
            self._oneri_konumla()

    def eventFilter(self, obj, event):
        if obj is self.oneri_liste.viewport():
            if event.type() == QEvent.Type.Leave:
                self._hover_gizle()
        if obj is self.arama_edit:
            if event.type() == QEvent.Type.FocusIn:
                metin = self.arama_edit.text().strip()
                if metin:
                    QTimer.singleShot(30, self._otomatik_ara)
                elif self.cmb_kategori.currentData():
                    QTimer.singleShot(30, self._kategori_urunlerini_goster)
            elif event.type() == QEvent.Type.FocusOut:
                # Listeye tiklamaya izin ver (kisa gecikme)
                QTimer.singleShot(180, self._focus_kaybi_kontrol)
        return super().eventFilter(obj, event)

    def _focus_kaybi_kontrol(self):
        """Arama ve oneri listesi odakta degilse kapat."""
        try:
            fw = self.focusWidget()
            if fw is self.arama_edit:
                return
            if fw is self.oneri_liste or (fw and self.oneri_liste.isAncestorOf(fw)):
                return
            self._oneri_gizle()
        except Exception:
            self._oneri_gizle()

    def _kategori_degisti(self, _i=None):
        if self.arama_edit.hasFocus() and not self.arama_edit.text().strip():
            self._kategori_urunlerini_goster()

    def _kategori_urunlerini_goster(self):
        try:
            kat = self.cmb_kategori.currentData()
            if not kat:
                self._oneri_gizle()
                return
            oneriler = ana_urunleri_yerel(arama="", kategori_id=kat)
            self._oneri_doldur(oneriler)
        except Exception as e:
            log_error("Kategori urun", e, __file__, "MagazaEkrani._kategori_urunlerini_goster")

    def _oneri_gizle(self):
        self.oneri_liste.clear()
        self.oneri_liste.hide()
        self._oneri_urunler = []
        self._hover_gizle()

    def _oneri_tiklandi(self, item):
        row = self.oneri_liste.row(item)
        if 0 <= row < len(self._oneri_urunler):
            u = self._oneri_urunler[row]
            self._oneri_gizle()
            self.arama_edit.clear()
            self._sepete_ekle(self._ana_urune_cevir(u))
            self.arama_edit.setFocus()

    def _enter_ara(self):
        try:
            self._arama_timer.stop()
            metin = self.arama_edit.text().strip()
            # Listede secili varsa onu ekle
            if self.oneri_liste.isVisible() and self._oneri_urunler:
                row = self.oneri_liste.currentRow()
                if row < 0:
                    row = 0
                if 0 <= row < len(self._oneri_urunler):
                    u = self._oneri_urunler[row]
                    self._oneri_gizle()
                    self.arama_edit.clear()
                    self._sepete_ekle(self._ana_urune_cevir(u))
                    self.arama_edit.setFocus()
                    return
            if not metin:
                # Bos arama + kategori -> kategori urunleri
                if self.cmb_kategori.currentData():
                    self._kategori_urunlerini_goster()
                else:
                    self._oneri_gizle()
                return
            u = self._yerel_kod_eslesmesi(metin)
            if u is None and self._kod_benzeri(metin):
                u = urun_bul_kod(metin)
            if u:
                self._oneri_gizle()
                self.arama_edit.clear()
                self._sepete_ekle(self._ana_urune_cevir(u), on_secili_barkod=u.get("barkod"))
                self.arama_edit.setFocus()
                return
            kat = self.cmb_kategori.currentData()
            oneriler = ana_urunleri_yerel(arama=metin, kategori_id=kat)
            if not oneriler:
                self._oneri_gizle()
                self.mesaj("Urun bulunamadi", False)
                return
            if len(oneriler) == 1:
                self._oneri_gizle()
                self.arama_edit.clear()
                self._sepete_ekle(self._ana_urune_cevir(oneriler[0]))
                self.arama_edit.setFocus()
                return
            self._oneri_doldur(oneriler)
            self.arama_edit.setFocus()
        except Exception as e:
            log_error("Arama", e, __file__, "MagazaEkrani._enter_ara")
            self.mesaj(str(e), False)

    def _adet_sor(self, varsayilan: int = 1) -> int:
        adet, ok = QInputDialog.getInt(
            self, "Adet", "Sepete eklenecek adet:", varsayilan, 1, 99, 1
        )
        if not ok:
            return 0
        return int(adet)

    def _ana_urune_cevir(self, u: dict) -> dict:
        """Varyant ise parent ana urunu dondur; degilse kendisi."""
        try:
            from core.urun_servis import urun_getir
            pid = u.get("parent_id")
            if pid:
                ana = urun_getir(int(pid))
                if ana:
                    return ana
            return u
        except Exception:
            return u

    def _sepete_ekle(self, urun: dict, adet: int = 1, on_secili_barkod: str | None = None):
        """
        Ana urun karti sepete eklenir. Varyant + adet kart uzerinden secilir.
        Ekstra pencere yok.
        """
        try:
            from core.urun_servis import varyantlari_listele, urun_getir
            adet = max(1, int(adet or 1))
            ana = self._ana_urune_cevir(urun)
            ana_id = ana.get("id")
            tum = varyantlari_listele(ana_id) if ana_id else [ana]
            varyantlar = [v for v in tum if v.get("id") != ana_id]
            # Secili varyant: barkod ile veya tek varyant veya ana
            secili = None
            if on_secili_barkod:
                for v in tum:
                    if (v.get("barkod") or "") == on_secili_barkod:
                        secili = v
                        break
            if secili is None and varyantlar:
                secili = varyantlar[0]
            if secili is None:
                secili = ana

            # Ayni ana urun sepette varsa sadece adet artirma (ayni varyant)
            for item in self.sepet:
                if item.get("parent_id") == ana_id and item.get("urun_id") == secili.get("id"):
                    item["adet"] = int(item["adet"]) + adet
                    self._sepet_goster()
                    self.mesaj(f"{item.get('ad')} adet guncellendi", True)
                    return

            gorsel = ana.get("gorsel_yolu") or secili.get("gorsel_yolu") or ""
            self.sepet.append({
                "urun_id": secili.get("id"),
                "parent_id": ana_id,
                "ad": ana.get("ad") or secili.get("ad") or "?",
                "fiyat": float(secili.get("satis_fiyati") or ana.get("satis_fiyati") or 0),
                "adet": adet,
                "barkod": secili.get("barkod") or "",
                "stok_kodu": ana.get("stok_kodu") or "",
                "beden": secili.get("beden") or "",
                "gorsel": gorsel,
                "secili": False,
                "varyantlar": varyantlar if varyantlar else [],
                "ana": ana,
            })
            self._sepet_goster()
            self.mesaj(f"{ana.get('ad')} sepete eklendi", True)
        except Exception as e:
            log_error("Sepete ekle", e, __file__, "MagazaEkrani._sepete_ekle")
            self.mesaj(str(e), False)

    def _indirim_mod_degisti(self):
        self._sepet_goster()

    def _sepet_goster(self):
        # kartlari temizle
        while self.sepet_grid.count():
            item = self.sepet_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        tekil = self.rad_tekil.isChecked()
        ara = 0.0
        # Yatay akis: genislige gore kolon
        cols = max(2, self.sepet_scroll.viewport().width() // 190)
        for i, item in enumerate(self.sepet):
            t = float(item["fiyat"]) * int(item["adet"])
            ara += t
            kart = self._sepet_kart_olustur(i, item, tekil)
            self.sepet_grid.addWidget(kart, i // cols, i % cols)

        self._sepet_toplamlarini_guncelle()

    def _sepet_toplamlarini_guncelle(self):
        """Kartları yeniden oluşturmadan ara toplam ve indirimi güncelle."""
        ara = self._ara_toplam()
        ind = self._indirim_hesapla(ara)
        y = self.spin_yuzde.value()
        self.lbl_ara.setText(
            f"Ara toplam: {ara:,.0f} TL  |  Indirim: {ind:,.0f} TL"
            + (f" (%{y:.1f})" if y else "")
        )
        self.lbl_toplam.setText(f"TOPLAM: {max(0.0, ara - ind):,.0f} TL")

    def _sepet_kart_olustur(self, idx: int, item: dict, tekil: bool) -> QFrame:
        """
        [ ]                    [X]
        FOTOGRAF
        URUN ADI
        Barkod
        [S][M][L][XL]     Fiyat / adet
        """
        kart = QFrame()
        kart.setFixedSize(176, 350)
        kart.setStyleSheet(
            f"QFrame {{ background:{CARD_BG}; border:1px solid {BORDER}; border-radius:2px; }}"
        )
        root = QVBoxLayout(kart)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(3)

        ust = QHBoxLayout()
        ust.setContentsMargins(0, 0, 0, 0)
        chk = QCheckBox()
        chk.setChecked(bool(item.get("secili")))
        chk.setEnabled(tekil)
        chk.setStyleSheet(
            "QCheckBox { background:transparent; }"
            f"QCheckBox::indicator {{ width:14px; height:14px; border:1px solid {BORDER_2}; "
            f"background:{PANEL}; border-radius:2px; }}"
            f"QCheckBox::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; }}"
        )
        chk.stateChanged.connect(lambda s, i=idx: self._sepet_secim(i, s))
        ust.addWidget(chk)
        ust.addStretch()
        btn_x = QPushButton("×")
        btn_x.setFixedSize(22, 22)
        btn_x.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT}; border:none; "
            "font-size:16px; font-weight:700; padding:0; }}"
            f"QPushButton:hover {{ color:{ACCENT}; }}"
        )
        btn_x.clicked.connect(lambda _=False, i=idx: self._sepet_satir_sil(i))
        ust.addWidget(btn_x)
        root.addLayout(ust)

        # fotograf
        foto = QLabel()
        foto.setFixedSize(158, 132)
        foto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foto.setStyleSheet(f"background:{PANEL_2}; border:1px solid {BORDER}; border-radius:2px;")
        yol = item.get("gorsel") or ""
        if yol:
            pix = QPixmap(yol)
            if not pix.isNull():
                foto.setPixmap(pix.scaled(
                    154, 128, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
            else:
                foto.setText("FOTOGRAF")
                foto.setStyleSheet(f"background:{PANEL_2}; color:{MUTED}; font-size:10px;")
        else:
            foto.setText("FOTOGRAF")
            foto.setStyleSheet(f"background:{PANEL_2}; color:{MUTED}; font-size:10px;")
        root.addWidget(foto, 0, Qt.AlignmentFlag.AlignCenter)

        # urun adi — 2 satir
        ad = QLabel((item.get("ad") or "").upper())
        ad.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ad.setStyleSheet(
            f"color:{CARD_TEXT}; font-size:12px; font-weight:700; letter-spacing:0.2px;"
        )
        ad.setWordWrap(True)
        ad.setMaximumHeight(36)
        # ellipsis manuel: uzun isim kirp
        text = (item.get("ad") or "").upper()
        if len(text) > 40:
            ad.setText(text[:38] + "…")
        else:
            ad.setText(text)
        root.addWidget(ad)

        # Kod ve fiyat alt alta, aynı yazı boyutu ve hizalama.
        kod = item.get("barkod") or item.get("stok_kodu") or ""
        bk = QLabel(kod)
        bk.setToolTip(kod)
        bk.setWordWrap(True)
        bk.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bk.setStyleSheet(f"color:{CARD_MUTED}; font-size:13px; border:none; background:transparent;")
        root.addWidget(bk)

        fiyat = QLabel(f"{float(item.get('fiyat') or 0):,.0f} TL")
        fiyat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fiyat.setStyleSheet(f"color:{TEXT}; font-size:13px; border:none; background:transparent;")
        root.addWidget(fiyat)

        # Beden seçimi ayrı satırda; adet kontrolüyle yer paylaşmaz.
        alt = QHBoxLayout()
        alt.setSpacing(3)
        alt.setContentsMargins(0, 4, 0, 0)

        varyantlar = item.get("varyantlar") or []
        beden_map = {}
        for v in varyantlar:
            b = (v.get("beden") or "").upper().strip()
            if b:
                beden_map[b] = v

        kutu_pasif = (
            f"QPushButton {{ background:{PANEL_2}; color:{TEXT}; font-size:10px; font-weight:600; "
            f"border:1px solid {BORDER_2}; border-radius:2px; padding:0; "
            "min-width:26px; max-width:26px; min-height:26px; max-height:26px; }"
        )
        kutu_aktif = (
            f"QPushButton {{ background:{ACCENT}; color:{TEXT}; font-size:10px; font-weight:700; "
            f"border:1px solid {ACCENT}; border-radius:2px; padding:0; "
            "min-width:26px; max-width:26px; min-height:26px; max-height:26px; }"
        )
        kutu_yok = (
            f"QPushButton {{ background:{PANEL}; color:{MUTED}; font-size:10px; "
            f"border:1px solid {BORDER}; border-radius:2px; padding:0; "
            "min-width:26px; max-width:26px; min-height:26px; max-height:26px; }"
        )

        if varyantlar:
            for etiket in ("S", "M", "L", "XL"):
                v = beden_map.get(etiket)
                btn = QPushButton(etiket)
                btn.setFixedSize(26, 26)
                if v:
                    aktif = v.get("id") == item.get("urun_id")
                    btn.setStyleSheet(kutu_aktif if aktif else kutu_pasif)
                    btn.clicked.connect(
                        lambda _=False, i=idx, vid=v.get("id"): self._sepet_varyant_sec(i, vid)
                    )
                else:
                    btn.setEnabled(False)
                    btn.setStyleSheet(kutu_yok)
                alt.addWidget(btn)
        else:
            notu = QLabel("tek urun")
            notu.setStyleSheet(f"color:{MUTED}; font-size:9px;")
            alt.addWidget(notu)

        alt.addStretch()

        root.addLayout(alt)
        root.addStretch()

        adet_satiri = QHBoxLayout()
        adet_satiri.setSpacing(6)
        adet_satiri.addStretch()
        eksi = QPushButton("−")
        arti = QPushButton("+")
        for btn in (eksi, arti):
            btn.setFixedSize(32, 34)
            btn.setAutoRepeat(True)
            btn.setStyleSheet(
                f"QPushButton {{ background:{PANEL}; color:{TEXT}; border:1px solid {BORDER_2}; "
                "border-radius:2px; font-size:18px; padding:0; min-width:0px; min-height:0px; letter-spacing:0px; }"
                f"QPushButton:hover {{ background:{ACCENT}; }}"
                f"QPushButton:disabled {{ color:{MUTED}; }}"
            )
        eksi.setToolTip("Adedi azalt")
        arti.setToolTip("Adedi artır")

        spin = QSpinBox()
        spin.setRange(1, max(99, int(item.get("adet") or 1)))
        spin.setValue(int(item.get("adet") or 1))
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setKeyboardTracking(False)
        spin.setFixedSize(48, 34)
        # Indirim kutusundaki gibi: icer QLineEdit'e dokunmayan sade QSpinBox stili
        # (ozel 'QSpinBox QLineEdit' kurali icer alani 1px'e daratip rakami gizliyordu)
        spin.setStyleSheet(
            f"QSpinBox {{ background:{PANEL_2}; color:{TEXT}; border:1px solid {BORDER_2}; "
            "border-radius:2px; font-size:15px; font-weight:700; padding:0 2px; }"
            "QSpinBox::up-button, QSpinBox::down-button { width:0px; height:0px; }"
        )
        spin.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setToolTip("Ürün adedi; sayı yazarak da değiştirilebilir")
        eksi.clicked.connect(spin.stepDown)
        arti.clicked.connect(spin.stepUp)
        spin.valueChanged.connect(lambda v, i=idx: self._sepet_adet_degisti(i, v))
        spin.valueChanged.connect(lambda v, b=eksi: b.setEnabled(v > spin.minimum()))
        spin.valueChanged.connect(lambda v, b=arti: b.setEnabled(v < spin.maximum()))
        eksi.setEnabled(spin.value() > spin.minimum())
        arti.setEnabled(spin.value() < spin.maximum())
        adet_satiri.addWidget(eksi)
        adet_satiri.addWidget(spin)
        adet_satiri.addWidget(arti)
        adet_satiri.addStretch()
        root.addLayout(adet_satiri)
        return kart

    def _sepet_varyant_sec(self, idx: int, varyant_id: int):
        if not (0 <= idx < len(self.sepet)):
            return
        item = self.sepet[idx]
        for v in item.get("varyantlar") or []:
            if v.get("id") == varyant_id:
                item["urun_id"] = v.get("id")
                item["barkod"] = v.get("barkod") or ""
                item["beden"] = v.get("beden") or ""
                item["fiyat"] = float(v.get("satis_fiyati") or item.get("fiyat") or 0)
                if v.get("gorsel_yolu"):
                    item["gorsel"] = v.get("gorsel_yolu")
                break
        self._sepet_goster()

    def _sepet_satir_sil(self, idx: int):
        if 0 <= idx < len(self.sepet):
            self.sepet.pop(idx)
            self._sepet_goster()

    def _sepet_adet_degisti(self, idx: int, val: int):
        if 0 <= idx < len(self.sepet):
            self.sepet[idx]["adet"] = max(1, int(val))
            if not self._ind_lock:
                self._sepet_goster()

    def _sepet_secim(self, idx: int, state: int):
        if 0 <= idx < len(self.sepet):
            self.sepet[idx]["secili"] = state == Qt.CheckState.Checked.value or state == 2
            if not self._ind_lock:
                # yuzde varsa tekil bazda TL guncelle
                self._indirim_yuzde_degisti()

    def _indirim_taban(self) -> float:
        """Toplam veya secili tekil urunlerin tutari."""
        if self.rad_tekil.isChecked():
            s = sum(
                float(i["fiyat"]) * int(i["adet"])
                for i in self.sepet if i.get("secili")
            )
            return s
        return self._ara_toplam()

    def _indirim_hesapla(self, ara: float | None = None) -> float:
        if ara is None:
            ara = self._ara_toplam()
        taban = self._indirim_taban()
        ind = float(self.spin_indirim.value() or 0)
        if self.rad_tekil.isChecked():
            return min(ind, taban)
        return min(ind, ara)

    def _ara_toplam(self) -> float:
        return sum(float(i["fiyat"]) * int(i["adet"]) for i in self.sepet)

    def _indirim_tl_degisti(self):
        if self._ind_lock:
            return
        self._ind_lock = True
        taban = self._indirim_taban()
        if taban > 0:
            y = (self.spin_indirim.value() / taban) * 100
            self.spin_yuzde.blockSignals(True)
            self.spin_yuzde.setValue(min(100, y))
            self.spin_yuzde.blockSignals(False)
        self._sepet_goster()
        self._ind_lock = False

    def _indirim_yuzde_degisti(self):
        if self._ind_lock:
            return
        self._ind_lock = True
        taban = self._indirim_taban()
        tl = taban * (self.spin_yuzde.value() / 100.0)
        self.spin_indirim.blockSignals(True)
        self.spin_indirim.setValue(round(tl))
        self.spin_indirim.blockSignals(False)
        self._sepet_goster()
        self._ind_lock = False

    def sepet_temizle(self):
        self.sepet.clear()
        self.spin_indirim.setValue(0)
        self.spin_yuzde.setValue(0)
        self._sepet_goster()
        self.mesaj("Sepet temizlendi")
        self.arama_edit.setFocus()

    def _odeme_degisti(self):
        kart = self.cmb_odeme.currentIndex() == 1
        self.cmb_banka.setEnabled(kart)
        if not kart:
            self.cmb_banka.setCurrentIndex(0)

    def _kategorileri_doldur(self, koru_secim: bool = True):
        onceki = self.cmb_kategori.currentData() if koru_secim else None
        self.cmb_kategori.blockSignals(True)
        self.cmb_kategori.clear()
        self.cmb_kategori.addItem("Tum kategoriler", None)
        for k in kategorileri_listele():
            self.cmb_kategori.addItem(k["ad"], k["id"])
        if onceki is not None:
            idx = self.cmb_kategori.findData(onceki)
            self.cmb_kategori.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_kategori.blockSignals(False)

    def mesaj(self, text, ok=True):
        self.lbl_mesaj.setStyleSheet(
            f"color: {OK if ok else DANGER}; font-size:12px;"
        )
        self.lbl_mesaj.setText(text)

    # ---- satis
    def satisi_tamamla(self):
        if getattr(self, "_bekleyen", None):
            self.mesaj("Once bekleyen kanal ayirmasini yapin (uyari bandindaki 'Ayir')", False)
            return
        if not self.sepet:
            self.mesaj("Sepet bos", False)
            return
        try:
            odeme = "nakit" if self.cmb_odeme.currentIndex() == 0 else "kart"
            banka = None
            if odeme == "kart":
                b = self.cmb_banka.currentText()
                if b in ("Akbank", "Yapikredi"):
                    banka = b
                else:
                    self.mesaj("Kart icin banka secin", False)
                    return
            ind_toplam = self._indirim_hesapla()
            fis = yeni_fis_no()
            basarili = 0
            # Indirimi ilk satira veya secili urunlere dagit
            if self.rad_tekil.isChecked():
                secililer = [i for i, it in enumerate(self.sepet) if it.get("secili")]
                if not secililer and ind_toplam > 0:
                    self.mesaj("Tekil indirim icin urun secin (kutucuk)", False)
                    return
                for i, item in enumerate(self.sepet):
                    ind = ind_toplam if (i == secililer[0] if secililer else False) else 0
                    ok, msg = satis_yap(
                        item["urun_id"], int(item["adet"]), float(item["fiyat"]),
                        ind, odeme, fis_no=fis, banka=banka,
                    )
                    if ok:
                        basarili += 1
                        urun_cache_stok_dus(int(item["urun_id"]), int(item["adet"]))
                    else:
                        self.mesaj(msg, False)
                        break
            else:
                for i, item in enumerate(self.sepet):
                    ok, msg = satis_yap(
                        item["urun_id"], int(item["adet"]), float(item["fiyat"]),
                        ind_toplam if i == 0 else 0, odeme, fis_no=fis, banka=banka,
                    )
                    if ok:
                        basarili += 1
                        urun_cache_stok_dus(int(item["urun_id"]), int(item["adet"]))
                    else:
                        self.mesaj(msg, False)
                        break
            if basarili:
                islem_kaydet(
                    self.aktif_kullanici or self.kullanici_adi or "-",
                    "satis", f"{basarili} urun",
                )
                self.mesaj(f"Tamam — {basarili} urun satildi")
                self.sepet.clear()
                self.spin_indirim.setValue(0)
                self.spin_yuzde.setValue(0)
                self.cmb_odeme.setCurrentIndex(0)
                self._sepet_goster()
                self.yenile_hepsi()
            self.arama_edit.setFocus()
        except Exception as e:
            log_error("Satis", e, __file__, "MagazaEkrani.satisi_tamamla")
            self.mesaj(str(e), False)

    def masraf_kaydet(self):
        try:
            ok, msg = masraf_ekle(self.masraf_tutar.value(), self.masraf_not.text().strip())
            if ok:
                self.masraf_tutar.setValue(0)
                self.masraf_not.clear()
                self.mesaj(msg)
                self.ozet_yenile()
                self.masraf_listesi_yenile()
            else:
                self.mesaj(msg, False)
        except Exception as e:
            log_error("Masraf", e, __file__, "MagazaEkrani.masraf_kaydet")
            self.mesaj(str(e), False)

    def gun_sonu(self):
        try:
            from ui.gun_sonu_dialog import GunSonuDialog

            d = GunSonuDialog(self, self.kullanici_adi)
            if d.exec() and d.kaydedildi:
                self.yenile_hepsi()
        except Exception as e:
            log_error("Gun sonu", e, __file__, "MagazaEkrani.gun_sonu")
            QMessageBox.critical(self, "Hata", str(e))

    def satis_secili_iade(self):
        selected = self.satis_tablo.selectedItems()
        if not selected:
            self.mesaj("Once bir satis satiri secin", False)
            return
        row = selected[0].row()
        fis_no = self.satis_tablo.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if not fis_no:
            # barkod kolonunda fis sakli olmayabilir — detay kolonundan
            item = self.satis_tablo.item(row, 1)
            fis_no = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not fis_no:
            self.mesaj("Fis numarasi bulunamadi", False)
            return
        pin, ok = QInputDialog.getText(
            self, "Yonetim Sifresi", "Iade icin KENDI sifrenizi girin:",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        if not pin_dogrula(pin.strip(), self.kullanici_adi):
            QMessageBox.warning(self, "Hata", "Sifre yanlis")
            return
        if QMessageBox.question(
            self, "Iade Onay",
            f"Fis {fis_no} iade edilsin mi? Stok geri yuklenir.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            ok, msg = fis_iade(fis_no)
            self.mesaj(msg, ok)
            if ok:
                islem_kaydet(
                    self.aktif_kullanici or self.kullanici_adi or "-",
                    "iade", f"Fis {fis_no}",
                )
                urun_cache_sifirla()
            self.yenile_hepsi()
        except Exception as e:
            log_error("Iade", e, __file__, "MagazaEkrani.satis_secili_iade")
            self.mesaj(str(e), False)

    def masraf_secili_sil(self):
        row = self.masraf_tablo.currentRow()
        if row < 0:
            self.mesaj("Masraf secin", False)
            return
        mid = self.masraf_tablo.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if not mid:
            self.mesaj("Masraf id yok", False)
            return
        try:
            ok, msg = masraf_sil(int(mid))
            self.mesaj(msg, ok)
            self.ozet_yenile()
            self.masraf_listesi_yenile()
        except Exception as e:
            log_error("Masraf sil", e, __file__, "MagazaEkrani.masraf_secili_sil")
            self.mesaj(str(e), False)

    # ---- hos geldin notu
    def hos_geldin(self, adi: str):
        try:
            self.lbl_hosgeldin.setText(f"Hos geldin, {adi}")
            self.hosgeldin_bandi.show()
            if getattr(self, "_hosgeldin_timer", None):
                self._hosgeldin_timer.stop()
            else:
                self._hosgeldin_timer = QTimer(self)
                self._hosgeldin_timer.setSingleShot(True)
                self._hosgeldin_timer.timeout.connect(self.hosgeldin_bandi.hide)
            self._hosgeldin_timer.start(5000)
        except Exception as e:
            log_error("Hos geldin", e, __file__, "MagazaEkrani.hos_geldin")

    def hosgeldin_kapat(self):
        if getattr(self, "_hosgeldin_timer", None):
            self._hosgeldin_timer.stop()
        self.hosgeldin_bandi.hide()

    # ---- personel giris / cikis penceresi
    def personel_pencere(self):
        dlg = PersonelDialog(self)
        dlg.giris_ok.connect(self.hos_geldin)
        dlg.giris_ok.connect(self.aktif_yenile)
        dlg.cikis_ok.connect(self.aktif_yenile)
        dlg.exec()
        self.aktif_yenile()

    def aktif_yenile(self):
        try:
            satirlar = aktif_kullanicilar()
            adlar = sorted({(r.get("kullanici") or "").strip() for r in satirlar} - {""})
            self.lbl_aktif.setText("Aktif: " + (" · ".join(adlar) or "-"))
        except Exception as e:
            log_error("Aktif liste", e, __file__, "MagazaEkrani.aktif_yenile")

    def ozet_yenile(self):
        try:
            o = gunluk_ozet()
            self.lbl_ciro.setText(f"Ciro: {o['ciro']:,.0f} TL")
            self.lbl_nakit.setText(f"Nakit: {o.get('nakit', 0):,.0f} TL")
            self.lbl_kart.setText(f"Kart: {o.get('kart', 0):,.0f} TL")
            self.lbl_masraf.setText(f"Masraf: {o.get('masraf', 0):,.0f} TL")
            self.lbl_net.setText(f"Net: {o.get('net', 0):,.0f} TL")
            try:
                from core.gun_sonu_servis import devir_ozeti

                d = devir_ozeti()
                etiket = "Dunku devir"
                if d.get("onceki_tarih"):
                    etiket = f"Devir ({d['onceki_tarih']})"
                self.lbl_devir.setText(f"{etiket}: {d.get('onceki_devir', 0):,.0f} TL")
            except Exception:
                pass
        except Exception as e:
            log_error("Ozet", e, __file__, "MagazaEkrani.ozet_yenile")

    def satis_listesi_yenile(self):
        try:
            gruplar = bugunku_satislar()
            self.satis_tablo.setRowCount(0)
            for g in gruplar:
                fis = g.get("fis_no")
                odeme = g.get("odeme_tipi") or ""
                if g.get("banka"):
                    odeme = f"{odeme}/{g.get('banka')}"
                for k in g.get("kalemler") or []:
                    r = self.satis_tablo.rowCount()
                    self.satis_tablo.insertRow(r)
                    kod = k.get("stok_kodu") or ""
                    ad = k.get("urun_adi") or ""
                    adet = k.get("adet") or 0
                    tutar = float(k.get("toplam") or 0)
                    it0 = QTableWidgetItem(str(kod))
                    it0.setData(Qt.ItemDataRole.UserRole, fis)
                    self.satis_tablo.setItem(r, 0, it0)
                    it1 = QTableWidgetItem(str(ad))
                    it1.setData(Qt.ItemDataRole.UserRole, fis)
                    self.satis_tablo.setItem(r, 1, it1)
                    self.satis_tablo.setItem(r, 2, QTableWidgetItem(str(adet)))
                    self.satis_tablo.setItem(r, 3, QTableWidgetItem(f"{tutar:,.0f}"))
                    self.satis_tablo.setItem(r, 4, QTableWidgetItem(str(odeme)))
        except Exception as e:
            log_error("Satis listesi", e, __file__, "MagazaEkrani.satis_listesi_yenile")

    def masraf_listesi_yenile(self):
        try:
            liste = bugunku_masraflar()
            self.masraf_tablo.setRowCount(0)
            for m in liste:
                r = self.masraf_tablo.rowCount()
                self.masraf_tablo.insertRow(r)
                saat = (m.get("tarih") or m.get("olusturma") or "")[:16]
                it0 = QTableWidgetItem(str(saat))
                it0.setData(Qt.ItemDataRole.UserRole, m.get("id"))
                self.masraf_tablo.setItem(r, 0, it0)
                self.masraf_tablo.setItem(r, 1, QTableWidgetItem(str(m.get("aciklama") or "")))
                self.masraf_tablo.setItem(
                    r, 2, QTableWidgetItem(f"{float(m.get('tutar') or 0):,.0f}")
                )
        except Exception as e:
            log_error("Masraf listesi", e, __file__, "MagazaEkrani.masraf_listesi_yenile")

    def islem_listesi_yenile(self):
        """Geriye uyumluluk — satis + masraf listelerini yenile."""
        self.satis_listesi_yenile()
        self.masraf_listesi_yenile()

    def yenile_hepsi(self):
        self._kategorileri_doldur(True)
        self.ozet_yenile()
        self.satis_listesi_yenile()
        self.masraf_listesi_yenile()
        self._bekleyen_yenile()
        self.aktif_yenile()
        # stok uyari bandi kaldirildi

    # ---- bekleyen kanal ayirmalari
    def _bekleyen_yenile(self):
        try:
            self._bekleyen = [b for b in bekleyen_ayirmalar() if b.get("durum") == "bekliyor"]
            self._uyari_bandi_doldur()
        except Exception as e:
            log_error("Bekleyen ayirma liste", e, __file__, "MagazaEkrani._bekleyen_yenile")

    def _uyari_bandi_doldur(self):
        # Baslik satiri (index 0) kalir, diger satirlar temizlenir
        while self.uyari_kutu.count() > 1:
            it = self.uyari_kutu.takeAt(1)
            w = it.widget()
            if w:
                w.deleteLater()
        if not self._bekleyen:
            self.uyari_bandi.hide()
            return
        for b in self._bekleyen:
            satir = QFrame()
            h = QHBoxLayout(satir)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            metin = (
                f"{b.get('ad') or '?'} — {b.get('stok_kodu') or '-'} — "
                f"Beden/Numara: {b.get('beden_goster') or '-'} — "
                f"Barkod: {b.get('barkod') or '-'} — {b.get('kanal')} satisi {b.get('adet')} adet, "
                f"magaza stoku {b.get('ana_stok')}"
            )
            lbl = QLabel(metin)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color:#000000; font-size:10pt; font-weight:600; border:none;")
            h.addWidget(lbl, 1)
            btn = QPushButton("Ayır")
            btn.setStyleSheet(_btn("birincil"))
            btn.clicked.connect(lambda _, bid=b["id"]: self._urunu_ayir(bid))
            h.addWidget(btn)
            self.uyari_kutu.addWidget(satir)
        self.uyari_bandi.show()

    def _urunu_ayir(self, bek_id: int):
        kayit = next((b for b in self._bekleyen if b.get("id") == bek_id), {})
        dlg = AyirOnayDialog(self, kayit, getattr(self, "kullanici_adi", "") or "")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        ok, msg = bekleyen_ayirma_yap(bek_id, ayiran=dlg._onaylanan)
        self.mesaj(msg, ok)
        self._bekleyen_yenile()
