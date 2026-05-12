from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from logo_cache import LOGO_HEIGHT_PX, LogoCache
from models import Game
from ui.section_header import apply_text_shadow
from urls import espn_game_url

_DRAG_THRESHOLD_PX = 4  # Manhattan distance before a press becomes a drag


class GameRow(QWidget):
    detail_requested = Signal(str, str)  # (league, event_id)

    def __init__(self, game: Game, is_favorite: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GameRow")

        self._league = game.league
        self._event_id = game.event_id
        self._url = espn_game_url(game.league, game.event_id)
        self._press_pos: QPoint | None = None
        self._drag_offset: QPoint | None = None
        self._dragging = False
        self._detail_btn: QPushButton | None = None

        if self._url:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip("Open on ESPN")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        if is_favorite:
            star = QLabel("★")
            star.setObjectName("FavoriteStar")
            apply_text_shadow(star)
            layout.addWidget(star)

        # --- Away group: logo, name, score ---
        layout.addWidget(_team_logo(game.league, game.away_team_id, game.away_logo_url))

        away_name = QLabel(game.away_short_name or game.away_abbr)
        away_name.setObjectName("TeamName")
        apply_text_shadow(away_name)
        layout.addWidget(away_name)

        if game.state in ("in", "post"):
            away_score = QLabel(game.away_score or "0")
            away_score.setObjectName("TeamScore")
            apply_text_shadow(away_score)
            layout.addWidget(away_score)

        layout.addStretch(1)

        # --- Status (middle) ---
        status_text = game.status_detail or _default_status(game.state)
        if status_text:
            status = QLabel(status_text)
            status.setObjectName(_status_object_name(game.state))
            apply_text_shadow(status)
            layout.addWidget(status)

        layout.addStretch(1)

        # --- Home group: score, name, logo (mirrored) ---
        if game.state in ("in", "post"):
            home_score = QLabel(game.home_score or "0")
            home_score.setObjectName("TeamScore")
            apply_text_shadow(home_score)
            layout.addWidget(home_score)

        home_name = QLabel(game.home_short_name or game.home_abbr)
        home_name.setObjectName("TeamName")
        apply_text_shadow(home_name)
        layout.addWidget(home_name)

        layout.addWidget(_team_logo(game.league, game.home_team_id, game.home_logo_url))

        # --- Game detail link (pre/live only) ---
        if game.state in ("in", "pre"):
            self._detail_btn = QPushButton("Game detail", self)
            self._detail_btn.setObjectName("MoreDetailButton")
            self._detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._detail_btn.setFlat(True)
            self._detail_btn.setToolTip("Show game detail")
            self._detail_btn.clicked.connect(self._emit_detail_requested)
            layout.addWidget(self._detail_btn)

    # ---- Mouse: click opens URL; drag moves the window ----

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._press_pos = event.globalPosition().toPoint()
        self._dragging = False
        win = self.window()
        if not getattr(win, "_locked", False):
            self._drag_offset = self._press_pos - win.frameGeometry().topLeft()
        else:
            self._drag_offset = None
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_pos is None:
            return super().mouseMoveEvent(event)
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        current = event.globalPosition().toPoint()
        if not self._dragging:
            if (current - self._press_pos).manhattanLength() > _DRAG_THRESHOLD_PX:
                self._dragging = True
        if self._dragging and self._drag_offset is not None:
            self.window().move(current - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
        was_click = self._press_pos is not None and not self._dragging
        self._press_pos = None
        self._drag_offset = None
        self._dragging = False
        if was_click and self._url:
            QDesktopServices.openUrl(QUrl(self._url))
        event.accept()

    def _emit_detail_requested(self) -> None:
        if self._event_id:
            self.detail_requested.emit(self._league, self._event_id)


def _team_logo(league: str, team_id: str, logo_url: str) -> QLabel:
    """Logo-only widget; the team name lives in a sibling QLabel."""
    cache = LogoCache.instance()
    pix = cache.get(league, team_id)
    label = QLabel()
    label.setObjectName("TeamLogo")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
    if pix is not None:
        label.setPixmap(pix)
        label.setFixedHeight(LOGO_HEIGHT_PX + 2)
    elif logo_url and team_id:
        cache.request(league, team_id, logo_url)
    apply_text_shadow(label)
    return label


def _status_object_name(state: str) -> str:
    if state == "in":
        return "StatusLive"
    if state == "post":
        return "StatusFinal"
    return "StatusText"


def _default_status(state: str) -> str:
    if state == "post":
        return "Final"
    return ""
