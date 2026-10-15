import os
import sys
import ctypes
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon

from core.config import APP_NAME, APP_ICON_PNG, APP_ICON_PATH
from ui.main_window import MainWindow
from ui.styles import GLOBAL_STYLESHEET


def main() -> None:
    # Windows taskbar icon grouping support
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("neuaudio.studio.app")
    except Exception:
        pass

    # Initialize Application
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    # Set Application Icon
    icon_file = APP_ICON_PNG if APP_ICON_PNG.exists() else APP_ICON_PATH
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    # Set default modern typography
    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    # Inject Centralized Dark Minimalist Stylesheet
    app.setStyleSheet(GLOBAL_STYLESHEET)

    # Launch Root Window
    window = MainWindow()
    if icon_file.exists():
        window.setWindowIcon(QIcon(str(icon_file)))
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
