from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget
from typing import Optional


class Card(QFrame):
    """Reusable container card adhering to the 12px radius and 20px padding specification."""

    def __init__(self, title: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("class", "card")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(14)

        if title:
            self.title_label = QLabel(title)
            self.title_label.setProperty("class", "section-title")
            self._layout.addWidget(self.title_label)

    @property
    def layout(self) -> QVBoxLayout:
        return self._layout

    def addWidget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def addLayout(self, layout) -> None:
        self._layout.addLayout(layout)
