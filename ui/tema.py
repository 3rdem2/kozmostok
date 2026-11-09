# -*- coding: utf-8 -*-
"""Kozmosize tek kaynaklı tema sistemi (PyQt6)."""

from __future__ import annotations

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication, QSpinBox

# --- Renk paleti ---
BG = "#0A0A0A"
PANEL = "#121212"
PANEL_2 = "#171717"
BORDER = "#262626"
BORDER_2 = "#333333"

ACCENT = "#C41E3A"
ACCENT_H = "#E63950"
ACCENT_D = "#8E1528"

TEXT = "#F2EFE9"
TEXT_2 = "#C9C5BE"
MUTED = "#8C8C8C"

OK = "#3E7C59"
WARN = "#C9A227"
DANGER = "#C41E3A"
INFO = "#5B7C99"

SIZE_11 = 11
SIZE_12 = 12
SIZE_13 = 13
SIZE_15 = 15
SIZE_20 = 20
SIZE_28 = 28

DISPLAY_FONT_CANDIDATES = [
    "Oswald",
    "Bahnschrift SemiCondensed",
    "Bahnschrift",
    "Segoe UI Semibold",
]
BODY_FONT_CANDIDATES = ["Inter", "Segoe UI", "Arial"]
MONO_FONT_CANDIDATES = ["JetBrains Mono", "Cascadia Mono", "Consolas"]


def _font_fallback(candidates: list[str]) -> str:
    if QApplication.instance() is None:
        return candidates[-1]
    try:
        installed = {f.lower(): f for f in QFontDatabase.families()}
    except Exception:
        return candidates[-1]
    for name in candidates:
        found = installed.get(name.lower())
        if found:
            return found
    return candidates[-1]


def secili_font_adlari() -> tuple[str, str, str]:
    return (
        _font_fallback(DISPLAY_FONT_CANDIDATES),
        _font_fallback(BODY_FONT_CANDIDATES),
        _font_fallback(MONO_FONT_CANDIDATES),
    )


def baslik_font(punto: int = SIZE_20) -> QFont:
    ad, _, _ = secili_font_adlari()
    f = QFont(ad, punto)
    f.setWeight(QFont.Weight.DemiBold)
    f.setCapitalization(QFont.Capitalization.AllUppercase)
    return f


def govde_font(punto: int = SIZE_12) -> QFont:
    _, ad, _ = secili_font_adlari()
    f = QFont(ad, punto)
    f.setWeight(QFont.Weight.Normal)
    return f


def sayi_font(punto: int = SIZE_12) -> QFont:
    _, _, ad = secili_font_adlari()
    f = QFont(ad, punto)
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setFixedPitch(True)
    return f


def btn_qss(
    variant: str = "ikincil",
    min_height: int = 34,
    radius: int = 2,
) -> str:
    """Yerel butonlar için tekrar kullanılabilir QSS bloğu üretir."""
    variants = {
        "birincil": (ACCENT, ACCENT_H, ACCENT_D, TEXT, ACCENT),
        "ikincil": ("transparent", PANEL_2, PANEL, TEXT, BORDER_2),
        "hayalet": ("transparent", PANEL_2, PANEL, TEXT_2, "transparent"),
        "tehlike": (DANGER, ACCENT_H, ACCENT_D, TEXT, DANGER),
        "danger": (DANGER, ACCENT_H, ACCENT_D, TEXT, DANGER),
        "ok": (OK, "#4B9369", "#2F5E44", TEXT, OK),
    }
    bg, hov, prs, fg, br = variants.get(variant, variants["ikincil"])
    border_width = 0 if variant == "hayalet" else 1
    return (
        "QPushButton {"
        f"background:{bg}; color:{fg}; border:{border_width}px solid {br};"
        f"border-radius:{radius}px; min-height:{min_height}px;"
        "padding:8px 16px; font-weight:700; letter-spacing:1px;"
        "}"
        f"QPushButton:hover {{ background:{hov}; }}"
        f"QPushButton:pressed {{ background:{prs}; }}"
        "QPushButton:focus { border:1px solid " + ACCENT_H + "; }"
        "QPushButton:disabled { background:" + PANEL + "; color:" + MUTED + "; border-color:" + BORDER + "; }"
    )


def kontrol_qss() -> str:
    return (
        "QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {"
        f"background:{PANEL_2}; color:{TEXT}; border:1px solid {BORDER_2};"
        "border-radius:2px; padding:6px 10px; min-height:34px;"
        "selection-background-color:" + ACCENT + ";"
        "}"
        "QSpinBox, QDoubleSpinBox {"
        f"background:{PANEL_2}; color:{TEXT}; border:1px solid {BORDER_2};"
        "border-radius:2px; padding:0px 6px; min-height:34px;"
        "selection-background-color:" + ACCENT + ";"
        "}"
        "QSpinBox QLineEdit, QDoubleSpinBox QLineEdit {"
        f"background:transparent; color:{TEXT}; border:none; padding:0; margin:0;"
        "}"
        "QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {"
        f"border:1px solid {ACCENT};"
        "}"
        "QComboBox::drop-down {"
        f"width:20px; border-left:1px solid {BORDER}; background:{PANEL};"
        "}"
        "QComboBox QAbstractItemView {"
        f"background:{PANEL}; color:{TEXT}; border:1px solid {BORDER_2};"
        f"selection-background-color:{ACCENT};"
        "}"
    )


def tablo_qss() -> str:
    return (
        "QTableWidget {"
        f"background:{PANEL}; alternate-background-color:{PANEL_2}; color:{TEXT};"
        f"gridline-color:#3A3A3A; border:1px solid {BORDER};"
        "outline: none;"
        "}"
        "QTableWidget::item {"
        "padding: 4px 8px;"
        "border-right: 1px solid #2E2E2E;"
        "border-bottom: 1px solid #2E2E2E;"
        "}"
        "QHeaderView::section {"
        f"background:{PANEL_2}; color:{TEXT};"
        "border: none;"
        "border-right: 1px solid #3A3A3A;"
        f"border-bottom: 1px solid {ACCENT};"
        "padding: 8px 8px; font-weight: 700;"
        "}"
        "QTableWidget::item:selected {"
        f"background:{ACCENT_D}; color:{TEXT};"
        "}"
    )


def _app_qss() -> str:
    display, body, mono = secili_font_adlari()
    return f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: "{body}", "Inter", "Segoe UI", "Arial";
    font-size: {SIZE_12}px;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QFrame#kart, QFrame.kart {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 2px;
}}
QLabel {{ background: transparent; color: {TEXT}; }}
QLabel#baslik {{
    color: {TEXT};
    font-family: "{display}", "Bahnschrift", "Segoe UI Semibold";
    font-size: {SIZE_20}px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
}}
QLabel#vurgu {{ color: {ACCENT_H}; font-size: {SIZE_15}px; font-weight: 700; }}
QLabel#muted {{ color: {MUTED}; font-size: {SIZE_11}px; }}
QLabel#etiket {{ color: {TEXT_2}; font-size: {SIZE_12}px; font-weight: 600; letter-spacing: 1px; }}

{kontrol_qss()}

QPushButton {{
    background: transparent;
    color: {TEXT};
    border: 1px solid {BORDER_2};
    border-radius: 2px;
    min-height: 34px;
    padding: 8px 16px;
    font-size: {SIZE_12}px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QPushButton:hover {{ background: {PANEL_2}; }}
QPushButton:pressed {{ background: {PANEL}; }}
QPushButton:focus {{ border: 1px solid {ACCENT_H}; }}
QPushButton:disabled {{ background: {PANEL}; color: {MUTED}; border-color: {BORDER}; }}

QPushButton#birincil {{ background: {ACCENT}; border-color: {ACCENT}; color: {TEXT}; }}
QPushButton#birincil:hover {{ background: {ACCENT_H}; border-color: {ACCENT_H}; }}
QPushButton#birincil:pressed {{ background: {ACCENT_D}; border-color: {ACCENT_D}; }}

QPushButton#ikincil {{ background: transparent; border-color: {BORDER_2}; color: {TEXT}; }}
QPushButton#ikincil:hover {{ background: {PANEL_2}; }}
QPushButton#ikincil:pressed {{ background: {PANEL}; }}

QPushButton#hayalet {{ background: transparent; border: none; color: {TEXT_2}; }}
QPushButton#hayalet:hover {{ color: {TEXT}; background: {PANEL_2}; }}
QPushButton#hayalet:pressed {{ background: {PANEL}; }}

QPushButton#tehlike, QPushButton#danger {{ background: {DANGER}; border-color: {DANGER}; color: {TEXT}; }}
QPushButton#tehlike:hover, QPushButton#danger:hover {{ background: {ACCENT_H}; border-color: {ACCENT_H}; }}
QPushButton#tehlike:pressed, QPushButton#danger:pressed {{ background: {ACCENT_D}; border-color: {ACCENT_D}; }}

QPushButton#ok {{ background: {OK}; border-color: {OK}; color: {TEXT}; }}
QPushButton#ok:hover {{ background: #4B9369; border-color: #4B9369; }}
QPushButton#ok:pressed {{ background: #2F5E44; border-color: #2F5E44; }}

{tablo_qss()}
QTableWidget {{ font-family: "{mono}", "JetBrains Mono", "Consolas"; font-size: {SIZE_11}px; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; background: {BG}; }}
QTabBar::tab {{
    background: {PANEL}; color: {MUTED};
    border: 1px solid {BORDER}; padding: 8px 14px;
    margin-right: 2px; font-weight: 700; letter-spacing: 1px;
}}
QTabBar::tab:selected {{ color: {TEXT}; background: {PANEL_2}; border-bottom: 2px solid {ACCENT}; }}

QScrollBar:vertical {{ width: 10px; background: {BG}; }}
QScrollBar::handle:vertical {{ background: {BORDER_2}; min-height: 30px; border-radius: 3px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar:horizontal {{ height: 10px; background: {BG}; }}
QScrollBar::handle:horizontal {{ background: {BORDER_2}; min-width: 30px; border-radius: 3px; }}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT}; }}

QCheckBox, QRadioButton {{ spacing: 8px; color: {TEXT}; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px; height: 14px; border: 1px solid {BORDER_2}; background: {PANEL};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QGroupBox {{ border: 1px solid {BORDER}; border-radius: 2px; margin-top: 10px; padding-top: 12px; }}
QGroupBox::title {{ color: {TEXT_2}; subcontrol-origin: margin; left: 8px; padding: 0 4px; }}

QToolTip {{ background: {PANEL_2}; color: {TEXT}; border: 1px solid {BORDER_2}; padding: 4px 6px; }}
QMenu {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {ACCENT_D}; }}

QProgressBar {{
    background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 2px; text-align: center;
}}
QProgressBar::chunk {{ background: {ACCENT}; }}

QMessageBox {{ background: {BG}; }}
QMessageBox QLabel {{ color: {TEXT}; }}
"""


APP_QSS = _app_qss()


def tema_uygula(app: QApplication) -> None:
    """Uygulama geneline Kozmosize temasını uygular."""
    try:
        app.setStyle("Fusion")
        app.setFont(govde_font(SIZE_12))
        app.setStyleSheet(_app_qss())
    except Exception:
        pass


class GuvenliSpin(QSpinBox):
    """
    Kart / form icinde tasmayan adet kutusu.
    Oklar kutu siniri icinde; varsayilan aralik 0-999999.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 999999)
        self.setValue(0)
        self.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        self.setFixedHeight(26)
        self.setMinimumWidth(52)
        self.setStyleSheet(
            "QSpinBox {"
            "  background: #121212; color: #F2EFE9;"
            "  border: 1px solid #333333; border-radius: 2px;"
            "  padding-right: 2px; font-size: 11px;"
            "  min-height: 24px; max-height: 26px;"
            "}"
            "QSpinBox::up-button {"
            "  subcontrol-origin: border; subcontrol-position: top right;"
            "  width: 16px; height: 12px;"
            "  border-left: 1px solid #333333; background: #171717;"
            "}"
            "QSpinBox::down-button {"
            "  subcontrol-origin: border; subcontrol-position: bottom right;"
            "  width: 16px; height: 12px;"
            "  border-left: 1px solid #333333; background: #171717;"
            "}"
            "QSpinBox::up-arrow, QSpinBox::down-arrow { width: 7px; height: 7px; }"
        )
