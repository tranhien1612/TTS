"""Reusable modern VideoPlayer component with custom floating controls and click-to-toggle playback.

Designed for reuse across views in Neu Audio Studio (Sketch Video, TTS, STT, etc.).
"""
from pathlib import Path
from typing import Optional, Union
import threading

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QEvent
from PyQt6.QtGui import QCursor, QWheelEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QStackedLayout,
    QPushButton,
    QSlider,
    QLabel,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from ui.styles import BG_MAIN, BORDER_COLOR


class VideoSeekSlider(QSlider):
    """Horizontal seek slider that supports direct click-to-seek and ignores mouse wheel scrolling."""

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            w = self.width()
            if w > 0 and self.maximum() > self.minimum():
                x = event.position().x()
                ratio = max(0.0, min(1.0, x / w))
                val = int(self.minimum() + ratio * (self.maximum() - self.minimum()))
                self.setValue(val)
                self.sliderMoved.emit(val)
        super().mousePressEvent(event)


class VideoControlsOverlay(QFrame):
    """Floating translucent bottom control bar for video playback."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("videoControlsOverlay")
        self.setFixedHeight(38)

        self.setStyleSheet("""
            #videoControlsOverlay {
                background-color: rgba(15, 23, 42, 0.55);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 8px;
            }
            #videoControlsOverlay QLabel {
                color: #FFFFFF;
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 11px;
                font-weight: 600;
                border: none;
                background: transparent;
            }
            #videoControlsOverlay QPushButton {
                background: transparent;
                color: #FFFFFF;
                border: none;
                font-size: 14px;
                padding: 0px 4px;
            }
            #videoControlsOverlay QPushButton:hover {
                color: #818CF8;
            }
            #videoControlsOverlay QSlider {
                background: transparent;
            }
            #videoControlsOverlay QSlider::groove:horizontal {
                height: 4px;
                background: rgba(255, 255, 255, 0.25);
                border-radius: 2px;
            }
            #videoControlsOverlay QSlider::sub-page:horizontal {
                background: #818CF8;
                border-radius: 2px;
            }
            #videoControlsOverlay QSlider::handle:horizontal {
                background: #FFFFFF;
                width: 10px;
                height: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(10)

        # 1. Play / Pause / Replay button
        self.btn_play_pause = QPushButton("▶")
        self.btn_play_pause.setFixedSize(26, 26)
        self.btn_play_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.btn_play_pause)

        # 2. Time label (e.g. 0:00 / 0:30)
        self.time_label = QLabel("0:00 / 0:00")
        layout.addWidget(self.time_label)

        # 3. Timeline Seek Slider
        self.timeline_slider = VideoSeekSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setRange(0, 0)
        self.timeline_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.timeline_slider, 1)

        # 4. Volume / Mute button
        self.btn_volume = QPushButton("🔊")
        self.btn_volume.setFixedSize(26, 26)
        self.btn_volume.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.btn_volume)


class VideoPlayer(QFrame):
    """Self-contained, reusable video player component with hover controls,

    click-to-toggle playback, and media state management.
    """

    clicked = pyqtSignal()
    video_loaded = pyqtSignal(Path)
    aspect_ratio_changed = pyqtSignal(float)
    playback_state_changed = pyqtSignal(QMediaPlayer.PlaybackState)
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)

    def __init__(self, placeholder_text: str = "Chưa có video", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("videoPlayer")
        self.setMouseTracking(True)
        self.current_video_path: Optional[Path] = None
        self._has_video: bool = False
        self.video_aspect_ratio: float = 16.0 / 9.0
        self.video_resolution: Optional[tuple[int, int]] = None

        # Internal Media Player
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0)

        # Layout hierarchy: Stack
        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)

        # Page 0: Placeholder
        self.placeholder_widget = QWidget()
        placeholder_layout = QVBoxLayout(self.placeholder_widget)
        placeholder_layout.setContentsMargins(20, 20, 20, 20)
        placeholder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.placeholder_text = QLabel(placeholder_text)
        self.placeholder_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_text.setStyleSheet(
            "color: #64748B; font-size: 13px; font-weight: 500; border: none; background: transparent;"
        )
        placeholder_layout.addWidget(self.placeholder_text)
        self.stack.addWidget(self.placeholder_widget)

        # Page 1: Video Widget
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("border-radius: 10px; background-color: #000000;")
        self.video_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.video_widget.installEventFilter(self)
        self.player.setVideoOutput(self.video_widget)
        self.stack.addWidget(self.video_widget)

        # Floating overlay control bar
        self.overlay = VideoControlsOverlay(self)
        self.overlay.setVisible(False)

        # Aliases for convenience
        self.btn_play_pause = self.overlay.btn_play_pause
        self.time_label = self.overlay.time_label
        self.timeline_slider = self.overlay.timeline_slider
        self.btn_volume = self.overlay.btn_volume

        # Wire internal signals
        self._connect_signals()
        self._update_style()

    def _connect_signals(self) -> None:
        self.btn_play_pause.clicked.connect(self.toggle_playback)
        self.timeline_slider.sliderPressed.connect(self._on_seek_pressed)
        self.timeline_slider.sliderMoved.connect(self._on_seek)
        self.timeline_slider.sliderReleased.connect(self._on_seek_released)
        self.btn_volume.clicked.connect(self.toggle_mute)

        self.player.positionChanged.connect(self._on_player_position_changed)
        self.player.durationChanged.connect(self._on_player_duration_changed)
        self.player.playbackStateChanged.connect(self._on_player_state_changed)

        if hasattr(self.video_widget, "videoSink") and self.video_widget.videoSink() is not None:
            self.video_widget.videoSink().videoSizeChanged.connect(self._on_video_sink_size_changed)

    def _on_video_sink_size_changed(self, *args) -> None:
        """Handle video size change notifications directly from Qt multimedia decoder."""
        size = args[0] if args else None
        if size is None and hasattr(self.video_widget, "videoSink") and self.video_widget.videoSink() is not None:
            size = self.video_widget.videoSink().videoSize()
        if size is not None and hasattr(size, "isValid") and size.isValid() and size.width() > 0 and size.height() > 0:
            ratio = size.width() / size.height()
            self.video_resolution = (size.width(), size.height())
            if abs(ratio - self.video_aspect_ratio) > 0.01:
                self.video_aspect_ratio = ratio
                self.aspect_ratio_changed.emit(ratio)

    def _update_style(self) -> None:
        if self._has_video:
            self.setStyleSheet(f"""
                #videoPlayer {{
                    background-color: #000000;
                    border: 1px solid {BORDER_COLOR};
                    border-radius: 10px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                #videoPlayer {{
                    background-color: {BG_MAIN};
                    border: 2px dashed #CBD5E1;
                    border-radius: 12px;
                }}
                #videoPlayer QLabel {{
                    border: none;
                    background: transparent;
                }}
            """)

    # ─── Public API ──────────────────────────────────────────────────────

    @property
    def has_video(self) -> bool:
        return self._has_video

    def set_has_video(self, has_video: bool) -> None:
        self._has_video = has_video
        if has_video:
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(0)
            self.overlay.setVisible(False)
        self._update_style()

    def update_aspect_size(
        self,
        available_width: Optional[int] = None,
        max_height: int = 520,
        min_height: int = 240,
    ) -> tuple[int, int]:
        """Dynamically resize widget to fit available width while strictly matching video aspect ratio."""
        if available_width is None:
            parent = self.parentWidget()
            available_width = parent.width() if parent else self.width()

        avail_w = max(200, available_width)

        if not self._has_video:
            target_w = avail_w
            target_h = min_height
            self.setFixedSize(target_w, target_h)
            return target_w, target_h

        ratio = self.video_aspect_ratio if self.video_aspect_ratio > 0 else (16.0 / 9.0)

        # Height if we fill available_width
        target_h = int(avail_w / ratio)

        if target_h > max_height:
            target_h = max_height
            target_w = int(max_height * ratio)
        elif target_h < min_height:
            target_h = min_height
            target_w = min(avail_w, int(min_height * ratio))
        else:
            target_w = avail_w
            target_h = int(target_w / ratio)

        target_w = max(100, min(target_w, avail_w))
        target_h = max(min_height, target_h)

        self.setFixedSize(target_w, target_h)
        return target_w, target_h

    def load_video(self, video_path: Union[Path, str]) -> None:
        """Load and display the given video file."""
        path = Path(video_path)
        if not path.exists():
            return
        self.current_video_path = path

        # Probe resolution asynchronously in background thread so UI never freezes
        def _bg_probe():
            try:
                from core.dubbing_service import get_video_resolution
                res = get_video_resolution(path)
                if res and res[1] > 0:
                    self.video_resolution = res
                    self.video_aspect_ratio = res[0] / res[1]
                    self.aspect_ratio_changed.emit(self.video_aspect_ratio)
            except Exception:
                pass
        threading.Thread(target=_bg_probe, daemon=True).start()

        self.set_has_video(True)

        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.timeline_slider.setEnabled(True)
        self.btn_play_pause.setEnabled(True)
        self.btn_play_pause.setText("▶")
        self.video_loaded.emit(path)

    def play(self) -> None:
        if self._has_video:
            self.player.play()

    def pause(self) -> None:
        if self._has_video:
            self.player.pause()

    def stop(self) -> None:
        self.player.stop()

    def toggle_playback(self) -> None:
        """Toggle playback between playing and paused, or replay if finished."""
        if not self._has_video or not self.current_video_path:
            return
        dur = self.player.duration()
        pos = self.player.position()
        if dur > 0 and pos >= dur - 100:
            self.player.setPosition(0)
            self.player.play()
            return

        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def toggle_mute(self) -> None:
        if self.audio_output.isMuted():
            self.audio_output.setMuted(False)
            self.btn_volume.setText("🔊")
        else:
            self.audio_output.setMuted(True)
            self.btn_volume.setText("🔇")

    def clear(self) -> None:
        """Stop playback and clear current video state."""
        self.player.stop()
        self.player.setSource(QUrl())
        self.current_video_path = None
        self.video_aspect_ratio = 16.0 / 9.0
        self.video_resolution = None
        self.timeline_slider.setValue(0)
        self.timeline_slider.setRange(0, 0)
        self.time_label.setText("0:00 / 0:00")
        self.btn_play_pause.setText("▶")
        self.set_has_video(False)

    def cleanup(self) -> None:
        """Safely terminate player on exit."""
        self.player.stop()

    # ─── Internal Event Handlers ─────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        margin = 12
        h = 38
        self.overlay.setGeometry(
            margin,
            self.height() - h - margin,
            max(50, self.width() - (margin * 2)),
            h,
        )

    def enterEvent(self, event) -> None:
        if self._has_video:
            self.overlay.setVisible(True)
            self.overlay.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.overlay.setVisible(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._has_video and event.button() == Qt.MouseButton.LeftButton:
            if not self.overlay.geometry().contains(event.pos()):
                self.toggle_playback()
                self.clicked.emit()
        super().mousePressEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.video_widget:
            if event.type() == QEvent.Type.Enter:
                if self._has_video:
                    self.overlay.setVisible(True)
                    self.overlay.raise_()
            elif event.type() == QEvent.Type.Leave:
                pos = self.mapFromGlobal(QCursor.pos())
                if not self.rect().contains(pos):
                    self.overlay.setVisible(False)
            elif event.type() == QEvent.Type.MouseButtonPress:
                if self._has_video and event.button() == Qt.MouseButton.LeftButton:
                    self.toggle_playback()
                    self.clicked.emit()
                    return True
        return super().eventFilter(watched, event)

    def _on_seek_pressed(self) -> None:
        """Immediately pause playback when interacting with timeline."""
        if self._has_video and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()

    def _on_seek(self, position: int) -> None:
        """Pause playback and display the exact frame at the selected timeline position."""
        if not self._has_video:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        self.player.setPosition(position)
        self._update_time_label(position, self.player.duration())

    def _on_seek_released(self) -> None:
        """Commit final position upon releasing the slider and keep frame displayed."""
        if not self._has_video:
            return
        pos = self.timeline_slider.value()
        self.player.setPosition(pos)
        self._update_time_label(pos, self.player.duration())

    def _on_player_position_changed(self, position: int) -> None:
        if not self.timeline_slider.isSliderDown():
            self.timeline_slider.setValue(position)
        self._update_time_label(position, self.player.duration())
        dur = self.player.duration()
        if dur > 0 and position >= dur - 300 and self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play_pause.setText("↺")
        self.position_changed.emit(position)

    def _on_player_duration_changed(self, duration: int) -> None:
        self.timeline_slider.setRange(0, duration)
        self._update_time_label(self.player.position(), duration)
        self.duration_changed.emit(duration)

    def _on_player_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play_pause.setText("⏸")
        else:
            dur = self.player.duration()
            pos = self.player.position()
            if dur > 0 and pos >= dur - 300:
                self.btn_play_pause.setText("↺")
            else:
                self.btn_play_pause.setText("▶")
        self.playback_state_changed.emit(state)

    def _update_time_label(self, pos_ms: int, dur_ms: int) -> None:
        pos_sec = max(0, pos_ms // 1000)
        dur_sec = max(0, dur_ms // 1000)
        pos_str = f"{pos_sec // 60}:{pos_sec % 60:02d}"
        dur_str = f"{dur_sec // 60}:{dur_sec % 60:02d}"
        self.time_label.setText(f"{pos_str} / {dur_str}")


# Alias for backward compatibility
VideoContainer = VideoPlayer
