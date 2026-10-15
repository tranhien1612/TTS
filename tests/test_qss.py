import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow

app = QApplication([])
win = MainWindow()

btn = win.tts_view.btn_synthesize
style = """
QPushButton {
    background-color: #4F46E5;
    color: #FFFFFF;
    font-size: 14px;
    font-weight: 700;
    padding: 10px 22px;
    border-radius: 8px;
    border: 1px solid #4338CA;
}
QPushButton:hover {
    background-color: #4338CA;
}
QPushButton:disabled {
    background-color: #E2E8F0;
    color: #94A3B8;
}
"""
btn.setStyleSheet(style)
win.show()
app.processEvents()

pix = btn.grab()
img = pix.toImage()
print("Rendered corner (20, 20):", img.pixelColor(20, 20).name())
print("Rendered center:", img.pixelColor(btn.width()//2, btn.height()//2).name())
win.close()
