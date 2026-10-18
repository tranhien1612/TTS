import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QButtonGroup,
    QFileDialog,
    QProgressBar,
    QScrollArea,
    QSlider,
    QFrame,
    QMessageBox,
)

from core.config import (
    DEFAULT_VOICE,
    AUDIO_FILE_FILTER,
    EXAMPLES_DIR,
)
from core.worker import WorkerThread
from engines.tts_engine import TTSEngine
from ui.components.card import Card
from ui.components.audio_player import AudioPlayer
from ui.components.voice_pill import VoicePill, FlowWidget
from ui.components.slider_badge import EditableSliderBadge
from ui.styles import PRIMARY_BUTTON_STYLE, SECONDARY_BUTTON_STYLE


class NoWheelSlider(QSlider):
    """QSlider that ignores mouse wheel events to prevent accidental value changes during page scrolling."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class TTSView(QWidget):
    """Text-to-Speech and Voice Cloning primary view."""

    status_updated = pyqtSignal(str)

    def __init__(self, tts_engine: TTSEngine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = tts_engine
        self.worker: Optional[WorkerThread] = None
        self.reference_audio_path: Optional[Path] = None
        self.selected_preset_id: str = DEFAULT_VOICE
        self.last_preset_pill: Optional[VoicePill] = None
        self._preset_pills: List[VoicePill] = []

        self._setup_ui()
        self.refresh_state()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        # Scroll Area to handle smaller screen heights gracefully
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Header Title Row
        header_layout = QHBoxLayout()
        title_label = QLabel("Text to Speech")
        title_label.setProperty("class", "header-title")
        header_layout.addWidget(title_label)
        layout.addLayout(header_layout)

        # --- Card 1: Text Input ---
        text_card = Card() #title="Văn bản cần đọc"

        self.text_input = QTextEdit()
        self.text_input.setAcceptRichText(False)
        self.text_input.setPlaceholderText(
            "Nhập hoặc dán văn bản cần đọc tại đây...\n"
        )
        self.text_input.setMinimumHeight(120)
        txt_palette = self.text_input.palette()
        txt_palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
        txt_palette.setColor(QPalette.ColorRole.Text, QColor("#0F172A"))
        txt_palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#94A3B8"))
        self.text_input.setPalette(txt_palette)
        self.text_input.textChanged.connect(self._update_char_count)
        text_card.addWidget(self.text_input)

        # Text toolbar
        text_tools = QHBoxLayout()
        self.char_count_label = QLabel("0 ký tự")
        self.char_count_label.setProperty("class", "caption")
        text_tools.addWidget(self.char_count_label)
        text_tools.addStretch(1)
        text_card.addLayout(text_tools)

        layout.addWidget(text_card)

        # --- Combined Card: Chọn voice, Tạo giọng nói & Trình phát âm thanh ---
        self.control_card = Card()

        # Section 1: Chọn voice (pills container)
        self.pills_widget = FlowWidget(margin=0, spacing=10)
        self.voice_btn_group = QButtonGroup(self)
        self.voice_btn_group.setExclusive(True)

        # Clone pill (will be hidden for models that don't support cloning)
        self.clone_pill = VoicePill(
            voice_id="__clone__",
            title="Voice Clone",
            subtitle="Chọn file audio",
            full_desc="Nhân bản giọng nói tức thì từ file âm thanh",
            is_clone=True,
        )
        self.clone_pill.clicked.connect(self._on_clone_pill_clicked)
        self.voice_btn_group.addButton(self.clone_pill)
        self.pills_widget.flow_layout.addWidget(self.clone_pill)

        self.control_card.addWidget(self.pills_widget)

        # Status / description label below pills
        self.voice_info_label = QLabel(f"🔊 Đang chọn giọng: {self.selected_preset_id}")
        self.voice_info_label.setProperty("class", "caption")
        self.control_card.addWidget(self.voice_info_label)

        # Divider 1
        divider1 = QFrame()
        divider1.setFrameShape(QFrame.Shape.HLine)
        divider1.setFrameShadow(QFrame.Shadow.Plain)
        divider1.setStyleSheet("background-color: #E2E8F0; max-height: 1px; border: none; margin-top: 4px; margin-bottom: 4px;")
        self.control_card.addWidget(divider1)

        # Speed adjustment row
        self.speed_container = QWidget()
        speed_layout = QHBoxLayout(self.speed_container)
        speed_layout.setContentsMargins(0, 4, 0, 4)
        speed_layout.setSpacing(12)

        speed_title = QLabel("Tốc độ đọc:")
        speed_title.setStyleSheet("font-weight: 600; color: #334155; font-size: 13px;")
        speed_layout.addWidget(speed_title)

        self.speed_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(50, 200)   # 0.5x to 2.0x
        self.speed_slider.setValue(100)        # default 1.0x
        self.speed_slider.setSingleStep(5)
        self.speed_slider.setPageStep(10)
        self.speed_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.speed_slider.valueChanged.connect(self._on_speed_slider_changed)
        speed_layout.addWidget(self.speed_slider, 1)

        self.speed_val_badge = EditableSliderBadge(
            self.speed_slider,
            suffix="x",
            scale=100.0,
            decimals=1,
        )
        self.speed_val_badge.setFixedWidth(54)
        speed_layout.addWidget(self.speed_val_badge)

        self.btn_reset_speed = QPushButton("↻")
        self.btn_reset_speed.setProperty("class", "secondary-btn")
        self.btn_reset_speed.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.btn_reset_speed.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_speed.clicked.connect(lambda: self.speed_slider.setValue(100))
        speed_layout.addWidget(self.btn_reset_speed)

        self.control_card.addWidget(self.speed_container)

        divider2 = QFrame()
        divider2.setFrameShape(QFrame.Shape.HLine)
        divider2.setFrameShadow(QFrame.Shadow.Plain)
        divider2.setStyleSheet("background-color: #E2E8F0; max-height: 1px; border: none; margin-top: 4px; margin-bottom: 4px;")
        self.control_card.addWidget(divider2)

        # Section 2: Bắt đầu tạo voice
        action_row = QHBoxLayout()
        self.btn_synthesize = QPushButton("Tạo giọng nói")
        self.btn_synthesize.setObjectName("btnSynthesize")
        self.btn_synthesize.setProperty("class", "primary-btn")
        self.btn_synthesize.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.btn_synthesize.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_synthesize.setMinimumHeight(44)
        self.btn_synthesize.clicked.connect(self._on_action_clicked)

        action_row.addWidget(self.btn_synthesize)
        self.control_card.addLayout(action_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate pulse
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
        self.control_card.addWidget(self.progress_bar)

        self.status_msg_label = QLabel("Sẵn sàng tạo âm thanh.")
        self.status_msg_label.setProperty("class", "caption")
        self.control_card.addWidget(self.status_msg_label)

        # Divider 2
        divider3 = QFrame()
        divider3.setFrameShape(QFrame.Shape.HLine)
        divider3.setFrameShadow(QFrame.Shadow.Plain)
        divider3.setStyleSheet("background-color: #E2E8F0; max-height: 1px; border: none; margin-top: 4px; margin-bottom: 4px;")
        self.control_card.addWidget(divider3)

        # Section 3: Phát âm thanh
        self.player_card = AudioPlayer(title="Trình phát âm thanh", is_card=False)
        self.control_card.addWidget(self.player_card)

        layout.addWidget(self.control_card)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    # ─── Pill management ────────────────────────────────────────────────

    def _build_preset_pills(self) -> None:
        """Create preset voice pills from the engine's current voice list."""
        first_preset: Optional[VoicePill] = None
        for v in self.engine.list_preset_voices():
            name = v["id"]
            desc = v.get("description", "")
            gender = v.get("gender", "")
            subtitle = self._format_voice_subtitle(desc, gender)
            pill = VoicePill(voice_id=name, title=name, subtitle=subtitle, full_desc=v.get("label", name))
            pill.clicked.connect(lambda checked, p=pill: self._on_preset_pill_clicked(p))
            self.voice_btn_group.addButton(pill)
            self.pills_widget.flow_layout.addWidget(pill)
            self._preset_pills.append(pill)
            if not first_preset:
                first_preset = pill

        if first_preset:
            first_preset.setChecked(True)
            self.selected_preset_id = first_preset.voice_id
            self.last_preset_pill = first_preset

    def refresh_state(self) -> None:
        """Refresh TTS view state when model type changes or tab is displayed."""
        # Remove old preset pills from layout and button group
        for pill in self._preset_pills:
            self.voice_btn_group.removeButton(pill)
            self.pills_widget.flow_layout.removeWidget(pill)
            pill.deleteLater()
        self._preset_pills.clear()
        self.last_preset_pill = None

        is_downloaded = self.engine.is_model_downloaded()

        if not is_downloaded:
            # Model not yet downloaded:
            # 1. Do NOT display voices or speed slider
            self.clone_pill.setVisible(False)
            self.pills_widget.setVisible(False)
            self.speed_container.setVisible(False)
            self.voice_info_label.setText(f"⚠️ Mô hình '{self.engine.current_model_type}' chưa được tải về máy. Vui lòng vào '⚙ Cài đặt' để tải mô hình.")
            self.btn_synthesize.setText("Tạo giọng nói")
            self.btn_synthesize.setEnabled(True)
            self.status_msg_label.setText("Mô hình chưa sẵn sàng. Vui lòng vào '⚙ Cài đặt' để tải và khởi tạo mô hình.")
        else:
            # Model is downloaded:
            self.pills_widget.setVisible(True)
            self.speed_container.setVisible(True)
            # Show clone pill if supported
            self.clone_pill.setVisible(self.engine.supports_voice_clone)
            if not self.engine.supports_voice_clone and self.clone_pill.isChecked():
                self.clone_pill.setChecked(False)

            # Rebuild from engine's updated voice list
            self._build_preset_pills()

            # Update info label
            if self.last_preset_pill:
                sub = f" ({self.last_preset_pill.subtitle_text})" if self.last_preset_pill.subtitle_text else ""
                self.voice_info_label.setText(f"🔊 Đang chọn giọng: {self.last_preset_pill.title_text}{sub}")
            elif not self.clone_pill.isHidden():
                self.clone_pill.setChecked(True)
                if self.reference_audio_path and self.reference_audio_path.exists():
                    self.voice_info_label.setText(f"🔊 Nhân bản từ tệp mẫu: {self.reference_audio_path.name}")
                else:
                    self.voice_info_label.setText("🔊 Chế độ Voice Clone. Vui lòng nhấn vào nút 'Voice Clone' để chọn tệp âm thanh mẫu.")
            else:
                self.voice_info_label.setText("🔊 Sẵn sàng tạo âm thanh.")

            self.btn_synthesize.setText("Tạo giọng nói")
            self.btn_synthesize.setEnabled(True)
            self.status_msg_label.setText("Sẵn sàng tạo âm thanh.")

        # Ensure progress bar animation is stopped and hidden if idle, and inputs are enabled
        if self.worker is None or not self.worker.isRunning():
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(False)
            self._set_inputs_enabled(True)

    def _on_speed_slider_changed(self, value: int) -> None:
        """Handle speed slider value change (50 -> 0.5x, 100 -> 1.0x, 200 -> 2.0x)."""
        factor = value / 100.0
        if value % 10 == 0:
            self.speed_val_badge.setText(f"{factor:.1f}x")
        else:
            self.speed_val_badge.setText(f"{factor:.2f}x")

    def refresh_voice_pills(self) -> None:
        """Backward-compatible alias for refresh_state."""
        self.refresh_state()

    @staticmethod
    def _format_voice_subtitle(desc: str, gender: str = "") -> str:
        """Format voice description into level 2 attribute e.g. 'Nữ · Miền Bắc'."""
        parts = [p.strip() for p in desc.split("·") if p.strip()] if desc else []
        g = ""
        if parts and parts[0] in ("Nam", "Nữ"):
            g = parts[0]
        elif gender:
            g_low = gender.strip().lower()
            if g_low in ("nam", "male"):
                g = "Nam"
            elif g_low in ("nữ", "nu", "female"):
                g = "Nữ"
            else:
                g = gender.strip()

        r = ""
        if len(parts) >= 2:
            r = parts[1].strip()
        elif "Bắc" in desc:
            r = "Bắc"
        elif "Nam" in desc:
            r = "Nam"
        elif "Trung" in desc:
            r = "Trung"

        if r and not r.startswith("Miền"):
            r = f"Miền {r}"

        items = []
        if g:
            items.append(g)
        if r:
            items.append(r)
        return " · ".join(items) if items else desc

    def _on_preset_pill_clicked(self, pill: VoicePill) -> None:
        """Handle selection of a preset voice pill."""
        pill.setChecked(True)
        self.selected_preset_id = pill.voice_id
        self.last_preset_pill = pill
        sub = f" ({pill.subtitle_text})" if pill.subtitle_text else ""
        self.voice_info_label.setText(f"🔊 Đang chọn giọng: {pill.title_text}{sub}")

    def _on_clone_pill_clicked(self) -> None:
        """Handle clicking Voice Clone pill: open file dialog to choose clone audio."""
        start_dir = str(EXAMPLES_DIR if EXAMPLES_DIR.exists() else Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn tệp âm thanh mẫu để Clone giọng (.wav, .mp3, .m4a)",
            start_dir,
            AUDIO_FILE_FILTER,
        )
        if path:
            self.reference_audio_path = Path(path)
            file_name = self.reference_audio_path.name
            display_name = file_name if len(file_name) <= 22 else f"{file_name[:19]}..."
            self.clone_pill.set_content("Voice Clone", display_name)
            self.clone_pill.setChecked(True)
            self.voice_info_label.setText(f"Nhân bản từ tệp mẫu: {self.reference_audio_path.name}")
        else:
            if self.reference_audio_path and self.reference_audio_path.exists():
                self.clone_pill.setChecked(True)
            else:
                # Revert to last selected preset pill
                if self.last_preset_pill:
                    self.last_preset_pill.setChecked(True)
                    self._on_preset_pill_clicked(self.last_preset_pill)

    def _update_char_count(self) -> None:
        count = len(self.text_input.toPlainText())
        self.char_count_label.setText(f"{count} ký tự")

    def _on_progress(self, percent: int, message: str) -> None:
        """Handle progress updates from background worker."""
        if 0 < percent < 100:
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
        elif percent >= 100:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.progress_bar.setVisible(False)
        else:
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)

        self.status_msg_label.setText(message)
        if "tạo giọng nói" in message.lower() or "xử lý" in message.lower():
            self.btn_synthesize.setText("Đang xử lý giọng nói...")

    def _cleanup_worker(self) -> None:
        if self.worker is not None:
            try:
                self.worker.quit()
                self.worker.wait(200)
                self.worker.deleteLater()
            except Exception:
                pass
            self.worker = None

    def _on_action_clicked(self) -> None:
        """Handle main button click: warn if model missing, otherwise start synthesis."""
        if self.worker is not None and self.worker.isRunning():
            return

        if not self.engine.is_model_downloaded():
            # QMessageBox.warning(
            #     self,
            #     "Chưa có mô hình",
            #     f"Mô hình '{self.engine.current_model_type}' chưa được tải về máy trong thư mục models.\n\n"
            #     "Vui lòng chuyển sang mục '⚙ Cài đặt' ở thanh điều hướng để tải và khởi tạo mô hình.",
            # )
            self.status_msg_label.setText("⚠️ Chưa có mô hình. Vui lòng vào '⚙ Cài đặt' để tải mô hình.")
            return

        self._start_synthesis()

    def _start_synthesis(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        text = self.text_input.toPlainText().strip()
        if not text:
            self.status_msg_label.setText("❌ Vui lòng nhập văn bản trước khi tạo giọng nói.")
            return

        if (self.clone_pill.isChecked() and self.clone_pill.isVisible()) or not self._preset_pills:
            if not self.reference_audio_path or not self.reference_audio_path.exists():
                self._on_clone_pill_clicked()
                if not self.reference_audio_path or not self.reference_audio_path.exists():
                    return
            voice_ref = str(self.reference_audio_path.resolve())
        else:
            voice_ref = self.selected_preset_id or DEFAULT_VOICE

        self._run_synthesis_inference(text, voice_ref)

    def _set_inputs_enabled(self, enabled: bool) -> None:
        """Enable or disable input parameters (text editing, voice selection, speed adjustment) during synthesis."""
        self.text_input.setEnabled(enabled)
        self.pills_widget.setEnabled(enabled)
        self.clone_pill.setEnabled(enabled)
        self.speed_container.setEnabled(enabled)
        self.speed_slider.setEnabled(enabled)
        self.speed_val_badge.setEnabled(enabled)
        self.btn_reset_speed.setEnabled(enabled)

    def _run_synthesis_inference(self, text: str, voice_ref: str) -> None:
        self.btn_synthesize.setEnabled(False)
        self._set_inputs_enabled(False)
        self.btn_synthesize.setText("Đang xử lý giọng nói...")
        self.status_msg_label.setText("Đang xử lý tạo giọng nói...")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)

        # Run inference asynchronously via QThread Worker
        self._cleanup_worker()
        speed = self.speed_slider.value() / 100.0 if hasattr(self, "speed_slider") else 1.0
        self.worker = WorkerThread(
            self.engine.synthesize,
            text=text,
            voice_ref=voice_ref,
            speed=speed,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_task.connect(self._on_synthesis_finished)
        self.worker.failed_task.connect(self._on_synthesis_failed)
        self.worker.start()

    def _on_synthesis_finished(self, result: Dict[str, Any]) -> None:
        self.btn_synthesize.setEnabled(True)
        self._set_inputs_enabled(True)
        self.btn_synthesize.setText("Tạo giọng nói")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self._cleanup_worker()

        output_path: Path = result["output_path"]
        duration = result["duration"]
        elapsed = result["elapsed_time"]
        voice_desc = result["voice"]
        speed = result.get("speed", 1.0)

        msg = f"✓ Hoàn tất trong {elapsed:.2f}s | Độ dài âm thanh: {duration:.2f}s | Tốc độ: {speed:.2f}x | Giọng: {voice_desc}"
        self.status_msg_label.setText(msg)
        self.status_updated.emit(msg)

        # Load into AudioPlayer
        self.player_card.load_audio(output_path, description=f"{voice_desc} ({duration:.1f}s, {speed:.2f}x)")

    def _on_synthesis_failed(self, error_msg: str) -> None:
        self.btn_synthesize.setEnabled(True)
        self._set_inputs_enabled(True)
        self.btn_synthesize.setText("Tạo giọng nói")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self._cleanup_worker()
        self.status_msg_label.setText(f"❌ Lỗi: {error_msg}")
