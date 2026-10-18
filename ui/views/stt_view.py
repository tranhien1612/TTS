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
    QPushButton,
    QFileDialog,
    QTextEdit,
    QProgressBar,
    QScrollArea,
    QFrame,
    QCheckBox,
    QComboBox,
    QMessageBox,
    QApplication,
)

from core.config import (
    AUDIO_FILE_FILTER,
    OUTPUTS_DIR,
)
from core.worker import WorkerThread
from core.translator import (
    SUPPORTED_TRANSLATION_LANGUAGES,
    translate_text,
    translate_segments,
)
from engines.stt_engine import STTEngine, format_srt, sync_text_to_segments
from ui.components.card import Card
from ui.styles import PRIMARY_BUTTON_STYLE, SECONDARY_BUTTON_STYLE


class STTView(QWidget):
    """Speech-to-Text interface with transcription, optional translation, and SRT export."""

    status_updated = pyqtSignal(str)

    def __init__(self, stt_engine: STTEngine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = stt_engine
        self.selected_audio: Optional[Path] = None
        self.current_segments: List[Dict[str, Any]] = []
        self.current_translated_segments: List[Dict[str, Any]] = []
        self.worker: Optional[WorkerThread] = None
        self.trans_worker: Optional[WorkerThread] = None

        self._setup_ui()

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

        # Header Title Row
        header_layout = QHBoxLayout()
        title_label = QLabel("Speech-to-Text")
        title_label.setProperty("class", "header-title")
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        layout.addLayout(header_layout)

        # --- Unified Single Card: File Selection, Translation & Results ---
        stt_card = Card()

        # Section 1: File Selection Row
        file_select_row = QHBoxLayout()
        file_select_row.setSpacing(12)

        self.btn_select_file = QPushButton("📁 Chọn tệp âm thanh")
        self.btn_select_file.setProperty("class", "secondary-btn")
        self.btn_select_file.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.btn_select_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_file.setMinimumHeight(40)
        self.btn_select_file.clicked.connect(self._on_select_file)
        file_select_row.addWidget(self.btn_select_file)

        self.file_name_label = QLabel("Chưa chọn tệp âm thanh (.wav, .mp3, .m4a, ...)")
        self.file_name_label.setProperty("class", "caption")
        self.file_name_label.setStyleSheet("color: #475569; font-size: 13px;")
        file_select_row.addWidget(self.file_name_label, 1)

        stt_card.addLayout(file_select_row)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setStyleSheet("background-color: #E2E8F0; max-height: 1px; border: none; margin-top: 4px; margin-bottom: 4px;")
        stt_card.addWidget(divider)

        # Action Button: Transcribe
        action_row = QHBoxLayout()
        self.btn_transcribe = QPushButton("Bắt đầu nhận dạng")
        self.btn_transcribe.setProperty("class", "primary-btn")
        self.btn_transcribe.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.btn_transcribe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_transcribe.setMinimumHeight(44)
        self.btn_transcribe.clicked.connect(self._start_transcribe)
        action_row.addWidget(self.btn_transcribe)
        stt_card.addLayout(action_row)

        # Progress bar (5px)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
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
        stt_card.addWidget(self.progress_bar)

        self.status_label = QLabel("Sẵn sàng nhận dạng. Vui lòng bấm 'Chọn tệp âm thanh'.")
        self.status_label.setProperty("class", "caption")
        stt_card.addWidget(self.status_label)

        # Subtle divider
        divider2 = QFrame()
        divider2.setFrameShape(QFrame.Shape.HLine)
        divider2.setFrameShadow(QFrame.Shadow.Plain)
        divider2.setStyleSheet("background-color: #E2E8F0; max-height: 1px; border: none; margin-top: 4px; margin-bottom: 4px;")
        stt_card.addWidget(divider2)

        # Section 2: Recognition Results & Translation
        # 1. Text "Kết quả nhận dạng"
        self.results_section_title = QLabel("Kết quả nhận dạng")
        self.results_section_title.setProperty("class", "section-title")
        stt_card.addWidget(self.results_section_title)

        # 2. Translation Options Row (Checkbox + Target Language Combobox + Translate Button)
        trans_options_row = QHBoxLayout()
        trans_options_row.setSpacing(12)

        self.chk_translate = QCheckBox("Dịch sang ngôn ngữ khác")
        self.chk_translate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_translate.setStyleSheet("font-weight: 600; font-size: 13px; color: #1E293B;")
        self.chk_translate.setEnabled(False)
        self.chk_translate.setToolTip("Chỉ khả dụng sau khi nhận dạng âm thanh")
        self.chk_translate.toggled.connect(self._on_translate_toggled)
        trans_options_row.addWidget(self.chk_translate)

        self.target_lang_label = QLabel("Ngôn ngữ đích:")
        self.target_lang_label.setStyleSheet("color: #64748B; font-size: 13px; font-weight: 500;")
        self.target_lang_label.setVisible(False)
        trans_options_row.addWidget(self.target_lang_label)

        self.combo_target_lang = QComboBox()
        for label, code in SUPPORTED_TRANSLATION_LANGUAGES:
            self.combo_target_lang.addItem(label, code)
        self.combo_target_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_target_lang.setMinimumWidth(160)
        self.combo_target_lang.setVisible(False)
        self.combo_target_lang.currentIndexChanged.connect(self._on_target_lang_changed)
        trans_options_row.addWidget(self.combo_target_lang)

        self.btn_translate_now = QPushButton("🔄 Dịch văn bản")
        self.btn_translate_now.setProperty("class", "secondary-btn")
        self.btn_translate_now.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.btn_translate_now.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_translate_now.setVisible(False)
        self.btn_translate_now.setEnabled(False)
        self.btn_translate_now.clicked.connect(self._translate_current_text)
        trans_options_row.addWidget(self.btn_translate_now)

        trans_options_row.addStretch(1)
        stt_card.addLayout(trans_options_row)

        # 3. Ô hiển thị văn bản (Results Row: Original + Translated)
        results_layout = QHBoxLayout()
        results_layout.setSpacing(16)

        # --- Column 1: Văn bản gốc (Original) ---
        self.original_column = QWidget()
        orig_layout = QVBoxLayout(self.original_column)
        orig_layout.setContentsMargins(0, 0, 0, 0)
        orig_layout.setSpacing(8)

        self.orig_title = QLabel("Văn bản gốc")
        self.orig_title.setProperty("class", "caption")
        self.orig_title.setStyleSheet("font-weight: 600; color: #475569; font-size: 13px;")
        self.orig_title.setVisible(False)
        orig_layout.addWidget(self.orig_title)

        self.transcript_box = QTextEdit()
        self.transcript_box.setReadOnly(False)
        self.transcript_box.setAcceptRichText(False)
        self.transcript_box.setPlaceholderText("Văn bản sau khi nhận dạng từ tệp âm thanh sẽ hiển thị tại đây...")
        self.transcript_box.setMinimumHeight(240)
        box_pal = self.transcript_box.palette()
        box_pal.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
        box_pal.setColor(QPalette.ColorRole.Text, QColor("#0F172A"))
        box_pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#94A3B8"))
        self.transcript_box.setPalette(box_pal)
        self.transcript_box.textChanged.connect(self._update_text_stats)
        orig_layout.addWidget(self.transcript_box)

        # Toolbar below original transcript
        tools_layout = QHBoxLayout()
        self.stats_label = QLabel("0 từ · 0 ký tự")
        self.stats_label.setProperty("class", "caption")
        tools_layout.addWidget(self.stats_label)
        tools_layout.addStretch(1)

        self.btn_save_txt = QPushButton("💾 Lưu tệp .txt")
        self.btn_save_txt.setProperty("class", "secondary-btn")
        self.btn_save_txt.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.btn_save_txt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_txt.clicked.connect(self._save_txt)
        tools_layout.addWidget(self.btn_save_txt)

        self.btn_save_srt = QPushButton("🎬 Lưu tệp .srt")
        self.btn_save_srt.setProperty("class", "secondary-btn")
        self.btn_save_srt.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.btn_save_srt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_srt.clicked.connect(self._save_srt)
        tools_layout.addWidget(self.btn_save_srt)

        self.btn_clear = QPushButton("Xóa trắng")
        self.btn_clear.setProperty("class", "secondary-btn")
        self.btn_clear.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self._clear_transcript)
        tools_layout.addWidget(self.btn_clear)

        orig_layout.addLayout(tools_layout)
        results_layout.addWidget(self.original_column, 1)

        # --- Column 2: Bản dịch (Translated) ---
        self.translated_column = QWidget()
        trans_layout = QVBoxLayout(self.translated_column)
        trans_layout.setContentsMargins(0, 0, 0, 0)
        trans_layout.setSpacing(8)

        self.translated_title = QLabel("Bản dịch")
        self.translated_title.setProperty("class", "caption")
        self.translated_title.setStyleSheet("font-weight: 600; color: #475569; font-size: 13px;")
        trans_layout.addWidget(self.translated_title)

        self.translated_box = QTextEdit()
        self.translated_box.setReadOnly(False)
        self.translated_box.setAcceptRichText(False)
        self.translated_box.setPlaceholderText("Văn bản sau khi dịch sẽ hiển thị tại đây...")
        self.translated_box.setMinimumHeight(240)
        trans_box_pal = self.translated_box.palette()
        trans_box_pal.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
        trans_box_pal.setColor(QPalette.ColorRole.Text, QColor("#0F172A"))
        trans_box_pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#94A3B8"))
        self.translated_box.setPalette(trans_box_pal)
        self.translated_box.textChanged.connect(self._update_trans_stats)
        trans_layout.addWidget(self.translated_box)

        # Toolbar below translated transcript
        trans_tools_layout = QHBoxLayout()
        self.trans_stats_label = QLabel("0 từ · 0 ký tự")
        self.trans_stats_label.setProperty("class", "caption")
        trans_tools_layout.addWidget(self.trans_stats_label)
        trans_tools_layout.addStretch(1)

        self.btn_save_trans_txt = QPushButton("💾 Lưu tệp .txt")
        self.btn_save_trans_txt.setProperty("class", "secondary-btn")
        self.btn_save_trans_txt.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.btn_save_trans_txt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_trans_txt.clicked.connect(self._save_translated_txt)
        trans_tools_layout.addWidget(self.btn_save_trans_txt)

        self.btn_save_trans_srt = QPushButton("🎬 Lưu tệp .srt")
        self.btn_save_trans_srt.setProperty("class", "secondary-btn")
        self.btn_save_trans_srt.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.btn_save_trans_srt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_trans_srt.clicked.connect(self._save_translated_srt)
        trans_tools_layout.addWidget(self.btn_save_trans_srt)

        self.btn_clear_trans = QPushButton("Xóa trắng")
        self.btn_clear_trans.setProperty("class", "secondary-btn")
        self.btn_clear_trans.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.btn_clear_trans.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_trans.clicked.connect(self._clear_translated)
        trans_tools_layout.addWidget(self.btn_clear_trans)

        trans_layout.addLayout(trans_tools_layout)
        results_layout.addWidget(self.translated_column, 1)

        # Hidden by default until translate checkbox is checked
        self.translated_column.setVisible(False)

        stt_card.addLayout(results_layout)
        layout.addWidget(stt_card)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    # ─── Translation Handlers ───────────────────────────────────────────

    def _on_translate_toggled(self, checked: bool) -> None:
        """Show or hide translation options and result column."""
        self.target_lang_label.setVisible(checked)
        self.combo_target_lang.setVisible(checked)
        self.btn_translate_now.setVisible(checked)
        self.translated_column.setVisible(checked)
        self.orig_title.setVisible(checked)

        has_text = bool(self.transcript_box.toPlainText().strip())
        self.btn_translate_now.setEnabled(has_text and checked)

        if checked:
            lang_label = self.combo_target_lang.currentText()
            self.translated_title.setText(f"Bản dịch ({lang_label})")
        # NOTE: Do NOT auto-translate on toggle. User must click 'Dịch văn bản'.

    def _on_target_lang_changed(self, idx: int) -> None:
        lang_label = self.combo_target_lang.currentText()
        self.translated_title.setText(f"Bản dịch ({lang_label})")

    def _translate_current_text(self) -> None:
        """Translate currently transcribed text into selected target language."""
        if self.trans_worker is not None and self.trans_worker.isRunning():
            self.status_label.setText("⏳ Đang trong quá trình dịch, vui lòng chờ...")
            return

        text = self.transcript_box.toPlainText().strip()
        if not text:
            self.btn_translate_now.setEnabled(False)
            self.status_label.setText("⚠️ Chưa có nội dung nhận dạng để dịch. Vui lòng nhận dạng âm thanh trước.")
            return

        # Synchronize any user edits made in transcript_box to segments before translating
        self.current_segments = sync_text_to_segments(text, self.current_segments)

        self.btn_translate_now.setEnabled(False)
        target_code = self.combo_target_lang.currentData() or "vi"
        self._start_translation(text, self.current_segments, target_code)

    def _start_translation(self, text: str, segments: List[Dict[str, Any]], target_lang: str) -> None:
        """Run translation asynchronously in background thread."""
        lang_name = self.combo_target_lang.currentText()
        self.status_label.setText(f"⏳ Đang dịch sang {lang_name}...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        def _do_translation():
            tr_text = translate_text(text, target_lang=target_lang)
            tr_segs = translate_segments(segments, target_lang=target_lang)
            return tr_text, tr_segs

        self._cleanup_trans_worker()
        self.trans_worker = WorkerThread(_do_translation)
        self.trans_worker.finished_task.connect(self._on_translation_finished)
        self.trans_worker.failed_task.connect(self._on_translation_failed)
        self.trans_worker.start()

    def _on_translation_finished(self, result: Any) -> None:
        self.btn_translate_now.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._cleanup_trans_worker()
        tr_text, tr_segs = result
        self.current_translated_segments = tr_segs
        display_text = tr_text or "\n".join(s["text"].strip() for s in tr_segs if s.get("text", "").strip())
        self.translated_box.setPlainText(display_text)
        self.translated_box.moveCursor(self.translated_box.textCursor().MoveOperation.End)
        lang_name = self.combo_target_lang.currentText()
        self.status_label.setText(f"✓ Đã dịch sang {lang_name} thành công!")

    def _on_translation_failed(self, error_msg: str) -> None:
        self.btn_translate_now.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._cleanup_trans_worker()
        self.status_label.setText(f"❌ Lỗi khi dịch: {error_msg}")

    def _cleanup_trans_worker(self) -> None:
        if self.trans_worker is not None:
            try:
                if self.trans_worker.isRunning():
                    self.trans_worker.quit()
                    if not self.trans_worker.wait(1000):
                        self.trans_worker.terminate()
                        self.trans_worker.wait(500)
                self.trans_worker.deleteLater()
            except Exception:
                pass
            self.trans_worker = None

    # ─── Transcription Handlers ──────────────────────────────────────────

    def _on_select_file(self) -> None:
        """Open file dialog to choose an audio file for transcription."""
        if self.worker is not None and self.worker.isRunning():
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn tệp âm thanh cần nhận dạng (.wav, .mp3, .m4a)",
            "",
            AUDIO_FILE_FILTER,
        )
        if path:
            self.selected_audio = Path(path)
            file_size_mb = self.selected_audio.stat().st_size / (1024 * 1024)
            self.file_name_label.setText(f"📁 {self.selected_audio.name} ({file_size_mb:.2f} MB)")
            self.status_label.setText(f"Đã chọn tệp: {self.selected_audio.name}. Bấm 'Bắt đầu nhận dạng' để chạy.")

    def _on_progress(self, percent: int, msg: str) -> None:
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
        self.status_label.setText(msg)
        if "nhận dạng" in msg.lower():
            self.btn_transcribe.setText("⏳ Đang nhận dạng...")

    def _cleanup_worker(self) -> None:
        if self.worker is not None:
            try:
                if self.worker.isRunning():
                    self.worker.quit()
                    if not self.worker.wait(1000):
                        self.worker.terminate()
                        self.worker.wait(500)
                self.worker.deleteLater()
            except Exception:
                pass
            self.worker = None

    def _start_transcribe(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        # 1. Kiểm tra xem mô hình STT đã được tải chưa
        if not self.engine.is_model_downloaded():
            # QMessageBox.warning(
            #     self,
            #     "Chưa có mô hình",
            #     "Mô hình nhận dạng giọng nói (Whisper Large-v3-Turbo) chưa được tải về trong thư mục models.\n\n"
            #     "Vui lòng chuyển sang mục '⚙ Cài đặt' ở thanh điều hướng để tải và khởi tạo mô hình.",
            # )
            self.status_label.setText("⚠️ Chưa có mô hình. Vui lòng vào '⚙ Cài đặt' để tải mô hình.")
            return

        # 2. Kiểm tra tệp âm thanh đầu vào
        if not self.selected_audio or not self.selected_audio.exists():
            self.status_label.setText("❌ Vui lòng chọn một tệp âm thanh để nhận dạng.")
            return

        self.btn_transcribe.setEnabled(False)
        self.btn_select_file.setEnabled(False)
        self.chk_translate.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self._run_transcribe_inference()

    def _run_transcribe_inference(self) -> None:
        self.btn_transcribe.setText("⏳ Đang nhận dạng...")
        self.status_label.setText("Đang nhận dạng âm thanh...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self._cleanup_worker()
        self.worker = WorkerThread(
            self.engine.transcribe,
            audio_source=self.selected_audio,
            beam_size=1,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_task.connect(self._on_transcribe_finished)
        self.worker.failed_task.connect(self._on_transcribe_failed)
        self.worker.start()

    def _on_transcribe_finished(self, result: Dict[str, Any]) -> None:
        self.btn_transcribe.setEnabled(True)
        self.btn_select_file.setEnabled(True)
        self.btn_transcribe.setText("Bắt đầu nhận dạng")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self._cleanup_worker()

        text = result.get("text", "")
        self.current_segments = result.get("segments", [])
        duration = result.get("duration", 0.0)
        elapsed = result.get("elapsed_time", 0.0)
        source = result.get("source", "")

        msg = f"✓ Hoàn tất trong {elapsed:.2f}s | Thời lượng: {duration:.2f}s | Tệp: {source}"
        self.status_label.setText(msg)
        self.status_updated.emit(msg)

        if len(self.current_segments) > 1:
            display_text = "\n".join(s["text"].strip() for s in self.current_segments if s.get("text", "").strip())
        else:
            display_text = text
        self.transcript_box.setPlainText(display_text or text)
        self.transcript_box.moveCursor(self.transcript_box.textCursor().MoveOperation.End)

        # Enable translate checkbox and button only when recognized text is available
        has_text = bool(text.strip())
        self.chk_translate.setEnabled(has_text)
        self.btn_translate_now.setEnabled(has_text)

    def _on_transcribe_failed(self, error_msg: str) -> None:
        self.btn_transcribe.setEnabled(True)
        self.btn_select_file.setEnabled(True)
        has_text = bool(self.transcript_box.toPlainText().strip())
        self.chk_translate.setEnabled(has_text)
        self.btn_translate_now.setEnabled(has_text)
        self.btn_transcribe.setText("Bắt đầu nhận dạng")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self._cleanup_worker()
        self.status_label.setText(f"❌ Lỗi: {error_msg}")

    # ─── Text Statistics ─────────────────────────────────────────────────

    def _update_text_stats(self) -> None:
        text = self.transcript_box.toPlainText().strip()
        words = len(text.split()) if text else 0
        chars = len(text)
        self.stats_label.setText(f"{words} từ · {chars} ký tự")
        has_text = bool(text)
        self.chk_translate.setEnabled(has_text)
        self.btn_translate_now.setEnabled(has_text)
        if not has_text and self.chk_translate.isChecked():
            self.chk_translate.setChecked(False)

    def _update_trans_stats(self) -> None:
        text = self.translated_box.toPlainText().strip()
        words = len(text.split()) if text else 0
        chars = len(text)
        self.trans_stats_label.setText(f"{words} từ · {chars} ký tự")

    # ─── File Export / Clear (Original) ──────────────────────────────────

    def _save_txt(self) -> None:
        text = self.transcript_box.toPlainText()
        if not text:
            self.status_label.setText("Chưa có nội dung văn bản để lưu.")
            return

        stem = self.selected_audio.stem if self.selected_audio else f"transcript_{time.strftime('%Y%m%d_%H%M%S')}"
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu văn bản nhận dạng (.txt)",
            str(OUTPUTS_DIR / f"{stem}.txt"),
            "Tệp văn bản (*.txt);;Tất cả tệp (*.*)",
        )
        if out_path:
            Path(out_path).write_text(text, encoding="utf-8")
            self.status_label.setText(f"Đã lưu văn bản thành công vào:\n{out_path}")

    def _save_srt(self) -> None:
        """Export transcription segments with timestamps into standard .srt format."""
        text = self.transcript_box.toPlainText().strip()
        if not text and not self.current_segments:
            self.status_label.setText("Chưa có dữ liệu phụ đề hoặc kết quả nhận dạng để lưu file .srt.")
            return

        self.current_segments = sync_text_to_segments(text, self.current_segments)
        if not self.current_segments:
            self.status_label.setText("Chưa có dữ liệu phụ đề hoặc kết quả nhận dạng để lưu file .srt.")
            return

        stem = self.selected_audio.stem if self.selected_audio else f"subtitles_{time.strftime('%Y%m%d_%H%M%S')}"
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu tệp phụ đề (.srt)",
            str(OUTPUTS_DIR / f"{stem}.srt"),
            "Tệp phụ đề (*.srt);;Tất cả tệp (*.*)",
        )
        if out_path:
            srt_content = format_srt(self.current_segments)
            Path(out_path).write_text(srt_content, encoding="utf-8")
            self.status_label.setText(f"Đã lưu tệp phụ đề .srt thành công vào:\n{out_path}")

    def _clear_transcript(self) -> None:
        self._cleanup_trans_worker()
        self.transcript_box.clear()
        self.current_segments = []
        self.chk_translate.setChecked(False)
        self.chk_translate.setEnabled(False)
        self.btn_translate_now.setEnabled(False)
        self.translated_box.clear()
        self.current_translated_segments = []
        self.translated_column.setVisible(False)
        self.progress_bar.setVisible(False)

    # ─── File Export / Clear (Translated) ────────────────────────────────

    def _save_translated_txt(self) -> None:
        text = self.translated_box.toPlainText()
        if not text:
            self.status_label.setText("Chưa có nội dung bản dịch để lưu.")
            return

        target_code = self.combo_target_lang.currentData() or "vi"
        stem = self.selected_audio.stem if self.selected_audio else f"transcript_{time.strftime('%Y%m%d_%H%M%S')}"
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu bản dịch (.txt)",
            str(OUTPUTS_DIR / f"{stem}_translated_{target_code}.txt"),
            "Tệp văn bản (*.txt);;Tất cả tệp (*.*)",
        )
        if out_path:
            Path(out_path).write_text(text, encoding="utf-8")
            self.status_label.setText(f"Đã lưu bản dịch thành công vào:\n{out_path}")

    def _save_translated_srt(self) -> None:
        """Export translated subtitle segments with timestamps into .srt format."""
        text = self.translated_box.toPlainText().strip()
        if not text and not self.current_translated_segments:
            self.status_label.setText("Chưa có dữ liệu phụ đề bản dịch để lưu file .srt.")
            return

        self.current_translated_segments = sync_text_to_segments(text, self.current_translated_segments)
        if not self.current_translated_segments:
            self.status_label.setText("Chưa có dữ liệu phụ đề bản dịch để lưu file .srt.")
            return

        target_code = self.combo_target_lang.currentData() or "vi"
        stem = self.selected_audio.stem if self.selected_audio else f"subtitles_{time.strftime('%Y%m%d_%H%M%S')}"
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu tệp phụ đề bản dịch (.srt)",
            str(OUTPUTS_DIR / f"{stem}_translated_{target_code}.srt"),
            "Tệp phụ đề (*.srt);;Tất cả tệp (*.*)",
        )
        if out_path:
            srt_content = format_srt(self.current_translated_segments)
            Path(out_path).write_text(srt_content, encoding="utf-8")
            self.status_label.setText(f"Đã lưu tệp phụ đề bản dịch .srt thành công vào:\n{out_path}")

    def _clear_translated(self) -> None:
        self.translated_box.clear()
        self.current_translated_segments = []
