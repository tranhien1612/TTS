"""Voice capsule/pill selector widget and dynamic flow layout for Neu Audio Studio."""
from typing import Optional, List, Any
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QLabel, QHBoxLayout, QLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QRect, QPoint, QSize


class FlowLayout(QLayout):
    """A standard Qt flow layout that wraps items dynamically across multiple rows."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 10):
        super().__init__(parent)
        self._items: List[Any] = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            if x + w > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x += w + spacing
            line_height = max(line_height, h)

        return y + line_height - effective_rect.y() + margins.top() + margins.bottom()


class FlowWidget(QWidget):
    """Container widget supporting dynamic height-for-width in QScrollArea."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 10):
        super().__init__(parent)
        self.flow_layout = FlowLayout(self, margin=margin, spacing=spacing)
        self.setLayout(self.flow_layout)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self.flow_layout.heightForWidth(width)

    def sizeHint(self) -> QSize:
        w = self.width() if self.width() > 0 else 600
        return QSize(w, self.heightForWidth(w))


class VoicePill(QPushButton):
    """Capsule/Pill button displaying voice name and tags in high contrast."""

    def __init__(
        self,
        voice_id: str,
        title: str,
        subtitle: str,
        full_desc: str = "",
        is_clone: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.voice_id = voice_id
        self.title_text = title
        self.subtitle_text = subtitle
        self.full_desc = full_desc
        self.is_clone = is_clone

        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(38)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label = QLabel(self)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.label)

        self._update_appearance(False)
        self.toggled.connect(self._update_appearance)

    def sizeHint(self) -> QSize:
        lbl_size = self.label.sizeHint()
        return QSize(lbl_size.width() + 32, 38)

    def set_content(self, title: str, subtitle: str) -> None:
        self.title_text = title
        self.subtitle_text = subtitle
        self._update_appearance(self.isChecked())
        self.updateGeometry()

    def _update_appearance(self, checked: bool) -> None:
        if checked:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #EEF2FF;
                    border: 1.5px solid #4F46E5;
                    border-radius: 19px;
                    padding: 0px;
                }
            """)
            sub_html = f"<span style='color:#6366F1; font-size:12px;'> &nbsp;·&nbsp; {self.subtitle_text}</span>" if self.subtitle_text else ""
            self.label.setText(
                f"<b style='color:#4F46E5; font-size:13px;'>{self.title_text}</b>{sub_html}"
            )
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #FFFFFF;
                    border: 1.5px solid #CBD5E1;
                    border-radius: 19px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #F8FAFC;
                    border: 1.5px solid #94A3B8;
                }
            """)
            sub_html = f"<span style='color:#64748B; font-size:12px;'> &nbsp;·&nbsp; {self.subtitle_text}</span>" if self.subtitle_text else ""
            self.label.setText(
                f"<b style='color:#0F172A; font-size:13px;'>{self.title_text}</b>{sub_html}"
            )
