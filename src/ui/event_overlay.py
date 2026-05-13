from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

from ui.section_header import apply_text_shadow


class EventOverlay(QLabel):
    """Floating banner over the detail panel that fades in, holds, fades out.

    Positioned with setGeometry rather than via a layout so it can sit on top
    of the detail body without pushing other content around. Mouse-transparent
    so it never blocks the buttons underneath.
    """

    FADE_IN_MS = 220
    HOLD_MS = 1500
    FADE_OUT_MS = 360

    def __init__(self, parent: QWidget) -> None:
        super().__init__("", parent)
        self.setObjectName("EventBanner")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        apply_text_shadow(self)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._fade_in = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_in.setDuration(self.FADE_IN_MS)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade_out = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_out.setDuration(self.FADE_OUT_MS)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)

        self._sequence: QSequentialAnimationGroup | None = None
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._fade_out.start)
        self._fade_in.finished.connect(lambda: self._hold_timer.start(self.HOLD_MS))
        self._fade_out.finished.connect(self.hide)

        self.hide()

    def show_event(self, event_key: str, text: str) -> None:
        """Run the banner animation. If one is already in flight, cancel it."""
        # Stop anything in progress and reset opacity baseline.
        self._fade_in.stop()
        self._fade_out.stop()
        self._hold_timer.stop()
        self._opacity.setOpacity(0.0)

        self.setText(text)
        self.setProperty("event", event_key)
        # Re-polish so the QSS property selector picks up the new event class.
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._fade_in.start()

    def stop(self) -> None:
        """Halt any running animation (called when the detail panel hides)."""
        self._fade_in.stop()
        self._fade_out.stop()
        self._hold_timer.stop()
        self._opacity.setOpacity(0.0)
        self.hide()

    def reposition(self) -> None:
        """Public hook for the parent's resizeEvent."""
        self._reposition()

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        w = self.width()
        h = self.height()
        x = max(0, (parent.width() - w) // 2)
        y = 4
        self.setGeometry(x, y, w, h)
