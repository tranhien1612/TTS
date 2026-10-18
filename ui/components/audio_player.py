import shutil
from pathlib import Path
from typing import Optional, List
import numpy as np
import soundfile as sf

from PyQt6.QtCore import QUrl, Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QMouseEvent, QPaintEvent
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QLabel,
    QFileDialog,
    QMessageBox,
)
from ui.components.card import Card
from ui.styles import PRIMARY_BUTTON_STYLE, SECONDARY_BUTTON_STYLE


class WaveformSeekBar(QWidget):
    """Custom waveform visualizer seek bar displaying audio peaks with interactive scrubbing."""

    seekRequested = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setEnabled(False)

        self.duration: int = 0
        self.position: int = 0
        self._is_dragging: bool = False
        self.num_bars: int = 64
        # Default placeholder waveform heights
        self.peaks: List[float] = [
            max(0.18, min(0.9, 0.25 + 0.35 * abs(np.sin(i / 3.8))))
            for i in range(self.num_bars)
        ]

    def load_peaks_from_file(self, audio_path: Path) -> None:
        """Extract peak amplitudes across num_bars segments from the audio file."""
        try:
            data, _ = sf.read(str(audio_path))
            if data.ndim > 1:
                data = data[:, 0]
            if len(data) > 0:
                chunks = np.array_split(data, self.num_bars)
                raw_peaks = [float(np.max(np.abs(c))) if len(c) > 0 else 0.1 for c in chunks]
                max_p = max(raw_peaks) if max(raw_peaks) > 0 else 1.0
                self.peaks = [max(0.18, min(1.0, p / max_p)) for p in raw_peaks]
            else:
                self.peaks = [0.25] * self.num_bars
        except Exception:
            # Fallback aesthetic wave if audio read fails
            self.peaks = [
                max(0.18, min(0.95, 0.25 + 0.45 * abs(np.sin(i / 3.5))))
                for i in range(self.num_bars)
            ]
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        n = len(self.peaks)
        if n == 0 or w <= 0 or h <= 0:
            return

        bar_spacing = w / n
        bar_w = max(2.5, min(5.0, bar_spacing - 2.5))
        progress_ratio = (self.position / self.duration) if self.duration > 0 else 0.0

        active_color = QColor("#4F46E5")      # Indigo 600 (Played portion)
        inactive_color = QColor("#CBD5E1")    # Slate 300 (Remaining portion)
        disabled_color = QColor("#E2E8F0")    # Slate 200 (Inactive)

        for i, peak in enumerate(self.peaks):
            cx = (i + 0.5) * bar_spacing
            bar_h = max(6.0, h * peak * 0.84)
            y = (h - bar_h) / 2.0

            bar_ratio = (i + 0.5) / n
            if not self.isEnabled():
                color = disabled_color
            elif bar_ratio <= progress_ratio:
                color = active_color
            else:
                color = inactive_color

            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            rect = QRectF(cx - bar_w / 2.0, y, bar_w, bar_h)
            radius = bar_w / 2.0
            painter.drawRoundedRect(rect, radius, radius)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.isEnabled() or self.duration <= 0:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._seek_from_mouse(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_dragging and self.isEnabled() and self.duration > 0:
            self._seek_from_mouse(event.position().x())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False

    def _seek_from_mouse(self, mouse_x: float) -> None:
        ratio = max(0.0, min(1.0, mouse_x / max(1.0, float(self.width()))))
        target_pos = int(ratio * self.duration)
        self.position = target_pos
        self.update()
        self.seekRequested.emit(target_pos)

    def setPosition(self, pos: int) -> None:
        if not self._is_dragging:
            self.position = pos
            self.update()

    def setDuration(self, dur: int) -> None:
        self.duration = dur
        self.update()

    # Compatibility methods
    def setValue(self, val: int) -> None:
        self.setPosition(val)

    def value(self) -> int:
        return self.position

    def setRange(self, min_val: int, max_val: int) -> None:
        self.duration = max_val
        self.update()


class AudioPlayer(QFrame):
    """Reusable audio player with waveform visualizer, playback controls, volume, and file export."""

    def __init__(
        self,
        title: Optional[str] = "Trình phát âm thanh",
        parent: Optional[QWidget] = None,
        is_card: bool = False,
    ):
        super().__init__(parent)
        self.current_audio_path: Optional[Path] = None

        self._layout = QVBoxLayout(self)
        if is_card:
            self.setProperty("class", "card")
            self._layout.setContentsMargins(20, 20, 20, 20)
            self._layout.setSpacing(14)
        else:
            self.setStyleSheet("background: transparent; border: none;")
            self._layout.setContentsMargins(0, 4, 0, 0)
            self._layout.setSpacing(10)

        if title:
            self.title_label = QLabel(title)
            self.title_label.setProperty("class", "section-title")
            self._layout.addWidget(self.title_label)

        # Initialize Qt Multimedia Player
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.85)

        self._setup_ui()
        self._connect_signals()

    def addWidget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def addLayout(self, layout) -> None:
        self._layout.addLayout(layout)

    def _setup_ui(self) -> None:
        # File info banner
        self.info_label = QLabel("Chưa có âm thanh được tải")
        self.info_label.setProperty("class", "caption")
        self.addWidget(self.info_label)

        # Progress / Waveform Row
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(12)

        self.time_label = QLabel("00:00")
        self.time_label.setProperty("class", "caption")
        self.time_label.setFixedWidth(45)

        # Custom Waveform Visualizer Seek Bar
        self.waveform_bar = WaveformSeekBar()
        self.seek_slider = self.waveform_bar  # alias for backwards compatibility

        self.duration_label = QLabel("00:00")
        self.duration_label.setProperty("class", "caption")
        self.duration_label.setFixedWidth(45)

        progress_layout.addWidget(self.time_label)
        progress_layout.addWidget(self.waveform_bar, 1)
        progress_layout.addWidget(self.duration_label)
        self.addLayout(progress_layout)

        # Controls Row
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(12)

        self.play_btn = QPushButton("Phát")
        self.play_btn.setProperty("class", "primary-btn")
        self.play_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setEnabled(False)
        self.play_btn.setFixedWidth(130)


        self.export_btn = QPushButton("Lưu")
        self.export_btn.setProperty("class", "primary-btn")
        self.export_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setEnabled(False)

        controls_layout.addWidget(self.play_btn)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self.export_btn)

        self.addLayout(controls_layout)

    def _connect_signals(self) -> None:
        self.play_btn.clicked.connect(self._toggle_playback)
        self.export_btn.clicked.connect(self._export_audio)

        self.waveform_bar.seekRequested.connect(self._on_seek_requested)

        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)

    def stop_and_release(self) -> None:
        """Stop playback and release the underlying file handle to avoid lock conflicts."""
        try:
            self.player.stop()
            self.player.setSource(QUrl())
        except Exception:
            pass

    def load_audio(self, audio_path: Path, description: str = "") -> None:
        """Load an audio file into the player and initialize waveform visualizer."""
        self.stop_and_release()
        self.current_audio_path = Path(audio_path)
        if not self.current_audio_path.exists():
            return

        self.player.setSource(QUrl.fromLocalFile(str(self.current_audio_path.resolve())))
        desc = description or self.current_audio_path.name
        self.info_label.setText(f"Đã tải: {desc}")
        self.play_btn.setEnabled(True)
        self.waveform_bar.setEnabled(True)
        self.waveform_bar.load_peaks_from_file(self.current_audio_path)
        self.export_btn.setEnabled(True)

    def _toggle_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("Tạm dừng")
        else:
            self.play_btn.setText("Phát")

    def _on_position_changed(self, position: int) -> None:
        self.waveform_bar.setPosition(position)
        self.time_label.setText(self._format_time(position))

    def _on_duration_changed(self, duration: int) -> None:
        self.waveform_bar.setDuration(duration)
        self.duration_label.setText(self._format_time(duration))

    def _on_seek_requested(self, position: int) -> None:
        self.player.setPosition(position)
        self.time_label.setText(self._format_time(position))

    def _export_audio(self) -> None:
        if not self.current_audio_path or not self.current_audio_path.exists():
            return

        default_name = self.current_audio_path.name
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu tệp âm thanh",
            default_name,
            "WAV Audio (*.wav);;Tất cả tệp (*.*)",
        )
        if save_path:
            try:
                shutil.copy2(self.current_audio_path, save_path)
                # QMessageBox.information(self, "Thành công", f"Đã lưu âm thanh tại:\n{save_path}")
            except Exception as e:
                # QMessageBox.critical(self, "Lỗi", f"Không thể lưu tệp: {e}")
                pass

    @staticmethod
    def _format_time(ms: int) -> str:
        seconds = max(0, ms // 1000)
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins:02d}:{secs:02d}"
