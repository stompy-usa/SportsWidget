from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget


def _make_icon() -> QIcon:
    """Build a simple programmatic icon so we don't ship an image file."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(QColor(30, 33, 41)))
    painter.setPen(QPen(QColor(245, 197, 66), 3))
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
    painter.setPen(QColor(245, 197, 66))
    font = QFont()
    font.setBold(True)
    font.setPointSize(22)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "S")
    painter.end()
    return QIcon(pix)


class SportsTray(QObject):
    show_requested = Signal()
    hide_requested = Signal()
    toggle_lock_requested = Signal()
    refresh_requested = Signal()
    favorites_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent_widget: QWidget) -> None:
        super().__init__(parent_widget)
        self._tray = QSystemTrayIcon(_make_icon(), parent_widget)
        self._tray.setToolTip("Sports Widget")

        menu = QMenu(parent_widget)

        self._act_show = QAction("Show / Hide", parent_widget)
        self._act_show.triggered.connect(self._toggle_visibility)
        menu.addAction(self._act_show)

        self._act_lock = QAction("Lock", parent_widget, checkable=True)
        self._act_lock.toggled.connect(lambda _on: self.toggle_lock_requested.emit())
        menu.addAction(self._act_lock)

        act_refresh = QAction("Refresh now", parent_widget)
        act_refresh.triggered.connect(self.refresh_requested.emit)
        menu.addAction(act_refresh)

        act_fav = QAction("Favorites...", parent_widget)
        act_fav.triggered.connect(self.favorites_requested.emit)
        menu.addAction(act_fav)

        menu.addSeparator()
        act_quit = QAction("Quit", parent_widget)
        act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

        self._window = parent_widget

    def show(self) -> None:
        self._tray.show()

    def set_locked(self, locked: bool) -> None:
        self._act_lock.blockSignals(True)
        self._act_lock.setChecked(locked)
        self._act_lock.blockSignals(False)

    def _toggle_visibility(self) -> None:
        if self._window.isVisible():
            self.hide_requested.emit()
        else:
            self.show_requested.emit()

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_visibility()
