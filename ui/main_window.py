from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QStackedWidget,
)

from core.config import APP_NAME, APP_ICON_PNG
from core.worker import WorkerThread
from engines.tts_engine import TTSEngine
from engines.stt_engine import STTEngine
from engines.sketch_engine import SketchEngine
from ui.views.tts_view import TTSView
from ui.views.stt_view import STTView
from ui.views.sketch_view import SketchView
from ui.views.dubbing_view import DubbingView
from ui.views.settings_view import SettingsView


class MainWindow(QMainWindow):
    """Main application window with 220px fixed sidebar and view router."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME}")
        if APP_ICON_PNG.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PNG)))
        self.resize(1150, 780)
        self.setMinimumSize(950, 640)

        # Initialize AI Engines
        self.tts_engine = TTSEngine()
        self.stt_engine = STTEngine()
        self.sketch_engine = SketchEngine()
        self._init_worker: Optional[WorkerThread] = None

        self._setup_ui()
        self._auto_init_local_models()

    def _setup_ui(self) -> None:
        root_widget = QWidget(self)
        root_widget.setObjectName("rootWidget")
        self.setCentralWidget(root_widget)

        root_layout = QHBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Sidebar (Fixed 220px, 12px H-padding, 20px V-padding) ---
        sidebar = QFrame()
        sidebar.setObjectName("sidebarFrame")
        sidebar.setFixedWidth(220)

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 20, 12, 20)
        sidebar_layout.setSpacing(8)

        # App Brand Header
        brand_widget = QWidget()
        brand_layout = QHBoxLayout(brand_widget)
        brand_layout.setContentsMargins(4, 0, 8, 12)
        brand_layout.setSpacing(10)

        if APP_ICON_PNG.exists():
            logo_label = QLabel()
            pixmap = QPixmap(str(APP_ICON_PNG)).scaled(26, 26, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pixmap)
            brand_layout.addWidget(logo_label)

        app_title = QLabel(APP_NAME)
        app_title.setObjectName("appTitle")

        brand_layout.addWidget(app_title)
        brand_layout.addStretch()
        sidebar_layout.addWidget(brand_widget)

        # Navigation Items
        self.btn_nav_tts = QPushButton("🔊 Text-to-Speech")
        self.btn_nav_tts.setProperty("class", "nav-btn")
        self.btn_nav_tts.setProperty("active", "true")
        self.btn_nav_tts.clicked.connect(lambda: self._switch_view(0))

        self.btn_nav_stt = QPushButton("🎙 Speech-to-Text")
        self.btn_nav_stt.setProperty("class", "nav-btn")
        self.btn_nav_stt.setProperty("active", "false")
        self.btn_nav_stt.clicked.connect(lambda: self._switch_view(1))

        self.btn_nav_sketch = QPushButton("✍ Video vẽ tay")
        self.btn_nav_sketch.setProperty("class", "nav-btn")
        self.btn_nav_sketch.setProperty("active", "false")
        self.btn_nav_sketch.clicked.connect(lambda: self._switch_view(2))

        self.btn_nav_dubbing = QPushButton("🎬 Phụ đề Video")
        self.btn_nav_dubbing.setProperty("class", "nav-btn")
        self.btn_nav_dubbing.setProperty("active", "false")
        self.btn_nav_dubbing.clicked.connect(lambda: self._switch_view(3))

        sidebar_layout.addWidget(self.btn_nav_tts)
        sidebar_layout.addWidget(self.btn_nav_stt)
        sidebar_layout.addWidget(self.btn_nav_sketch)
        sidebar_layout.addWidget(self.btn_nav_dubbing)

        sidebar_layout.addStretch(1)

        # Settings button at bottom-left of sidebar
        self.btn_nav_settings = QPushButton("⚙ Cài đặt")
        self.btn_nav_settings.setProperty("class", "nav-btn")
        self.btn_nav_settings.setProperty("active", "false")
        self.btn_nav_settings.clicked.connect(lambda: self._switch_view(4))
        sidebar_layout.addWidget(self.btn_nav_settings)

        root_layout.addWidget(sidebar)

        # --- Content Area (QStackedWidget Router) ---
        self.stack = QStackedWidget()
        self.tts_view = TTSView(self.tts_engine)
        self.stt_view = STTView(self.stt_engine)
        self.sketch_view = SketchView(self.sketch_engine)
        self.dubbing_view = DubbingView(self.stt_engine, self.tts_engine)
        self.settings_view = SettingsView(
            tts_engine=self.tts_engine,
            stt_engine=self.stt_engine,
            sketch_engine=self.sketch_engine,
            current_model=self.tts_engine.current_model_type,
        )
        self.settings_view.model_changed.connect(self._on_model_changed)

        self.stack.addWidget(self.tts_view)       # index 0
        self.stack.addWidget(self.stt_view)       # index 1
        self.stack.addWidget(self.sketch_view)    # index 2
        self.stack.addWidget(self.dubbing_view)   # index 3 (Tab 4)
        self.stack.addWidget(self.settings_view)  # index 4

        root_layout.addWidget(self.stack, 1)

    def _switch_view(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

        # Update button active states and refresh styles
        buttons = [
            self.btn_nav_tts,
            self.btn_nav_stt,
            self.btn_nav_sketch,
            self.btn_nav_dubbing,
            self.btn_nav_settings,
        ]
        for i, btn in enumerate(buttons):
            is_active = (i == index)
            btn.setProperty("active", "true" if is_active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if index == 0:
            self.tts_view.refresh_state()
        elif index == 3 and hasattr(self, "dubbing_view"):
            self.dubbing_view.refresh_state()
        elif index == 4 and hasattr(self, "settings_view"):
            self.settings_view.refresh_state()

    def _on_model_changed(self, model_key: str) -> None:
        """Handle model switch from settings: update engine and refresh TTS view."""
        self.tts_engine.set_model_type(model_key)
        self.tts_view.refresh_state()

    def _auto_init_local_models(self) -> None:
        """Automatically load any pre-downloaded local models into memory on app launch."""
        def _loader(progress_callback=None):
            # 1. TTS current model (VieNeu by default)
            try:
                if self.tts_engine.is_model_downloaded() and not self.tts_engine.is_loaded:
                    self.tts_engine.load_model()
            except Exception as e:
                print(f"[AutoInit] Lỗi nạp mô hình TTS: {e}")

            # 2. Whisper STT model
            try:
                if self.stt_engine.is_model_downloaded() and not self.stt_engine.is_loaded:
                    self.stt_engine.load_model()
            except Exception as e:
                print(f"[AutoInit] Lỗi nạp mô hình STT: {e}")

            # 3. Sketch model
            try:
                if self.sketch_engine.is_model_downloaded() and not getattr(self.sketch_engine, "is_loaded", False):
                    self.sketch_engine.load_model()
            except Exception as e:
                print(f"[AutoInit] Lỗi nạp mô hình Sketch: {e}")
            return True

        self._init_worker = WorkerThread(_loader)
        self._init_worker.finished_task.connect(self._on_auto_init_finished)
        self._init_worker.start()

    def _on_auto_init_finished(self, _=None) -> None:
        if hasattr(self, "settings_view"):
            self.settings_view.refresh_state()
        if hasattr(self, "tts_view"):
            self.tts_view.refresh_state()

    def closeEvent(self, event) -> None:
        """Safely clean up workers and release AI engine memory upon exit."""
        if hasattr(self, "_init_worker") and self._init_worker is not None:
            try:
                self._init_worker.quit()
                self._init_worker.wait(500)
            except Exception:
                pass

        if hasattr(self, "tts_view") and hasattr(self.tts_view, "_cleanup_worker"):
            self.tts_view._cleanup_worker()
        if hasattr(self, "stt_view"):
            if hasattr(self.stt_view, "_cleanup_worker"):
                self.stt_view._cleanup_worker()
            if hasattr(self.stt_view, "_cleanup_trans_worker"):
                self.stt_view._cleanup_trans_worker()
        if hasattr(self, "sketch_view") and hasattr(self.sketch_view, "_cleanup_worker"):
            self.sketch_view._cleanup_worker()
        if hasattr(self, "dubbing_view") and hasattr(self.dubbing_view, "_cleanup_worker"):
            self.dubbing_view._cleanup_worker()

        if hasattr(self, "tts_engine"):
            self.tts_engine.unload_model()
        if hasattr(self, "stt_engine"):
            self.stt_engine.unload_model()

        super().closeEvent(event)
