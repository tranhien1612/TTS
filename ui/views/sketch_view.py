import os
import shutil
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QThread, QByteArray, QSize, QEvent
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QCursor, QDragEnterEvent, QDropEvent
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QSlider,
    QComboBox,
    QProgressBar,
    QFileDialog,
    QFrame,
    QScrollArea,
    QStackedLayout,
    QMessageBox,
    QApplication,
)

from core.config import OUTPUTS_DIR
from engines.sketch_engine import SketchEngine
from ui.components import Card, VideoPlayer, VideoContainer, VideoControlsOverlay, EditableSliderBadge
from ui.styles import (
    PRIMARY_BUTTON_STYLE,
    SECONDARY_BUTTON_STYLE,
    BG_MAIN,
    BG_SURFACE,
    BG_SUBTLE,
    ACCENT_PRIMARY,
    ACCENT_LIGHT,
    ACCENT_BORDER,
    TEXT_MAIN,
    TEXT_MUTED,
    BORDER_COLOR,
    BORDER_INPUT,
)


UPLOAD_TRAY_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#6366F1" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"></path>
  <polyline points="7 9 12 4 17 9"></polyline>
  <line x1="12" y1="4" x2="12" y2="16"></line>
</svg>"""


class NoWheelSlider(QSlider):
    """QSlider that ignores mouse wheel events to prevent accidental value changes during page scrolling."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse wheel events to prevent accidental value changes during page scrolling."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class ImageDropZone(QFrame):
    """Interactive drag-and-drop & click-to-upload card matching the light minimalist theme.

    Displays only the image when selected, and clicking anywhere opens a file dialog to pick another image.
    """

    image_selected = pyqtSignal(Path)
    image_cleared = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # self.setToolTip("Nhấn để chọn hình ảnh từ máy tính (hoặc kéo thả ảnh vào đây)")
        self.image_path: Optional[Path] = None
        self._original_pixmap: Optional[QPixmap] = None
        self._is_drag_over = False

        self._setup_ui()
        self._update_style()

    def _setup_ui(self) -> None:
        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)

        # --- Page 0: Empty Dropzone state ---
        self.empty_widget = QWidget()
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setContentsMargins(20, 20, 20, 20)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Centered clean guidance text (no borders, clean transparent background)
        self.label_drop = QLabel("Nhấn vào khung hình hoặc kéo thả hình ảnh để tải lên")
        self.label_drop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_drop.setStyleSheet("color: #64748B; font-size: 13px; font-weight: 500; border: none; background: transparent;")
        empty_layout.addWidget(self.label_drop)

        self.stack.addWidget(self.empty_widget)

        # --- Page 1: Loaded Image Preview state (ONLY image display, fully edge-fitted) ---
        self.preview_widget = QWidget()
        preview_layout = QVBoxLayout(self.preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        preview_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Image preview label (prominent, centered, clean, strictly borderless)
        self.image_preview_label = QLabel()
        self.image_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview_label.setStyleSheet("border: none; background-color: transparent;")
        preview_layout.addWidget(self.image_preview_label)

        self.stack.addWidget(self.preview_widget)
        self.stack.setCurrentIndex(0)

    def _update_style(self) -> None:
        self.setObjectName("imageDropZone")
        if self._is_drag_over:
            self.setStyleSheet(f"""
                #imageDropZone {{
                    background-color: {ACCENT_LIGHT};
                    border: 2px dashed {ACCENT_PRIMARY};
                    border-radius: 12px;
                }}
                #imageDropZone QLabel {{
                    border: none;
                    background: transparent;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                #imageDropZone {{
                    background-color: {BG_MAIN};
                    border: 2px dashed #CBD5E1;
                    border-radius: 12px;
                }}
                #imageDropZone:hover {{
                    border-color: {ACCENT_PRIMARY};
                    background-color: #F8FAFC;
                }}
                #imageDropZone QLabel {{
                    border: none;
                    background: transparent;
                }}
            """)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_preview()

    def _update_preview(self) -> None:
        """Dynamically scale the loaded image to fit the container while preserving aspect ratio."""
        if self._original_pixmap and not self._original_pixmap.isNull():
            w = max(10, self.width())
            h = max(10, self.height())
            scaled_pix = self._original_pixmap.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_preview_label.setPixmap(scaled_pix)

    def mousePressEvent(self, event) -> None:
        if not self.isEnabled():
            return
        if event.button() == Qt.MouseButton.LeftButton:
            # Clicking anywhere on the card allows picking another image
            self._browse_image()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if not self.isEnabled():
            return
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                ext = Path(url.toLocalFile()).suffix.lower()
                if ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
                    event.acceptProposedAction()
                    self._is_drag_over = True
                    self._update_style()
                    return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._is_drag_over = False
        self._update_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._is_drag_over = False
        self._update_style()
        if not self.isEnabled():
            return
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp", ".bmp"] and path.exists():
                self.load_image(path)
                event.acceptProposedAction()
                return

    def _browse_image(self) -> None:
        if not self.isEnabled():
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn hình ảnh đầu vào",
            "",
            "Hình ảnh (*.png *.jpg *.jpeg *.webp *.bmp *.PNG *.JPG *.JPEG *.WEBP *.BMP)",
        )
        if file_path:
            self.load_image(Path(file_path))

    def load_image(self, path: Path) -> None:
        """Load and display the selected image inside the card."""
        if not path.exists():
            return
        self.image_path = path

        # Read pixmap and scale to fit card
        self._original_pixmap = QPixmap(str(path))
        if not self._original_pixmap.isNull():
            self._update_preview()
            self.stack.setCurrentIndex(1)
            self.image_selected.emit(path)

    def clear_image(self) -> None:
        """Clear currently selected image and return to dropzone."""
        self.image_path = None
        self._original_pixmap = None
        self.image_preview_label.clear()
        self.stack.setCurrentIndex(0)
        self.image_cleared.emit()


class SketchRenderWorker(QThread):
    """Background worker for rendering sketch video via SketchEngine without blocking GUI."""

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        engine: SketchEngine,
        image_path: Path,
        duration: int,
        fps: int,
        device: str,
        encoder: str,
        output_path: Path,
        width: int = 1920,
        height: int = 1080,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.image_path = image_path
        self.duration = max(1, duration)
        self.fps = max(1, fps)
        self.device = device
        self.encoder = encoder
        self.output_path = output_path
        self.width = width
        self.height = height
        self._is_cancelled = False

    def run(self) -> None:
        try:
            def _progress_cb(fraction: float, message: str = "") -> None:
                percent = max(0, min(100, int(fraction * 100)))
                self.progress.emit(percent, message)

            video_path, _ = self.engine.render(
                image_input=self.image_path,
                duration=float(self.duration),
                fps=int(self.fps),
                device=self.device,
                encoder=self.encoder,
                width=int(self.width),
                height=int(self.height),
                output_file=self.output_path,
                progress_callback=_progress_cb,
            )
            self.finished.emit(str(video_path))
        except Exception as e:
            self.error.emit(str(e))


class SketchView(QWidget):
    """Hand-drawn / Sketch video generator view matching Neu Audio Studio design system."""

    def __init__(self, sketch_engine: Optional[SketchEngine] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = sketch_engine or SketchEngine()
        self.selected_image: Optional[Path] = None
        self.current_video_path: Optional[Path] = None
        self.worker: Optional[SketchRenderWorker] = None

        self._setup_ui()
        self._setup_player()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # --- Header Title Row ---
        header_layout = QHBoxLayout()
        header_title = QLabel("Video vẽ tay từ ảnh")
        header_title.setProperty("class", "header-title")
        header_layout.addWidget(header_title)

        # feature_badge = QLabel("Sketch Video Generator")
        # feature_badge.setProperty("class", "badge-accent")
        # header_layout.addWidget(feature_badge)

        header_layout.addStretch(1)
        layout.addLayout(header_layout)

        # ============================================================
        # CARD 1: Chọn ảnh đầu vào (Image Selection Card - Left)
        # ============================================================
        self.image_card = Card()
        self.image_card.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        card1_title = QLabel("Chọn hình ảnh đầu vào")
        card1_title.setProperty("class", "section-title")
        card1_title.setFixedHeight(24)
        self.image_card.addWidget(card1_title)

        # Dropzone widget (Displays only image when selected; click opens browse)
        self.drop_zone = ImageDropZone()
        self.drop_zone.setFixedHeight(280)
        self.drop_zone.image_selected.connect(self._on_image_selected)
        self.drop_zone.image_cleared.connect(self._on_image_cleared)
        self.image_card.addWidget(self.drop_zone)

        # ============================================================
        # CARD 2: Video kết quả (Video Player Card - Right)
        # ============================================================
        self.video_card = Card()
        self.video_card.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        card2_title = QLabel("Video kết quả")
        card2_title.setProperty("class", "section-title")
        card2_title.setFixedHeight(24)
        self.video_card.addWidget(card2_title)

        # Video Player Component with integrated hover controls overlay & click-to-play
        self.video_player = VideoPlayer()
        self.video_player.setFixedHeight(280)
        self.video_card.addWidget(self.video_player)

        # Shortcuts / aliases for backward compatibility and clean wiring
        self.video_container = self.video_player
        self.overlay = self.video_player.overlay
        self.video_widget = self.video_player.video_widget
        self.video_stack = self.video_player.stack
        self.btn_play_pause = self.video_player.btn_play_pause
        self.time_label = self.video_player.time_label
        self.timeline_slider = self.video_player.timeline_slider
        self.player = self.video_player.player
        self.audio_output = self.video_player.audio_output

        # --- Row 1: Gộp image Card và video Card vào cùng 1 hàng (bên trái image, bên phải video) ---
        media_row = QHBoxLayout()
        media_row.setSpacing(16)
        media_row.addWidget(self.image_card, 1)
        media_row.addWidget(self.video_card, 1)
        layout.addLayout(media_row)

        # ============================================================
        # CARD 3: Cấu hình tham số & Tạo video (3 dòng, 2 tham số/dòng)
        # ============================================================
        self.params_card = Card()

        card3_title = QLabel("Cấu hình tham số")
        card3_title.setProperty("class", "section-title")
        self.params_card.addWidget(card3_title)

        params_grid = QGridLayout()
        params_grid.setHorizontalSpacing(24)
        params_grid.setVerticalSpacing(14)
        params_grid.setColumnStretch(0, 0)
        params_grid.setColumnStretch(1, 1)
        params_grid.setColumnStretch(2, 0)
        params_grid.setColumnStretch(3, 1)

        param_lbl_style = "font-weight: 600; font-size: 13px; color: #334155;"
        reset_btn_style = f"""
            QPushButton {{
                background-color: {BG_SUBTLE};
                color: {TEXT_MAIN};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
                padding: 0px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #E2E8F0;
                border-color: {ACCENT_PRIMARY};
                color: {ACCENT_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {ACCENT_LIGHT};
            }}
            QPushButton:disabled {{
                background-color: {BG_SUBTLE};
                color: #94A3B8;
                border-color: {BORDER_COLOR};
            }}
        """

        # ─── DÒNG 1: Thời gian video + Tốc độ khung hình ───
        # Dòng 1 - Trái: Thời gian video (slider + badge + reset)
        duration_label = QLabel("Thời gian video:")
        duration_label.setStyleSheet(param_lbl_style)
        params_grid.addWidget(duration_label, 0, 0)

        duration_ctrl_layout = QHBoxLayout()
        duration_ctrl_layout.setSpacing(10)

        self.duration_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.duration_slider.setRange(1, 120)
        self.duration_slider.setValue(10)
        self.duration_slider.valueChanged.connect(self._on_duration_changed)
        duration_ctrl_layout.addWidget(self.duration_slider, 1)

        self.duration_badge = EditableSliderBadge(self.duration_slider, suffix="s")
        self.duration_badge.setFixedWidth(64)
        duration_ctrl_layout.addWidget(self.duration_badge)

        self.btn_reset_duration = QPushButton("↻")
        self.btn_reset_duration.setProperty("class", "secondary-btn")
        self.btn_reset_duration.setStyleSheet(reset_btn_style)
        self.btn_reset_duration.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_duration.setFixedSize(32, 32)
        # self.btn_reset_duration.setToolTip("Khôi phục mặc định 10s")
        self.btn_reset_duration.clicked.connect(lambda: self.duration_slider.setValue(10))
        duration_ctrl_layout.addWidget(self.btn_reset_duration)

        params_grid.addLayout(duration_ctrl_layout, 0, 1)

        # Dòng 1 - Phải: Tốc độ khung hình (slider + badge + reset)
        fps_label = QLabel("Tốc độ khung hình (FPS):")
        fps_label.setStyleSheet(param_lbl_style)
        params_grid.addWidget(fps_label, 0, 2)

        fps_ctrl_layout = QHBoxLayout()
        fps_ctrl_layout.setSpacing(10)

        self.fps_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.fps_slider.setRange(0, 60)
        self.fps_slider.setValue(30)
        self.fps_slider.valueChanged.connect(self._on_fps_changed)
        fps_ctrl_layout.addWidget(self.fps_slider, 1)

        self.fps_badge = EditableSliderBadge(self.fps_slider, suffix=" fps")
        self.fps_badge.setFixedWidth(64)
        fps_ctrl_layout.addWidget(self.fps_badge)

        self.btn_reset_fps = QPushButton("↻")
        self.btn_reset_fps.setProperty("class", "secondary-btn")
        self.btn_reset_fps.setStyleSheet(reset_btn_style)
        self.btn_reset_fps.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_fps.setFixedSize(32, 32)
        # self.btn_reset_fps.setToolTip("Khôi phục mặc định 30 FPS")
        self.btn_reset_fps.clicked.connect(lambda: self.fps_slider.setValue(30))
        fps_ctrl_layout.addWidget(self.btn_reset_fps)

        params_grid.addLayout(fps_ctrl_layout, 0, 3)

        # ─── DÒNG 2: Width + Height ───
        # Dòng 2 - Trái: Width [64, 3840], default 1920
        width_label = QLabel("Width (px):")
        width_label.setStyleSheet(param_lbl_style)
        params_grid.addWidget(width_label, 1, 0)

        width_ctrl_layout = QHBoxLayout()
        width_ctrl_layout.setSpacing(10)

        self.width_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.width_slider.setRange(64, 3840)
        self.width_slider.setSingleStep(2)
        self.width_slider.setValue(1920)
        self.width_slider.valueChanged.connect(self._on_width_changed)
        width_ctrl_layout.addWidget(self.width_slider, 1)

        self.width_badge = EditableSliderBadge(self.width_slider, suffix=" px", is_even=True)
        self.width_badge.setFixedWidth(68)
        width_ctrl_layout.addWidget(self.width_badge)

        self.btn_reset_width = QPushButton("↻")
        self.btn_reset_width.setProperty("class", "secondary-btn")
        self.btn_reset_width.setStyleSheet(reset_btn_style)
        self.btn_reset_width.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_width.setFixedSize(32, 32)
        # self.btn_reset_width.setToolTip("Khôi phục mặc định 1920 px")
        self.btn_reset_width.clicked.connect(lambda: self.width_slider.setValue(1920))
        width_ctrl_layout.addWidget(self.btn_reset_width)

        params_grid.addLayout(width_ctrl_layout, 1, 1)

        # Dòng 2 - Phải: Height [64, 2160], default 1080
        height_label = QLabel("Height (px):")
        height_label.setStyleSheet(param_lbl_style)
        params_grid.addWidget(height_label, 1, 2)

        height_ctrl_layout = QHBoxLayout()
        height_ctrl_layout.setSpacing(10)

        self.height_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.height_slider.setRange(64, 2160)
        self.height_slider.setSingleStep(2)
        self.height_slider.setValue(1080)
        self.height_slider.valueChanged.connect(self._on_height_changed)
        height_ctrl_layout.addWidget(self.height_slider, 1)

        self.height_badge = EditableSliderBadge(self.height_slider, suffix=" px", is_even=True)
        self.height_badge.setFixedWidth(68)
        height_ctrl_layout.addWidget(self.height_badge)

        self.btn_reset_height = QPushButton("↻")
        self.btn_reset_height.setProperty("class", "secondary-btn")
        self.btn_reset_height.setStyleSheet(reset_btn_style)
        self.btn_reset_height.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_height.setFixedSize(32, 32)
        # self.btn_reset_height.setToolTip("Khôi phục mặc định 1080 px")
        self.btn_reset_height.clicked.connect(lambda: self.height_slider.setValue(1080))
        height_ctrl_layout.addWidget(self.btn_reset_height)

        params_grid.addLayout(height_ctrl_layout, 1, 3)

        # ─── DÒNG 3: Thiết bị xử lý + Bộ mã hóa ───
        # Dòng 3 - Trái: Thiết bị xử lý (default CPU, [CPU, GPU])
        device_label = QLabel("Thiết bị xử lý:")
        device_label.setStyleSheet(param_lbl_style)
        params_grid.addWidget(device_label, 2, 0)

        self.device_combo = NoWheelComboBox()
        self.device_combo.addItems(["CPU", "GPU"])
        self.device_combo.setCurrentText("CPU")
        self.device_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        params_grid.addWidget(self.device_combo, 2, 1)

        # Dòng 3 - Phải: Bộ mã hóa (default CPU H.264, [CPU H.264, NVIDIA NVENC])
        encoder_label = QLabel("Bộ mã hóa (Encoder):")
        encoder_label.setStyleSheet(param_lbl_style)
        params_grid.addWidget(encoder_label, 2, 2)

        self.encoder_combo = NoWheelComboBox()
        self.encoder_combo.addItems(["CPU H.264", "NVIDIA NVENC"])
        self.encoder_combo.setCurrentText("CPU H.264")
        self.encoder_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        params_grid.addWidget(self.encoder_combo, 2, 3)

        self.params_card.addLayout(params_grid)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setStyleSheet("background-color: #E2E8F0; max-height: 1px; border: none; margin-top: 6px; margin-bottom: 6px;")
        self.params_card.addWidget(divider)

        # Action Buttons: Tạo video & Lưu video
        action_layout = QVBoxLayout()
        action_layout.setSpacing(8)

        self.btn_render = QPushButton("Tạo video")
        self.btn_render.setProperty("class", "primary-btn")
        self.btn_render.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.btn_render.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_render.setMinimumHeight(44)
        self.btn_render.setEnabled(False)  # Enabled once an image is picked
        self.btn_render.clicked.connect(self._start_rendering)
        action_layout.addWidget(self.btn_render)

        self.btn_save_video = QPushButton("💾 Lưu video")
        self.btn_save_video.setProperty("class", "secondary-btn")
        self.btn_save_video.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.btn_save_video.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_video.setMinimumHeight(38)
        self.btn_save_video.setEnabled(False)  # Only enabled when video is generated
        self.btn_save_video.clicked.connect(self._save_video)
        action_layout.addWidget(self.btn_save_video)

        self.params_card.addLayout(action_layout)

        # Progress bar (5px)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #F1F5F9;
                border: 1px solid #E2E8F0;
                border-radius: 5px;
            }
            QProgressBar::chunk {
                background-color: #4F46E5;
                border-radius: 5px;
            }
        """)
        self.params_card.addWidget(self.progress_bar)

        self.status_label = QLabel("Sẵn sàng tạo video. Vui lòng chọn ảnh đầu vào.")
        self.status_label.setProperty("class", "caption")
        self.params_card.addWidget(self.status_label)

        layout.addWidget(self.params_card)
        layout.addStretch(1)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _setup_player(self) -> None:
        """Alias video_player internal properties for full backward compatibility."""
        self.player = self.video_player.player
        self.audio_output = self.video_player.audio_output

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_media_sizes()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_media_sizes()

    def _update_media_sizes(self) -> None:
        """Dynamically adjust image card and video card heights to maintain responsive 16:9 aspect ratio."""
        if hasattr(self, "drop_zone") and hasattr(self, "video_player"):
            w = self.drop_zone.width()
            if w > 80:
                target_h = max(260, min(420, int(w * 9 / 16)))
                if self.drop_zone.height() != target_h:
                    self.drop_zone.setFixedHeight(target_h)
                    self.video_player.setFixedHeight(target_h)

    # ─── Parameter Sliders ──────────────────────────────────────────────

    def _on_duration_changed(self, val: int) -> None:
        self.duration_badge.setText(f"{val}s")

    def _on_fps_changed(self, val: int) -> None:
        self.fps_badge.setText(f"{val} fps")

    def _on_width_changed(self, val: int) -> None:
        even_val = (val // 2) * 2
        self.width_badge.setText(f"{even_val} px")

    def _on_height_changed(self, val: int) -> None:
        even_val = (val // 2) * 2
        self.height_badge.setText(f"{even_val} px")

    # ─── Image Selection ────────────────────────────────────────────────

    def _on_image_selected(self, path: Path) -> None:
        self.selected_image = path
        self.btn_render.setEnabled(True)
        self.status_label.setText(f"Đã chọn ảnh: {path.name}. Sẵn sàng tạo video.")

    def _on_image_cleared(self) -> None:
        self.selected_image = None
        self.btn_render.setEnabled(False)
        self.status_label.setText("Vui lòng chọn ảnh đầu vào để tiếp tục.")

    # ─── Inputs Disabling / Enabling ────────────────────────────────────

    def _set_inputs_enabled(self, enabled: bool) -> None:
        """Disable or enable all interactive parameters during video rendering."""
        self.drop_zone.setEnabled(enabled)
        self.duration_slider.setEnabled(enabled)
        self.duration_badge.setEnabled(enabled)
        self.btn_reset_duration.setEnabled(enabled)
        self.fps_slider.setEnabled(enabled)
        self.fps_badge.setEnabled(enabled)
        self.btn_reset_fps.setEnabled(enabled)
        self.width_slider.setEnabled(enabled)
        self.width_badge.setEnabled(enabled)
        self.btn_reset_width.setEnabled(enabled)
        self.height_slider.setEnabled(enabled)
        self.height_badge.setEnabled(enabled)
        self.btn_reset_height.setEnabled(enabled)
        self.device_combo.setEnabled(enabled)
        self.encoder_combo.setEnabled(enabled)
        self.btn_render.setEnabled(enabled if self.selected_image is not None else False)
        self.btn_save_video.setEnabled(enabled if self.current_video_path is not None else False)

    # ─── Video Rendering ────────────────────────────────────────────────

    def _start_rendering(self) -> None:
        if not self.selected_image or not self.selected_image.exists():
            self.status_label.setText("Lỗi: Vui lòng chọn một hình ảnh hợp lệ trước khi tạo video.")
            return

        if not self.engine.is_assets_ready():
            self.status_label.setText("Lỗi: Thiếu tài nguyên trong thư mục assets/v181d.")
            return

        # Prepare output directory and filename
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        output_file = OUTPUTS_DIR / f"video.mp4"

        # Lock inputs and start progress
        self._set_inputs_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(10)
        self.status_label.setText("Đang khởi tạo tiến trình tạo video phác họa...")

        duration = self.duration_slider.value()
        fps = self.fps_slider.value()
        width = self.width_slider.value()
        height = self.height_slider.value()
        device = self.device_combo.currentText()
        encoder = self.encoder_combo.currentText()

        self.worker = SketchRenderWorker(
            engine=self.engine,
            image_path=self.selected_image,
            duration=duration,
            fps=fps,
            device=device,
            encoder=encoder,
            width=width,
            height=height,
            output_path=output_file,
            parent=self,
        )
        self.worker.progress.connect(self._on_render_progress)
        self.worker.finished.connect(self._on_render_finished)
        self.worker.error.connect(self._on_render_error)
        self.worker.start()

    def _on_render_progress(self, percent: int, msg: str) -> None:
        self.progress_bar.setValue(percent)
        self.status_label.setText(msg)

    def _on_render_finished(self, out_path_str: str) -> None:
        self._set_inputs_enabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Đã tạo video vẽ tay thành công!")

        out_path = Path(out_path_str)
        self.load_video(out_path)

    def _on_render_error(self, err_msg: str) -> None:
        self._set_inputs_enabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Lỗi: {err_msg}")
        # QMessageBox.critical(self, "Lỗi Render Video", f"Không thể tạo video:\n{err_msg}")

    # ─── Video Player Controls ──────────────────────────────────────────

    def load_video(self, video_path: Path) -> None:
        """Load the rendered video into VideoPlayer and enable player controls."""
        if not video_path.exists():
            return
        self.current_video_path = video_path
        self.video_player.load_video(video_path)
        self.btn_save_video.setEnabled(True)

    def _toggle_playback(self) -> None:
        self.video_player.toggle_playback()

    def _toggle_mute(self) -> None:
        self.video_player.toggle_mute()

    def _on_seek(self, position: int) -> None:
        self.video_player.player.setPosition(position)

    def _on_player_position_changed(self, position: int) -> None:
        pass

    def _on_player_duration_changed(self, duration: int) -> None:
        pass

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        pass

    def _update_time_label(self, pos_ms: int, dur_ms: int) -> None:
        pass

    def _save_video(self) -> None:
        """Export the rendered video to a user chosen destination."""
        if not self.current_video_path or not self.current_video_path.exists():
            return
        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu video vẽ tay",
            str(Path.home() / self.current_video_path.name),
            "Video Files (*.mp4 *.avi *.mkv *.mov)",
        )
        if dest_path:
            shutil.copy2(self.current_video_path, dest_path)
            self.status_label.setText(f"Video đã được lưu thành công tại: {dest_path}")
            # QMessageBox.information(self, "Đã lưu", f"Video đã được lưu thành công tại:\n{dest_path}")

    def _cleanup_worker(self) -> None:
        """Clean up active background worker thread on exit."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(1000)
        if hasattr(self, "video_player") and self.video_player:
            self.video_player.cleanup()
