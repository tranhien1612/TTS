"""Editable slider badge component for displaying and directly editing slider values.

Provides two-way synchronization between a QSlider and an interactive badge:
- Dragging slider updates badge text in real-time.
- Clicking badge allows typing a value directly (with validation, clamping, and data-type integrity).
"""
import re
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QLineEdit, QSlider, QWidget

SLIDER_BADGE_STYLE = """
    QLineEdit {
        background-color: #EEF2FF;
        color: #4F46E5;
        font-weight: bold;
        font-size: 13px;
        padding: 3px 6px;
        border-radius: 6px;
        border: 1px solid #C7D2FE;
    }
    QLineEdit:hover {
        border-color: #818CF8;
        background-color: #E0E7FF;
    }
    QLineEdit:focus {
        background-color: #FFFFFF;
        border: 1.5px solid #4F46E5;
        color: #0F172A;
    }
    QLineEdit:disabled {
        background-color: #F1F5F9;
        color: #94A3B8;
        border-color: #E2E8F0;
    }
"""


class EditableSliderBadge(QLineEdit):
    """Interactive badge that synchronizes two-way with a QSlider.

    Features:
    - Auto-formats value with optional suffix (e.g. '10s', '30 fps', '1920 px', '1.0x').
    - Allows direct text editing on click with auto-selection.
    - Validates and clamps input strictly within slider bounds.
    - Preserves data types (integer, even integer, float scale).
    """

    def __init__(
        self,
        slider: QSlider,
        suffix: str = "",
        scale: float = 1.0,
        is_even: bool = False,
        decimals: int = 0,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.slider = slider
        self.suffix = suffix
        self.scale = scale
        self.is_even = is_even
        self.decimals = decimals
        self._has_selected_on_click = False

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(SLIDER_BADGE_STYLE)
        self.setCursor(Qt.CursorShape.IBeamCursor)

        self.slider.valueChanged.connect(self._on_slider_value_changed)
        self.editingFinished.connect(self._on_editing_finished)
        self.returnPressed.connect(self.clearFocus)

        self._update_from_slider()

    def _update_from_slider(self) -> None:
        """Format text from slider's current integer value."""
        val = self.slider.value()
        if self.scale == 1.0 and self.decimals == 0:
            self.setText(f"{val}{self.suffix}")
        else:
            real_val = val / self.scale
            if val % 10 == 0:
                self.setText(f"{real_val:.1f}{self.suffix}")
            else:
                self.setText(f"{real_val:.2f}{self.suffix}")

    def _on_slider_value_changed(self, val: int) -> None:
        if not self.hasFocus():
            self._update_from_slider()

    def mousePressEvent(self, event) -> None:
        if not self.hasFocus():
            self._select_all_on_focus = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if getattr(self, "_select_all_on_focus", False):
            self.selectAll()
            self._select_all_on_focus = False

    def focusOutEvent(self, event) -> None:
        self._select_all_on_focus = False
        super().focusOutEvent(event)

    def _on_editing_finished(self) -> None:
        """Parse, validate, and clamp user input back into slider value."""
        raw = self.text().strip()
        match = re.search(r"[-+]?(?:\d*\.\d+|\d+)", raw)
        if not match:
            self._update_from_slider()
            return

        num = float(match.group(0))

        if self.scale != 1.0:
            # Scaled float value (e.g. speed factor: 0.5 to 2.0)
            min_real = self.slider.minimum() / self.scale
            max_real = self.slider.maximum() / self.scale
            val_real = max(min_real, min(max_real, num))
            slider_val = int(round(val_real * self.scale))
        else:
            # Integer value (e.g. seconds, fps, pixels)
            min_val = self.slider.minimum()
            max_val = self.slider.maximum()
            slider_val = int(round(num))
            if self.is_even:
                slider_val = (slider_val // 2) * 2
            slider_val = max(min_val, min(max_val, slider_val))

        self.slider.setValue(slider_val)
        self._update_from_slider()
