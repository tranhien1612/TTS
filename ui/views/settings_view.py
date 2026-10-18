"""Settings view – Central model management and download hub for Neu Audio Studio."""
from typing import Optional, Dict, Any
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QProgressBar,
    QFrame,
    QScrollArea,
    QMessageBox,
)

from core.config import (
    MODEL_VIENEU,
    MODEL_OMNIVOICE,
    DEFAULT_TTS_MODEL,
)
from core.model_manager import ModelManager
from core.worker import WorkerThread
from ui.components.card import Card
from ui.styles import (
    PRIMARY_BUTTON_STYLE,
    SECONDARY_BUTTON_STYLE,
    BORDER_COLOR,
    ACCENT_LIGHT,
    ACCENT_PRIMARY,
)


class SettingsView(QWidget):
    """Settings panel for central model downloading, loading, and TTS model selection."""

    model_changed = pyqtSignal(str)  # emits model key string (e.g. MODEL_VIENEU)

    def __init__(
        self,
        tts_engine=None,
        stt_engine=None,
        sketch_engine=None,
        current_model: str = DEFAULT_TTS_MODEL,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.tts_engine = tts_engine
        self.stt_engine = stt_engine
        self.sketch_engine = sketch_engine
        self._current_tts_model = current_model
        self.model_manager = ModelManager()
        self.worker: Optional[WorkerThread] = None

        self._action_buttons: list[QPushButton] = []
        self._setup_ui()
        self.refresh_state()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        # ─── Header ──────────────────────────────────────────────────────────
        header_box = QVBoxLayout()
        header_box.setSpacing(4)
        title = QLabel("Cài đặt & Quản lý Mô hình AI")
        title.setProperty("class", "header-title")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #0F172A;")
        header_box.addWidget(title)

        subtitle = QLabel("Tải về và khởi tạo các mô hình trí tuệ nhân tạo dùng cho giọng nói, nhận dạng âm thanh và video phác họa.")
        subtitle.setProperty("class", "caption")
        subtitle.setStyleSheet("color: #64748B; font-size: 13px;")
        header_box.addWidget(subtitle)
        layout.addLayout(header_box)

        # ─── Global Progress Bar & Status Banner ─────────────────────────────
        self.status_card = Card()
        status_box = QVBoxLayout()
        status_box.setSpacing(8)

        self.status_label = QLabel("Tất cả hệ thống sẵn sàng. Bạn có thể kiểm tra trạng thái và tải mô hình bên dưới.")
        self.status_label.setStyleSheet("color: #334155; font-size: 13px; font-weight: 500;")
        status_box.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #F1F5F9;
                border: 1px solid #E2E8F0;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #4F46E5;
                border-radius: 3px;
            }
        """)
        status_box.addWidget(self.progress_bar)
        self.status_card.addLayout(status_box)
        layout.addWidget(self.status_card)

        # ─── Card 1: Text-to-Speech (TTS) Models ─────────────────────────────
        self.card_tts = Card()
        tts_title = QLabel("1. Mô hình Text-to-Speech (Tạo giọng nói)")
        tts_title.setProperty("class", "section-title")
        tts_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #0F172A;")
        self.card_tts.addWidget(tts_title)

        tts_desc = QLabel("Lựa chọn và quản lý mô hình phát âm thanh chuyển văn bản thành giọng nói và nhân bản giọng (Voice Clone).")
        tts_desc.setProperty("class", "caption")
        self.card_tts.addWidget(tts_desc)

        # Radio button group for selecting active TTS model
        self.tts_btn_group = QButtonGroup(self)
        self.tts_btn_group.setExclusive(True)

        # Item 1: VieNeu
        self.item_vieneu = self._create_model_row(
            key=MODEL_VIENEU,
            name="VieNeu TTS (Khuyên dùng tiếng Việt)",
            tag="Tiếng Việt · Clone",
            description="Mô hình ONNX siêu nhẹ tối ưu tiếng Việt tự nhiên và hỗ trợ clone giọng từ tệp mẫu.",
            on_action=lambda: self._start_model_task("vieneu"),
        )
        self.card_tts.addWidget(self.item_vieneu["container"])
        self.tts_btn_group.addButton(self.item_vieneu["radio"])

        # Item 2: OmniVoice
        self.item_omnivoice = self._create_model_row(
            key=MODEL_OMNIVOICE,
            name="OmniVoice TTS (Đa ngôn ngữ)",
            tag="Đa ngôn ngữ · Clone",
            description="Mô hình TTS đa ngôn ngữ mạnh mẽ, hỗ trợ clone giọng nói linh hoạt.",
            on_action=lambda: self._start_model_task("omnivoice"),
        )
        self.card_tts.addWidget(self.item_omnivoice["container"])
        self.tts_btn_group.addButton(self.item_omnivoice["radio"])

        # Set checked radio
        if self._current_tts_model == MODEL_OMNIVOICE:
            self.item_omnivoice["radio"].setChecked(True)
        else:
            self.item_vieneu["radio"].setChecked(True)

        self.tts_btn_group.buttonClicked.connect(self._on_tts_radio_changed)
        layout.addWidget(self.card_tts)

        # ─── Card 2: STT & Video Dubbing (Whisper) ───────────────────────────
        self.card_stt = Card()
        stt_title = QLabel("2. Mô hình Speech-to-Text & Phụ đề Video")
        stt_title.setProperty("class", "section-title")
        stt_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #0F172A;")
        self.card_stt.addWidget(stt_title)

        stt_desc = QLabel("Mô hình AI nhận dạng giọng nói tự động (Speech-to-Text) và trích xuất phụ đề video có dấu thời gian (.srt).")
        stt_desc.setProperty("class", "caption")
        self.card_stt.addWidget(stt_desc)

        self.item_whisper = self._create_model_row(
            key="whisper",
            name="Whisper Large-v3-Turbo",
            tag="Nhận dạng giọng nói · INT8",
            description="Mô hình nhận dạng giọng nói đa ngôn ngữ chính xác cao, chạy tối ưu hóa INT8 trên CPU/GPU.",
            on_action=lambda: self._start_model_task("whisper"),
            has_radio=False,
        )
        self.card_stt.addWidget(self.item_whisper["container"])
        layout.addWidget(self.card_stt)

        layout.addStretch(1)
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _create_model_row(
        self,
        key: str,
        name: str,
        tag: str,
        description: str,
        on_action: Any,
        has_radio: bool = True,
    ) -> Dict[str, Any]:
        """Build an interactive card item with status indicator and action button."""
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background-color: #F8FAFC;
                border: 1px solid {BORDER_COLOR};
                border-radius: 10px;
                padding: 12px;
            }}
            QFrame:hover {{
                border-color: #CBD5E1;
            }}
        """)
        h_layout = QHBoxLayout(container)
        h_layout.setContentsMargins(8, 6, 8, 6)
        h_layout.setSpacing(14)

        radio = None
        if has_radio:
            radio = QRadioButton()
            radio.setProperty("model_key", key)
            radio.setCursor(Qt.CursorShape.PointingHandCursor)
            h_layout.addWidget(radio)

        # Text column
        info_col = QVBoxLayout()
        info_col.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        lbl_name = QLabel(name)
        lbl_name.setStyleSheet("font-size: 14px; font-weight: 600; color: #0F172A;")
        title_row.addWidget(lbl_name)

        lbl_tag = QLabel(tag)
        lbl_tag.setProperty("class", "badge-accent")
        lbl_tag.setStyleSheet(f"font-size: 11px; padding: 2px 8px; background-color: {ACCENT_LIGHT}; color: {ACCENT_PRIMARY}; border-radius: 4px;")
        title_row.addWidget(lbl_tag)
        title_row.addStretch(1)
        info_col.addLayout(title_row)

        lbl_desc = QLabel(description)
        lbl_desc.setStyleSheet("color: #64748B; font-size: 12px;")
        lbl_desc.setWordWrap(True)
        info_col.addWidget(lbl_desc)

        h_layout.addLayout(info_col, 1)

        # Status badge
        status_badge = QLabel("Đang kiểm tra...")
        status_badge.setFixedHeight(28)
        status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_layout.addWidget(status_badge)

        # Action button
        action_btn = QPushButton("Tải về")
        action_btn.setProperty("class", "primary-btn")
        action_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        action_btn.setFixedHeight(34)
        action_btn.clicked.connect(on_action)
        h_layout.addWidget(action_btn)
        self._action_buttons.append(action_btn)

        return {
            "key": key,
            "container": container,
            "radio": radio,
            "status_badge": status_badge,
            "action_btn": action_btn,
        }

    # ─── State Refresh & Status Badges ─────────────────────────────────────

    def refresh_state(self) -> None:
        """Inspect disk and memory status of all models and update UI indicators."""
        # 1. VieNeu
        vieneu_downloaded = self.model_manager.is_vieneu_downloaded()
        vieneu_loaded = (
            self.tts_engine is not None
            and self.tts_engine.is_loaded
            and self.tts_engine.current_model_type == MODEL_VIENEU
        )
        self._update_item_ui(self.item_vieneu, vieneu_downloaded, vieneu_loaded)

        # 2. OmniVoice
        omnivoice_downloaded = self.model_manager.is_omnivoice_downloaded()
        omnivoice_loaded = (
            self.tts_engine is not None
            and self.tts_engine.is_loaded
            and self.tts_engine.current_model_type == MODEL_OMNIVOICE
        )
        self._update_item_ui(self.item_omnivoice, omnivoice_downloaded, omnivoice_loaded)

        # 3. Whisper STT
        whisper_downloaded = (
            self.stt_engine.is_model_downloaded()
            if self.stt_engine is not None
            else self.model_manager.is_whisper_downloaded()
        )
        whisper_loaded = self.stt_engine is not None and self.stt_engine.is_loaded
        self._update_item_ui(self.item_whisper, whisper_downloaded, whisper_loaded)

    def _update_item_ui(self, item: Dict[str, Any], is_downloaded: bool, is_loaded: bool) -> None:
        badge: QLabel = item["status_badge"]
        btn: QPushButton = item["action_btn"]

        if is_downloaded:
            badge.setText("● Đã sẵn sàng")
            badge.setStyleSheet("background-color: #ECFDF5; color: #059669; border: 1px solid #A7F3D0; border-radius: 6px; padding: 4px 10px; font-weight: 600; font-size: 12px;")
            btn.setVisible(False)
        else:
            badge.setText("○ Chưa tải về")
            badge.setStyleSheet("background-color: #FEF2F2; color: #DC2626; border: 1px solid #FECACA; border-radius: 6px; padding: 4px 10px; font-weight: 600; font-size: 12px;")
            btn.setText("Tải về")
            btn.setVisible(True)
            btn.setEnabled(True)
            btn.setStyleSheet(PRIMARY_BUTTON_STYLE)

    # ─── Event Handlers ───────────────────────────────────────────────────

    def _on_tts_radio_changed(self, button: QRadioButton) -> None:
        key = button.property("model_key")
        if key and key != self._current_tts_model:
            self._current_tts_model = key
            self.model_changed.emit(key)
            self.refresh_state()

    # ─── Background Model Task ───────────────────────────────────────────

    def _set_actions_enabled(self, enabled: bool) -> None:
        for btn in self._action_buttons:
            btn.setEnabled(enabled)

    def _start_model_task(self, target: str) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        self._set_actions_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText(f"Đang chuẩn bị xử lý mô hình '{target}'...")

        def _task_runner(progress_callback=None):
            if target == "vieneu":
                if not self.model_manager.is_vieneu_downloaded():
                    self.model_manager.ensure_vieneu_model(progress_callback)
                if progress_callback:
                    progress_callback(90, "Đang nạp mô hình VieNeu vào bộ nhớ...")
                if self.tts_engine:
                    self.tts_engine.set_model_type(MODEL_VIENEU)
                    self.tts_engine.load_model(progress_callback)
            elif target == "omnivoice":
                if not self.model_manager.is_omnivoice_downloaded():
                    self.model_manager.ensure_omnivoice_model(progress_callback)
                if progress_callback:
                    progress_callback(90, "Đang nạp mô hình OmniVoice vào bộ nhớ...")
                if self.tts_engine:
                    self.tts_engine.set_model_type(MODEL_OMNIVOICE)
                    self.tts_engine.load_model(progress_callback)
            elif target == "whisper":
                if self.stt_engine:
                    self.stt_engine.ensure_model_downloaded(progress_callback)
                    if progress_callback:
                        progress_callback(90, "Đang nạp mô hình Whisper vào bộ nhớ...")
                    self.stt_engine.load_model(progress_callback)
                else:
                    self.model_manager.ensure_whisper_model(progress_callback)
            return target

        self._cleanup_worker()
        self.worker = WorkerThread(_task_runner)
        self.worker.progress.connect(self._on_task_progress)
        self.worker.finished_task.connect(self._on_task_finished)
        self.worker.failed_task.connect(self._on_task_failed)
        self.worker.start()

    def _on_task_progress(self, percent: int, msg: str) -> None:
        self.status_label.setText(msg)
        if 0 < percent < 100:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
        elif percent >= 100:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
        else:
            self.progress_bar.setRange(0, 0)

    def _on_task_finished(self, target: str) -> None:
        self.progress_bar.setVisible(False)
        self._set_actions_enabled(True)
        self._cleanup_worker()
        self.refresh_state()
        self.status_label.setText(f"✓ Mô hình '{target}' đã được tải và khởi tạo sẵn sàng sử dụng!")
        # QMessageBox.information(
        #     self,
        #     "Thành công",
        #     f"Mô hình '{target}' đã được chuẩn bị và khởi tạo thành công!\nBạn có thể quay lại các tab chức năng để sử dụng ngay.",
        # )

    def _on_task_failed(self, error_msg: str) -> None:
        self.progress_bar.setVisible(False)
        self._set_actions_enabled(True)
        self._cleanup_worker()
        self.refresh_state()
        self.status_label.setText(f"❌ Xử lý mô hình thất bại: {error_msg}. Vui lòng kiểm tra lại kết nối mạng hoặc thử lại.")
        # QMessageBox.critical(
        #     self,
        #     "Lỗi",
        #     f"Không thể tải hoặc khởi tạo mô hình:\n{error_msg}\n\nVui lòng kiểm tra lại kết nối mạng hoặc thử lại.",
        # )

    def _cleanup_worker(self) -> None:
        if self.worker is not None:
            try:
                self.worker.quit()
                self.worker.wait(500)
                self.worker.deleteLater()
            except Exception:
                pass
            self.worker = None

    @property
    def current_model(self) -> str:
        return self._current_tts_model