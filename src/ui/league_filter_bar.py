from __future__ import annotations

from typing import get_args

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from models import League
from ui.section_header import apply_text_shadow

LEAGUES: tuple[League, ...] = get_args(League)


class _LeagueBadge(QLabel):
    toggled = Signal(str, bool)  # (league, enabled)

    def __init__(self, league: str, enabled: bool, parent: QWidget | None = None) -> None:
        super().__init__(league.upper(), parent)
        self._league = league
        self._enabled = enabled
        self.setObjectName("LeagueFilterBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Toggle {league.upper()}")
        self._refresh_style()
        apply_text_shadow(self)

    def set_enabled_state(self, enabled: bool) -> None:
        if self._enabled == enabled:
            return
        self._enabled = enabled
        self._refresh_style()

    def _refresh_style(self) -> None:
        self.setProperty("active", "true" if self._enabled else "false")
        # Force a re-polish so the active-state QSS rule actually applies.
        style = self.style()
        style.unpolish(self)
        style.polish(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._enabled = not self._enabled
            self._refresh_style()
            self.toggled.emit(self._league, self._enabled)
            event.accept()
            return
        # Right-click etc. bubble up so the window context menu still appears.
        event.ignore()


class LeagueFilterBar(QWidget):
    """Row of clickable league badges at the top of the widget."""

    league_toggled = Signal(str, bool)  # (league, enabled)

    def __init__(self, enabled_leagues: set[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LeagueFilterBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 2)
        layout.setSpacing(10)

        self._badges: dict[str, _LeagueBadge] = {}
        for lg in LEAGUES:
            badge = _LeagueBadge(lg, enabled=lg in enabled_leagues, parent=self)
            badge.toggled.connect(self.league_toggled.emit)
            layout.addWidget(badge)
            self._badges[lg] = badge

        layout.addStretch(1)

    def set_enabled_leagues(self, enabled: set[str]) -> None:
        for lg, badge in self._badges.items():
            badge.set_enabled_state(lg in enabled)
