"""Video Subtitle (Phụ đề Video) interface for Neu Audio Studio.

Supports 2-stage video subtitle processing:
1. Giai đoạn 1: Trích xuất audio từ video, nhận dạng STT và dịch thuật sang ngôn ngữ đích (.srt).
2. Giai đoạn 2: Tạo video với phụ đề được gán trực tiếp (burn-in / hardsub) vào video gốc, giữ nguyên âm thanh.
Tất cả các tham số đầu vào được khóa trong suốt thời gian xử lý chức năng.
"""
import time
import shutil
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
    QComboBox,
    QMessageBox,
)

from core.config import (
    VIDEO_FILE_FILTER,
    OUTPUTS_DIR,
)
from core.worker import WorkerThread
from core.translator import SUPPORTED_TRANSLATION_LANGUAGES, translate_text, translate_segments
from core.dubbing_service import (
    extract_audio_from_video,
    get_media_duration,
    burn_subtitles_into_video,
)
from engines.stt_engine import STTEngine, format_srt, sync_text_to_segments
from ui.components.card import Card
from ui.components.video_player import VideoPlayer
from ui.styles import PRIMARY_BUTTON_STYLE, SECONDARY_BUTTON_STYLE


class VideoSubtitleView(QWidget):
    """Modern 2-stage Video Subtitle View with transcription, translation, and video burn-in preview."""

    status_updated = pyqtSignal(str)

    def __init__(self, stt_engine: STTEngine, tts_engine: Optional[Any] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.stt_engine = stt_engine

        # State Variables
        self.selected_video: Optional[Path] = None
        self.extracted_audio: Optional[Path] = None
        self.current_segments: List[Dict[str, Any]] = []
        self.current_translated_segments: List[Dict[str, Any]] = []
        self.current_srt_path: Optional[Path] = None
        self.subtitled_video_path: Optional[Path] = None
        self.video_duration: float = 0.0

        self.worker: Optional[WorkerThread] = None

        self._setup_ui()

    def refresh_state(self) -> None:
        """Refresh view controls."""
        pass

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
        title_label = QLabel("Phụ đề Video")
        title_label.setProperty("class", "header-title")
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        layout.addLayout(header_layout)

        # ═══════════════════════════════════════════════════════════════════
        # CARD 1: Giai đoạn 1 - Chọn Video & Tạo Văn Bản Phụ Đề
        # ═══════════════════════════════════════════════════════════════════
        self.card_stage1 = Card()

        stage1_title = QLabel("1. Chọn video & Tạo văn bản phụ đề")
        stage1_title.setProperty("class", "section-title")
        self.card_stage1.addWidget(stage1_title)

        # Video select & Target language row
        v_select_row = QHBoxLayout()
        v_select_row.setSpacing(12)

        self.btn_select_video = QPushButton("📁 Chọn video cần gán phụ đề")
        self.btn_select_video.setProperty("class", "secondary-btn")
        self.btn_select_video.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.btn_select_video.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_video.setMinimumHeight(40)
        self.btn_select_video.clicked.connect(self._on_select_video)
        v_select_row.addWidget(self.btn_select_video)

        self.video_name_label = QLabel("Chưa chọn tệp video (.mp4, .mkv, .avi, ...)")
        self.video_name_label.setProperty("class", "caption")
        self.video_name_label.setStyleSheet("color: #475569; font-size: 13px;")
        v_select_row.addWidget(self.video_name_label, 1)

        lang_label = QLabel("Ngôn ngữ dịch:")
        lang_label.setStyleSheet("color: #475569; font-size: 13px; font-weight: 500;")
        v_select_row.addWidget(lang_label)

        self.combo_target_lang = QComboBox()
        for label, code in SUPPORTED_TRANSLATION_LANGUAGES:
            self.combo_target_lang.addItem(label, code)
        self.combo_target_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_target_lang.setMinimumWidth(150)
        v_select_row.addWidget(self.combo_target_lang)

        self.card_stage1.addLayout(v_select_row)

        # Action Button 1: Tạo văn bản
        action_row1 = QHBoxLayout()
        self.btn_create_transcript = QPushButton("📝 Tạo văn bản")
        self.btn_create_transcript.setProperty("class", "primary-btn")
        self.btn_create_transcript.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.btn_create_transcript.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_create_transcript.setMinimumHeight(42)
        self.btn_create_transcript.clicked.connect(self._start_stage1_transcript)
        action_row1.addWidget(self.btn_create_transcript)
        self.card_stage1.addLayout(action_row1)

        # Progress 1
        self.progress_bar_1 = QProgressBar()
        self.progress_bar_1.setRange(0, 0)
        self.progress_bar_1.setTextVisible(False)
        self.progress_bar_1.setVisible(False)
        self.progress_bar_1.setFixedHeight(5)
        self.progress_bar_1.setStyleSheet("""
            QProgressBar { background-color: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 5px; }
            QProgressBar::chunk { background-color: #4F46E5; border-radius: 5px; }
        """)
        self.card_stage1.addWidget(self.progress_bar_1)

        self.status_label_1 = QLabel("Sẵn sàng. Vui lòng chọn tệp video cần gán phụ đề.")
        self.status_label_1.setProperty("class", "caption")
        self.card_stage1.addWidget(self.status_label_1)

        # Sub-Card: Text boxes (Original + Translated)
        results_layout = QHBoxLayout()
        results_layout.setSpacing(14)

        # Original column
        col_orig = QVBoxLayout()
        orig_lbl = QLabel("Văn bản nhận dạng gốc:")
        orig_lbl.setStyleSheet("font-weight: 600; font-size: 13px; color: #334155;")
        col_orig.addWidget(orig_lbl)

        self.orig_text_box = QTextEdit()
        self.orig_text_box.setReadOnly(False)
        self.orig_text_box.setAcceptRichText(False)
        self.orig_text_box.setPlaceholderText("Văn bản gốc sau khi nhận dạng từ video sẽ xuất hiện ở đây (có thể chỉnh sửa)...")
        self.orig_text_box.setMinimumHeight(160)
        box_pal = self.orig_text_box.palette()
        box_pal.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
        box_pal.setColor(QPalette.ColorRole.Text, QColor("#0F172A"))
        box_pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#94A3B8"))
        self.orig_text_box.setPalette(box_pal)
        self.orig_text_box.textChanged.connect(self._on_orig_text_changed)
        col_orig.addWidget(self.orig_text_box)
        results_layout.addLayout(col_orig, 1)

        # Translated column
        col_trans = QVBoxLayout()
        self.trans_box_lbl = QLabel("Văn bản sau khi dịch:")
        self.trans_box_lbl.setStyleSheet("font-weight: 600; font-size: 13px; color: #334155;")
        col_trans.addWidget(self.trans_box_lbl)

        self.trans_text_box = QTextEdit()
        self.trans_text_box.setReadOnly(False)
        self.trans_text_box.setAcceptRichText(False)
        self.trans_text_box.setPlaceholderText("Văn bản dịch (sẽ làm phụ đề) sẽ xuất hiện ở đây (có thể chỉnh sửa)...")
        self.trans_text_box.setMinimumHeight(160)
        self.trans_text_box.setPalette(box_pal)
        self.trans_text_box.textChanged.connect(self._on_trans_text_changed)
        col_trans.addWidget(self.trans_text_box)
        results_layout.addLayout(col_trans, 1)

        self.card_stage1.addLayout(results_layout)

        # Subtitle export tools
        srt_tools_row = QHBoxLayout()
        self.stats_label = QLabel("0 từ · 0 câu phụ đề")
        self.stats_label.setProperty("class", "caption")
        srt_tools_row.addWidget(self.stats_label)
        srt_tools_row.addStretch(1)

        self.btn_save_srt = QPushButton("🎬 Lưu phụ đề .srt")
        self.btn_save_srt.setProperty("class", "secondary-btn")
        self.btn_save_srt.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.btn_save_srt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_srt.setEnabled(False)
        self.btn_save_srt.clicked.connect(self._save_subtitles_srt)
        srt_tools_row.addWidget(self.btn_save_srt)

        self.card_stage1.addLayout(srt_tools_row)
        layout.addWidget(self.card_stage1)

        # ═══════════════════════════════════════════════════════════════════
        # CARD 2: Giai đoạn 2 - Tạo Video & Gán Phụ Đề (Burn-in Subtitles)
        # ═══════════════════════════════════════════════════════════════════
        self.card_stage2 = Card()

        stage2_title = QLabel("2. Gán phụ đề & Tạo video hoàn chỉnh")
        stage2_title.setProperty("class", "section-title")
        self.card_stage2.addWidget(stage2_title)

        # Action Button 2: Tạo video
        action_row2 = QHBoxLayout()
        self.btn_create_video = QPushButton("🎬 Tạo video")
        self.btn_create_video.setProperty("class", "primary-btn")
        self.btn_create_video.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.btn_create_video.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_create_video.setMinimumHeight(44)
        self.btn_create_video.setEnabled(False)
        self.btn_create_video.clicked.connect(self._start_stage2_burn_video)
        action_row2.addWidget(self.btn_create_video)
        self.card_stage2.addLayout(action_row2)

        # Progress 2
        self.progress_bar_2 = QProgressBar()
        self.progress_bar_2.setRange(0, 0)
        self.progress_bar_2.setTextVisible(False)
        self.progress_bar_2.setVisible(False)
        self.progress_bar_2.setFixedHeight(5)
        self.progress_bar_2.setStyleSheet("""
            QProgressBar { background-color: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 5px; }
            QProgressBar::chunk { background-color: #4F46E5; border-radius: 5px; }
        """)
        self.card_stage2.addWidget(self.progress_bar_2)

        self.status_label_2 = QLabel("Chưa có phụ đề. Hoàn tất Giai đoạn 1 để mở khóa tính năng gán phụ đề vào video.")
        self.status_label_2.setProperty("class", "caption")
        self.card_stage2.addWidget(self.status_label_2)

        # Video Player Container with centering to fit video aspect ratio cleanly
        self.video_container = QWidget()
        container_layout = QHBoxLayout(self.video_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.video_player = VideoPlayer(placeholder_text="Video sau khi gán phụ đề sẽ hiển thị tại đây")
        container_layout.addWidget(self.video_player)
        self.card_stage2.addWidget(self.video_container)

        self.video_player.aspect_ratio_changed.connect(lambda _: self._update_video_player_size())

        # Save video button row
        save_video_row = QHBoxLayout()
        save_video_row.addStretch(1)
        self.btn_save_video = QPushButton("💾 Lưu video hoàn chỉnh (.mp4)")
        self.btn_save_video.setProperty("class", "secondary-btn")
        self.btn_save_video.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.btn_save_video.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_video.setEnabled(False)
        self.btn_save_video.clicked.connect(self._save_final_video)
        save_video_row.addWidget(self.btn_save_video)
        self.card_stage2.addLayout(save_video_row)

        layout.addWidget(self.card_stage2)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    # ─── Responsive Aspect Ratio Sizing ──────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_video_player_size()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_video_player_size()

    def _update_video_player_size(self) -> None:
        """Dynamically fit video card player size to video aspect ratio, eliminating side black bars."""
        if hasattr(self, "video_player") and hasattr(self, "video_container"):
            avail_w = self.video_container.width()
            if avail_w <= 100:
                avail_w = max(400, self.card_stage2.width() - 40)
            self.video_player.update_aspect_size(available_width=avail_w)

    # ─── Input Locking Helper ────────────────────────────────────────────

    def _on_orig_text_changed(self) -> None:
        text = self.orig_text_box.toPlainText().strip()
        if hasattr(self, "current_segments") and self.current_segments:
            self.current_segments = sync_text_to_segments(text, self.current_segments)

    def _on_trans_text_changed(self) -> None:
        text = self.trans_text_box.toPlainText().strip()
        words = len(text.split()) if text else 0
        segs_count = len(text.splitlines()) if "\n" in text else (len(self.current_translated_segments) or (1 if text else 0))
        self.stats_label.setText(f"{words} từ · {segs_count} câu phụ đề")
        has_text = bool(text)
        is_idle = self.worker is None or not self.worker.isRunning()
        self.btn_save_srt.setEnabled(is_idle and has_text)
        self.btn_create_video.setEnabled(is_idle and has_text and self.selected_video is not None)
        if hasattr(self, "current_translated_segments") and self.current_translated_segments:
            self.current_translated_segments = sync_text_to_segments(text, self.current_translated_segments)

    def _set_inputs_enabled(self, enabled: bool) -> None:
        """Lock or unlock input parameters during asynchronous processing.

        When a function is running, all input parameters are strictly disabled.
        They are re-enabled only before running or after the task has completed.
        """
        self.btn_select_video.setEnabled(enabled)
        self.combo_target_lang.setEnabled(enabled)
        self.btn_create_transcript.setEnabled(enabled)

        has_subtitles = bool(self.trans_text_box.toPlainText().strip()) or bool(self.current_translated_segments)
        self.btn_save_srt.setEnabled(enabled and has_subtitles)
        self.btn_create_video.setEnabled(enabled and has_subtitles and self.selected_video is not None)

        has_final_video = self.subtitled_video_path is not None and self.subtitled_video_path.exists()
        self.btn_save_video.setEnabled(enabled and has_final_video)

        self.orig_text_box.setReadOnly(not enabled)
        self.trans_text_box.setReadOnly(not enabled)

        if enabled:
            self.btn_create_transcript.setText("📝 Tạo văn bản")

    # ─── Worker Safety Cleanup ──────────────────────────────────────────

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

    # ═════════════════════════════════════════════════════════════════════
    # GIAI ĐOẠN 1: Chọn video -> STT -> Translate -> .srt
    # ═════════════════════════════════════════════════════════════════════

    def _on_select_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn tệp video cần gán phụ đề",
            "",
            VIDEO_FILE_FILTER,
        )
        if path:
            self.selected_video = Path(path)
            size_mb = self.selected_video.stat().st_size / (1024 * 1024)
            self.video_name_label.setText(f"🎥 {self.selected_video.name} ({size_mb:.2f} MB)")
            self.status_label_1.setText(f"Đã chọn: {self.selected_video.name}. Nhấn 'Tạo văn bản' để bắt đầu.")

            # Pre-probe aspect ratio so player is prepared for the video format
            try:
                from core.dubbing_service import get_video_resolution
                res = get_video_resolution(self.selected_video)
                if res and res[1] > 0:
                    self.video_player.video_aspect_ratio = res[0] / res[1]
                    self.video_player.video_resolution = res
            except Exception:
                pass

    def _start_stage1_transcript(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        # 1. Kiểm tra xem mô hình STT đã được tải chưa
        if not self.stt_engine.is_model_downloaded():
            QMessageBox.warning(
                self,
                "Chưa có mô hình",
                "Mô hình nhận dạng giọng nói (Whisper Large-v3-Turbo) chưa được tải về trong thư mục models.\n\n"
                "Vui lòng chuyển sang mục '⚙ Cài đặt' ở thanh điều hướng để tải và khởi tạo mô hình.",
            )
            self.status_label_1.setText("⚠️ Chưa có mô hình. Vui lòng vào '⚙ Cài đặt' để tải mô hình.")
            return

        # 2. Đã có mô hình, kiểm tra tệp video đầu vào
        if not self.selected_video or not self.selected_video.exists():
            self.status_label_1.setText("❌ Vui lòng chọn tệp video cần gán phụ đề trước.")
            return

        self._run_stage1_processing()

    def _run_stage1_processing(self) -> None:
        """Run stage 1 audio extraction, STT transcription, and translation."""
        # Lock all inputs during processing
        self._set_inputs_enabled(False)
        self.btn_create_transcript.setText("⏳ Đang xử lý...")
        self.progress_bar_1.setVisible(True)
        self.progress_bar_1.setRange(0, 0)

        target_lang = self.combo_target_lang.currentData() or "vi"
        target_name = self.combo_target_lang.currentText()
        self.trans_box_lbl.setText(f"Văn bản sau khi dịch ({target_name}):")

        # Background task
        def _task_stage1():
            # 1. Trích xuất audio
            self.status_label_1.setText("⏳ Đang trích xuất audio từ video...")
            extracted_wav = extract_audio_from_video(self.selected_video)

            # 2. Lấy thời lượng
            duration = get_media_duration(extracted_wav)

            # 3. Chạy STT
            self.status_label_1.setText("⏳ Đang nhận dạng âm thanh...")
            stt_res = self.stt_engine.transcribe(extracted_wav, beam_size=1)
            orig_text = stt_res.get("text", "")
            orig_segments = stt_res.get("segments", [])

            # 4. Dịch sang ngôn ngữ đích
            self.status_label_1.setText(f"⏳ Đang dịch sang {target_name}...")
            trans_text = translate_text(orig_text, target_lang=target_lang)
            trans_segments = translate_segments(orig_segments, target_lang=target_lang)

            # 5. Lưu tạm file .srt
            srt_content = format_srt(trans_segments)
            temp_srt = OUTPUTS_DIR / f"_temp_subtitles_{int(time.time())}.srt"
            temp_srt.write_text(srt_content, encoding="utf-8")

            return {
                "extracted_audio": extracted_wav,
                "duration": duration,
                "orig_text": orig_text,
                "orig_segments": orig_segments,
                "trans_text": trans_text,
                "trans_segments": trans_segments,
                "srt_path": temp_srt,
            }

        self._cleanup_worker()
        self.worker = WorkerThread(_task_stage1)
        self.worker.finished_task.connect(self._on_stage1_finished)
        self.worker.failed_task.connect(self._on_stage1_failed)
        self.worker.start()

    def _on_stage1_finished(self, result: Dict[str, Any]) -> None:
        self.btn_create_transcript.setText("📝 Tạo văn bản")
        self.progress_bar_1.setVisible(False)
        self._cleanup_worker()

        self.extracted_audio = result["extracted_audio"]
        self.video_duration = result["duration"]
        self.current_segments = result["orig_segments"]
        self.current_translated_segments = result["trans_segments"]
        self.current_srt_path = result["srt_path"]

        orig_text = result["orig_text"]
        trans_text = result["trans_text"]

        if len(self.current_segments) > 1:
            disp_orig = "\n".join(s["text"].strip() for s in self.current_segments if s.get("text", "").strip())
        else:
            disp_orig = orig_text

        if len(self.current_translated_segments) > 1:
            disp_trans = "\n".join(s["text"].strip() for s in self.current_translated_segments if s.get("text", "").strip())
        else:
            disp_trans = trans_text

        self.orig_text_box.setPlainText(disp_orig or orig_text)
        self.trans_text_box.setPlainText(disp_trans or trans_text)

        words = len(trans_text.split()) if trans_text else 0
        segs_count = len(self.current_translated_segments)
        self.stats_label.setText(f"{words} từ · {segs_count} câu phụ đề")

        # Unlock all inputs now that Stage 1 has finished
        self._set_inputs_enabled(True)

        self.status_label_1.setText(f"✓ Hoàn tất tạo văn bản! Phát hiện {segs_count} câu phụ đề.")
        self.status_label_2.setText("Đã có dữ liệu phụ đề. Nhấn 'Tạo video' để gán phụ đề trực tiếp vào video.")

    def _on_stage1_failed(self, err: str) -> None:
        self.btn_create_transcript.setText("📝 Tạo văn bản")
        self.progress_bar_1.setVisible(False)
        self._cleanup_worker()
        self._set_inputs_enabled(True)
        self.status_label_1.setText(f"❌ Lỗi tạo văn bản: {err}")

    def _save_subtitles_srt(self) -> None:
        text = self.trans_text_box.toPlainText().strip()
        if not text and not self.current_translated_segments:
            return

        self.current_translated_segments = sync_text_to_segments(text, self.current_translated_segments)
        if not self.current_translated_segments:
            return

        target_code = self.combo_target_lang.currentData() or "vi"
        stem = self.selected_video.stem if self.selected_video else "subtitles"
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu tệp phụ đề (.srt)",
            str(OUTPUTS_DIR / f"{stem}_{target_code}.srt"),
            "Tệp phụ đề (*.srt);;Tất cả tệp (*.*)",
        )
        if out_path:
            srt_content = format_srt(self.current_translated_segments)
            Path(out_path).write_text(srt_content, encoding="utf-8")
            self.status_label_1.setText(f"✓ Đã lưu tệp phụ đề: {Path(out_path).name}")

    # ═════════════════════════════════════════════════════════════════════
    # GIAI ĐOẠN 2: Gán phụ đề vào video (Burn-in hardsub)
    # ═════════════════════════════════════════════════════════════════════

    def _start_stage2_burn_video(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        text = self.trans_text_box.toPlainText().strip()
        if not self.selected_video or (not text and not self.current_translated_segments):
            self.status_label_2.setText("❌ Chưa đủ dữ liệu video gốc hoặc tệp phụ đề.")
            return

        # Synchronize latest user edits from trans_text_box into segments
        self.current_translated_segments = sync_text_to_segments(text, self.current_translated_segments)
        if not self.current_translated_segments:
            self.status_label_2.setText("❌ Nội dung phụ đề trống, vui lòng nhập phụ đề.")
            return

        # Always re-write temp srt with latest edited subtitles
        srt_content = format_srt(self.current_translated_segments)
        self.current_srt_path = OUTPUTS_DIR / f"_temp_subtitles_{int(time.time())}.srt"
        self.current_srt_path.write_text(srt_content, encoding="utf-8")

        # Lock all inputs during video generation
        self._set_inputs_enabled(False)
        self.btn_create_video.setText("⏳ Đang gán phụ đề vào video...")
        self.progress_bar_2.setVisible(True)
        self.progress_bar_2.setRange(0, 0)
        self.status_label_2.setText("⏳ Đang gán phụ đề và xuất video hoàn chỉnh...")

        def _task_stage2(progress_callback):
            return burn_subtitles_into_video(
                video_path=self.selected_video,
                srt_path=self.current_srt_path,
                font_size=18,
                progress_callback=progress_callback,
            )

        self._cleanup_worker()
        self.worker = WorkerThread(_task_stage2)
        self.worker.finished_task.connect(self._on_stage2_finished)
        self.worker.failed_task.connect(self._on_stage2_failed)
        self.worker.start()

    def _on_stage2_finished(self, out_video: Path) -> None:
        self.btn_create_video.setText("🎬 Tạo video")
        self.progress_bar_2.setVisible(False)
        self._cleanup_worker()

        self.subtitled_video_path = out_video
        self.video_player.load_video(self.subtitled_video_path)
        self._update_video_player_size()

        # Unlock all inputs now that Stage 2 has finished
        self._set_inputs_enabled(True)
        self.status_label_2.setText("✓ Đã gán phụ đề vào video hoàn chỉnh thành công!")

    def _on_stage2_failed(self, err: str) -> None:
        self.btn_create_video.setText("🎬 Tạo video")
        self.progress_bar_2.setVisible(False)
        self._cleanup_worker()
        self._set_inputs_enabled(True)
        self.status_label_2.setText(f"❌ Lỗi tạo video: {err}")

    def _save_final_video(self) -> None:
        if not self.subtitled_video_path or not self.subtitled_video_path.exists():
            return

        stem = self.selected_video.stem if self.selected_video else "video_subtitled"
        target_code = self.combo_target_lang.currentData() or "vi"
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu video có phụ đề (.mp4)",
            str(OUTPUTS_DIR / f"{stem}_subtitled_{target_code}.mp4"),
            "Tệp video MP4 (*.mp4);;Tất cả tệp (*.*)",
        )
        if out_path:
            shutil.copy2(str(self.subtitled_video_path), out_path)
            self.status_label_2.setText(f"✓ Đã lưu video thành công vào: {Path(out_path).name}")


# Alias for backwards compatibility
DubbingView = VideoSubtitleView
