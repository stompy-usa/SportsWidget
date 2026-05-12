from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)


def apply_text_shadow(widget: QWidget) -> None:
    """Soft dark shadow so white text stays readable on light wallpapers."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(4)
    effect.setOffset(1, 1)
    effect.setColor(QColor(0, 0, 0, 180))
    widget.setGraphicsEffect(effect)


class SectionHeader(QWidget):
    toggled = Signal(str, bool)  # (section_key, collapsed)

    def __init__(
        self,
        key: str,
        label: str,
        collapsed: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._key = key
        self._collapsed = collapsed
        self.setObjectName("SectionHeaderRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 2)
        layout.setSpacing(6)

        self._arrow = QLabel("▼" if not collapsed else "▶")  # ▼ / ▶
        self._arrow.setObjectName("SectionArrow")
        apply_text_shadow(self._arrow)
        layout.addWidget(self._arrow)

        self._label = QLabel(label)
        self._label.setObjectName("SectionLabel")
        apply_text_shadow(self._label)
        layout.addWidget(self._label)
        layout.addStretch(1)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._collapsed = not self._collapsed
            self._arrow.setText("▶" if self._collapsed else "▼")
            self.toggled.emit(self._key, self._collapsed)
            event.accept()
            return
        super().mousePressEvent(event)
