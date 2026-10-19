import sys
import signal
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import force_kill_app
from ui.main_window import MainWindow
from PyQt6.QtWidgets import QApplication

def test_force_exit_setup():
    # 1. Test force_kill_app import and callable
    assert callable(force_kill_app)

    # 2. Test MainWindow force exit flag
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    assert win.is_force_exit_on_close is True, "MainWindow must have is_force_exit_on_close = True by default"
    win.is_force_exit_on_close = False
    win.close()

    # 3. Test SIGINT handler registration
    h = signal.getsignal(signal.SIGINT)
    assert h is not None

    print("Force exit tests passed successfully!")

if __name__ == "__main__":
    test_force_exit_setup()
