"""Settings view – TTS model selection panel."""
from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QButtonGroup,
    QFrame,
    QScrollArea,
)

from core.config import MODEL_VIENEU, MODEL_OMNIVOICE, DEFAULT_TTS_MODEL
from ui.components.card import Card


_MODEL_INFO = [
    {
        "key": MODEL_OMNIVOICE,
        "name": "OmniVoice",
        "desc": "Model TTS đa ngôn ngữ, hỗ trợ clone giọng nói. Chạy trên CPU/GPU (khuyến khích GPU).",
        "badge": "Đa ngôn ngữ · Clone",
    },
    {
        "key": MODEL_VIENEU,
        "name": "VieNeu",
        "desc": "Model TTS tiếng Việt chất lượng cao, hỗ trợ clone giọng nói. Chạy trên CPU/GPU",
        "badge": "Tiếng Việt · Clone",
    },
]


class SettingsView(QWidget):
    """Settings panel for selecting TTS model type."""

    model_changed = pyqtSignal(str)  # emits model key string

    def __init__(self, current_model: str = DEFAULT_TTS_MODEL, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current = current_model
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

        # Header
        title = QLabel("Cài đặt")
        title.setProperty("class", "header-title")
        layout.addWidget(title)

        # Model selection card
        card = Card()

        section_lbl = QLabel("Chọn mô hình TTS")
        section_lbl.setProperty("class", "section-title")
        card.addWidget(section_lbl)

        hint = QLabel("Model sẽ được tải về khi sử dụng lần đầu.")
        hint.setProperty("class", "caption")
        card.addWidget(hint)

        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        for info in _MODEL_INFO:
            radio = self._create_model_radio(info)
            card.addWidget(radio)
            self._btn_group.addButton(radio)
            if info["key"] == self._current:
                radio.setChecked(True)

        self._btn_group.buttonClicked.connect(self._on_selection)

        layout.addWidget(card)
        layout.addStretch(1)
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _create_model_radio(self, info: dict) -> QRadioButton:
        radio = QRadioButton()
        radio.setProperty("model_key", info["key"])
        radio.setCursor(Qt.CursorShape.PointingHandCursor)

        # Rich label via a stacked layout beside the radio indicator
        label_widget = QWidget()
        lbl_layout = QVBoxLayout(label_widget)
        lbl_layout.setContentsMargins(0, 6, 0, 6)
        lbl_layout.setSpacing(2)

        name_row = QHBoxLayout()
        name_lbl = QLabel(info["name"])
        name_lbl.setStyleSheet("font-size: 14px; font-weight: 600; color: #0F172A;")
        name_row.addWidget(name_lbl)

        badge = QLabel(info["badge"])
        badge.setProperty("class", "badge-accent")
        badge.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        name_row.addWidget(badge)
        name_row.addStretch()
        lbl_layout.addLayout(name_row)

        desc_lbl = QLabel(info["desc"])
        desc_lbl.setProperty("class", "caption")
        desc_lbl.setWordWrap(True)
        lbl_layout.addWidget(desc_lbl)

        # Set the entire label widget as the radio's text replacement
        radio.setText(f"  {info['name']}")
        radio.setStyleSheet("QRadioButton { spacing: 10px; }")

        # We can't easily embed a widget inside QRadioButton, so use a composite approach:
        # Create a container that holds the radio + labels side by side
        container = QWidget()
        h_layout = QHBoxLayout(container)
        h_layout.setContentsMargins(12, 8, 12, 8)
        h_layout.setSpacing(12)

        # Replace: just use a styled QRadioButton with description below its text
        radio.setText("")
        h_layout.addWidget(radio)
        h_layout.addWidget(label_widget, 1)

        container.setStyleSheet("""
            QWidget {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
            }
            QWidget:hover {
                border-color: #94A3B8;
            }
        """)

        # We return the container but need to track the radio for the button group
        # Trick: Make the container click-able by routing clicks to radio
        container.mousePressEvent = lambda e: radio.setChecked(True) or self._btn_group.buttonClicked.emit(radio)

        # Actually, QRadioButton must be the returned widget for QButtonGroup.
        # Instead, build a simpler approach: rich text on the radio itself.
        radio_styled = QRadioButton(f"  {info['name']} - {info['desc']}")
        radio_styled.setProperty("model_key", info["key"])
        radio_styled.setCursor(Qt.CursorShape.PointingHandCursor)
        radio_styled.setStyleSheet("""
            QRadioButton {
                spacing: 10px;
                padding: 12px 14px;
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
                font-size: 13px;
                color: #334155;
            }
            QRadioButton:hover {
                border-color: #94A3B8;
                background-color: #FFFFFF;
            }
            QRadioButton:checked {
                background-color: #EEF2FF;
                border: 1.5px solid #4F46E5;
                color: #0F172A;
                font-weight: 600;
            }
        """)

        # Cleanup: we built two widgets but only need the styled one
        container.deleteLater()
        return radio_styled

    def _on_selection(self, button: QRadioButton) -> None:
        key = button.property("model_key")
        if key and key != self._current:
            self._current = key
            self.model_changed.emit(key)

    @property
    def current_model(self) -> str:
        return self._current
