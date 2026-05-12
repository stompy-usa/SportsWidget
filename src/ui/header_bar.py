from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class HeaderBar(QWidget):
    """Draggable title strip with favorites toggle and settings/refresh buttons."""

    favorites_toggled = Signal(bool)
    favorites_dialog_requested = Signal()
    refresh_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self.setFixedHeight(28)

        self._drag_offset: QPoint | None = None
        self._locked = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        self.title = QLabel("SPORTS")
        self.title.setObjectName("HeaderTitle")
        layout.addWidget(self.title)

        self.status = QLabel("")
        self.status.setObjectName("HeaderStatus")
        layout.addWidget(self.status)
        layout.addStretch(1)

        self.fav_btn = QPushButton("☆")  # outlined star
        self.fav_btn.setObjectName("HeaderButton")
        self.fav_btn.setCheckable(True)
        self.fav_btn.setToolTip("Favorites only")
        self.fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fav_btn.toggled.connect(self._on_fav_toggled)
        layout.addWidget(self.fav_btn)

        self.settings_btn = QPushButton("⚙")  # gear
        self.settings_btn.setObjectName("HeaderButton")
        self.settings_btn.setToolTip("Manage favorites...")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(self.favorites_dialog_requested.emit)
        layout.addWidget(self.settings_btn)

        self.refresh_btn = QPushButton("↻")  # refresh arrow
        self.refresh_btn.setObjectName("HeaderButton")
        self.refresh_btn.setToolTip("Refresh now")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self.refresh_btn)

        self.close_btn = QPushButton("✕")  # close x
        self.close_btn.setObjectName("HeaderButton")
        self.close_btn.setToolTip("Hide (right-click tray icon to quit)")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(self.close_btn)

    def _on_fav_toggled(self, checked: bool) -> None:
        self.fav_btn.setText("★" if checked else "☆")
        self.favorites_toggled.emit(checked)

    def set_favorites_only(self, on: bool) -> None:
        self.fav_btn.blockSignals(True)
        self.fav_btn.setChecked(on)
        self.fav_btn.setText("★" if on else "☆")
        self.fav_btn.blockSignals(False)

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self._drag_offset = None

    # --- Drag-to-move support ---
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._locked or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        win = self.window()
        self._drag_offset = event.globalPosition().toPoint() - win.frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is None or self._locked:
            return super().mouseMoveEvent(event)
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        new_pos = event.globalPosition().toPoint() - self._drag_offset
        self.window().move(new_pos)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)
