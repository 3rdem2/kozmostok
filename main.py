# -*- coding: utf-8 -*-
"""
KOZMOSIZE Stok & Kasa Programi
Giris noktasi
"""

import sys
from pathlib import Path

# Proje kokunu path'e ekle
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt

from core.database import init_database, db_baglanti_ayarla
from core.logger import log_error, log_info
from ui.main_window import MainWindow
from ui.tema import tema_uygula


def main():
    try:
        # Yuksek DPI destegi
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        app = QApplication(sys.argv)
        app.setApplicationName("KOZMOSIZE Stok")
        tema_uygula(app)

        # Veritabani hazirla
        if not init_database():

            QMessageBox.critical(
                None,
                "Veritabani Hatasi",
                "Veritabani olusturulamadi.\nlogs/hatalar.log dosyasini kontrol edin."
            )
            return 1

        log_info("Program baslatildi.")

        pencere = MainWindow()
        pencere.show()

        kod = app.exec()
        try:
            from core.database import havuz_bosalt

            havuz_bosalt()
        except Exception:
            pass
        return kod

    except Exception as e:
        log_error("Program baslatma hatasi", e, __file__, "main")
        try:
            QMessageBox.critical(
                None,
                "Kritik Hata",
                f"Program baslatilamadi.\n\n{e}\n\nDetay: logs/hatalar.log"
            )
        except Exception:
            print(f"Kritik hata: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
