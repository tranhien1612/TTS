import os
import sys
import signal
import ctypes
from pathlib import Path

_base = Path(__file__).resolve().parent
_hf_home = _base / "models" / "hf"
_hf_home.mkdir(parents=True, exist_ok=True)


from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import QTimer

from core.config import APP_NAME, APP_ICON_PNG, APP_ICON_PATH, cleanup_outputs_dir, force_kill_app
from ui.main_window import MainWindow
from ui.styles import GLOBAL_STYLESHEET


def main() -> None:
    # Register Ctrl+C (SIGINT) and SIGTERM handler to force-kill app immediately
    signal.signal(signal.SIGINT, lambda *args: force_kill_app())
    try:
        signal.signal(signal.SIGTERM, lambda *args: force_kill_app())
    except Exception:
        pass

    # Clean up old generated outputs (audio, video, subtitles, etc.) to prevent disk bloat
    deleted_files = cleanup_outputs_dir()
    if deleted_files > 0:
        print(f"[Cleanup] Đã dọn dẹp {deleted_files} tệp cũ trong thư mục outputs/")

    # Windows taskbar icon grouping support
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("neuaudio.studio.app")
    except Exception:
        pass

    # Initialize Application
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.aboutToQuit.connect(force_kill_app)

    # Wake Python interpreter periodically so SIGINT / Ctrl+C is received during Qt event loop
    sig_timer = QTimer()
    sig_timer.timeout.connect(lambda: None)
    sig_timer.start(200)

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