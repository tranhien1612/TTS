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
    QMessageBox,
    QApplication,
)

from core.config import (
    AUDIO_FILE_FILTER,
    OUTPUTS_DIR,
)
from core.worker import WorkerThread
from engines.stt_engine import STTEngine, format_srt
from ui.components.card import Card
from ui.styles import PRIMARY_BUTTON_STYLE, SECONDARY_BUTTON_STYLE


class STTView(QWidget):
    """Speech-to-Text interface with file transcription and SRT subtitle export."""

    status_updated = pyqtSignal(str)

    def __init__(self, stt_engine: STTEngine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = stt_engine
        self.selected_audio: Optional[Path] = None
        self.current_segments: List[Dict[str, Any]] = []
        self.worker: Optional[WorkerThread] = None

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

        # --- Unified Single Card: File Selection & Transcript Result ---
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
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setStyleSheet("background-color: #E2E8F0; max-height: 1px; border: none; margin-top: 4px; margin-bottom: 4px;")
        stt_card.addWidget(divider)

        # Section 2: Transcript Display (Read-Only)
        result_title = QLabel("Kết quả nhận dạng")
        result_title.setProperty("class", "section-title")
        stt_card.addWidget(result_title)

        self.transcript_box = QTextEdit()
        self.transcript_box.setReadOnly(True)  # Display-only
        self.transcript_box.setAcceptRichText(False)
        self.transcript_box.setPlaceholderText("Văn bản sau khi nhận dạng từ tệp âm thanh sẽ hiển thị tại đây...")
        self.transcript_box.setMinimumHeight(200)
        box_pal = self.transcript_box.palette()
        box_pal.setColor(QPalette.ColorRole.Base, QColor("#F8FAFC"))
        box_pal.setColor(QPalette.ColorRole.Text, QColor("#0F172A"))
        box_pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#94A3B8"))
        self.transcript_box.setPalette(box_pal)
        self.transcript_box.textChanged.connect(self._update_text_stats)
        stt_card.addWidget(self.transcript_box)

        # Toolbar below transcript
        tools_layout = QHBoxLayout()
        self.stats_label = QLabel("0 từ · 0 ký tự")
        self.stats_label.setProperty("class", "caption")
        tools_layout.addWidget(self.stats_label)
        tools_layout.addStretch(1)

        save_txt_btn = QPushButton("💾 Lưu tệp .txt")
        save_txt_btn.setProperty("class", "secondary-btn")
        save_txt_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        save_txt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_txt_btn.clicked.connect(self._save_txt)
        tools_layout.addWidget(save_txt_btn)

        save_srt_btn = QPushButton("🎬 Lưu tệp .srt")
        save_srt_btn.setProperty("class", "secondary-btn")
        save_srt_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        save_srt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_srt_btn.clicked.connect(self._save_srt)
        tools_layout.addWidget(save_srt_btn)

        clear_btn = QPushButton("Xóa trắng")
        clear_btn.setProperty("class", "secondary-btn")
        clear_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_transcript)
        tools_layout.addWidget(clear_btn)

        stt_card.addLayout(tools_layout)
        layout.addWidget(stt_card)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _on_select_file(self) -> None:
        """Open file dialog to choose an audio file for transcription."""
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
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
        else:
            self.progress_bar.setRange(0, 0)
        self.status_label.setText(msg)
        if "nhận dạng" in msg.lower():
            self.btn_transcribe.setText("⏳ Đang nhận dạng...")

    def _cleanup_worker(self) -> None:
        if self.worker is not None:
            try:
                self.worker.quit()
                self.worker.wait(200)
                self.worker.deleteLater()
            except Exception:
                pass
            self.worker = None

    def _start_transcribe(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        if not self.selected_audio or not self.selected_audio.exists():
            self.status_label.setText("❌ Vui lòng chọn một tệp âm thanh để nhận dạng.")
            # QMessageBox.warning(self, "Thiếu tệp âm thanh", "Vui lòng chọn một tệp âm thanh để nhận dạng.")
            return

        self.btn_transcribe.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        # 1. Nếu chưa tải model: Tải trước, báo hoàn tất rồi mới chạy nhận dạng
        if not self.engine.is_model_downloaded():
            self.btn_transcribe.setText("⏳ Đang tải mô hình...")
            self.status_label.setText("Đang tải mô hình...")

            self._cleanup_worker()
            self.worker = WorkerThread(self.engine.ensure_model_downloaded)
            self.worker.progress.connect(self._on_progress)
            self.worker.finished_task.connect(self._on_download_finished_and_transcribe)
            self.worker.failed_task.connect(self._on_transcribe_failed)
            self.worker.start()
        else:
            self._run_transcribe_inference()

    def _on_download_finished_and_transcribe(self, _=None) -> None:
        self.status_label.setText("Đã tải xong mô hình.")
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
            language="vi",
            beam_size=1,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_task.connect(self._on_transcribe_finished)
        self.worker.failed_task.connect(self._on_transcribe_failed)
        self.worker.start()

    def _on_transcribe_finished(self, result: Dict[str, Any]) -> None:
        self.btn_transcribe.setEnabled(True)
        self.btn_transcribe.setText("Bắt đầu nhận dạng")
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

        self.transcript_box.setPlainText(text)
        self.transcript_box.moveCursor(self.transcript_box.textCursor().MoveOperation.End)

    def _on_transcribe_failed(self, error_msg: str) -> None:
        self.btn_transcribe.setEnabled(True)
        self.btn_transcribe.setText("Bắt đầu nhận dạng")
        self.progress_bar.setVisible(False)
        self._cleanup_worker()
        self.status_label.setText(f"❌ Lỗi: {error_msg}")
        # QMessageBox.critical(self, "Lỗi nhận dạng", f"Đã xảy ra lỗi khi nhận dạng tệp:\n{error_msg}")

    def _update_text_stats(self) -> None:
        text = self.transcript_box.toPlainText().strip()
        words = len(text.split()) if text else 0
        chars = len(text)
        self.stats_label.setText(f"{words} từ · {chars} ký tự")

    def _save_txt(self) -> None:
        text = self.transcript_box.toPlainText()
        if not text:
            # QMessageBox.information(self, "Thông báo", "Chưa có nội dung văn bản để lưu.")
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
            # QMessageBox.information(self, "Thành công", f"Đã lưu văn bản thành công vào:\n{out_path}")

    def _save_srt(self) -> None:
        """Export transcription segments with timestamps into standard .srt format."""
        if not self.current_segments:
            # QMessageBox.information(self, "Thông báo", "Chưa có dữ liệu phụ đề hoặc kết quả nhận dạng để lưu file .srt.")
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
            # QMessageBox.information(
            #     self,
            #     "Thành công",
            #     f"Đã lưu tệp phụ đề .srt thành công vào:\n{out_path}\n(Gồm {len(self.current_segments)} phân đoạn thời gian)",
            # )

    def _clear_transcript(self) -> None:
        self.transcript_box.clear()
        self.current_segments = []
