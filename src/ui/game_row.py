from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt, QUrl, Signal
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
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

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
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(6)

        badge = QLabel(game.league.upper())
        badge.setObjectName("LeagueBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_text_shadow(badge)
        layout.addWidget(badge)

        if is_favorite:
            star = QLabel("★")
            star.setObjectName("FavoriteStar")
            apply_text_shadow(star)
            layout.addWidget(star)

        layout.addWidget(_team_widget(game.league, game.away_team_id, game.away_abbr, game.away_logo_url))

        at_label = QLabel("@")
        at_label.setObjectName("Matchup")
        apply_text_shadow(at_label)
        layout.addWidget(at_label)

        layout.addWidget(_team_widget(game.league, game.home_team_id, game.home_abbr, game.home_logo_url))

        layout.addStretch(1)

        if game.state == "in":
            self._detail_btn = QPushButton("More detail", self)
            self._detail_btn.setObjectName("MoreDetailButton")
            self._detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._detail_btn.setFlat(True)
            self._detail_btn.setVisible(False)
            self._detail_btn.clicked.connect(self._emit_detail_requested)
            layout.addWidget(self._detail_btn)

            score = QLabel(f"{game.away_score} - {game.home_score}")
            score.setObjectName("ScoreText")
            apply_text_shadow(score)
            layout.addWidget(score)
            status = QLabel(game.status_detail or "LIVE")
            status.setObjectName("StatusLive")
            apply_text_shadow(status)
            layout.addWidget(status)
        elif game.state == "post":
            score = QLabel(f"{game.away_score} - {game.home_score}")
            score.setObjectName("ScoreText")
            apply_text_shadow(score)
            layout.addWidget(score)
            status = QLabel(game.status_detail or "Final")
            status.setObjectName("StatusFinal")
            apply_text_shadow(status)
            layout.addWidget(status)
        else:
            status = QLabel(game.status_detail or "Scheduled")
            status.setObjectName("StatusText")
            apply_text_shadow(status)
            layout.addWidget(status)

    # ---- Mouse: click opens URL; drag moves the window ----
    # We disambiguate click vs drag with a small movement threshold so the user
    # can grab a row to move the widget without accidentally opening a page.

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            # Right-click / middle-click bubble up so the widget's context menu works.
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

    # ---- Hover: reveal/hide the "More detail" button for live games ----

    def enterEvent(self, event: QEvent) -> None:
        if self._detail_btn is not None:
            self._detail_btn.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        if self._detail_btn is not None:
            self._detail_btn.setVisible(False)
        super().leaveEvent(event)

    def _emit_detail_requested(self) -> None:
        if self._event_id:
            self.detail_requested.emit(self._league, self._event_id)


def _team_widget(league: str, team_id: str, abbreviation: str, logo_url: str) -> QLabel:
    cache = LogoCache.instance()
    pix = cache.get(league, team_id)
    label = QLabel()
    label.setObjectName("Matchup")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
    if pix is not None:
        label.setPixmap(pix)
        label.setFixedHeight(LOGO_HEIGHT_PX + 2)
    else:
        label.setText(abbreviation)
        if logo_url and team_id:
            cache.request(league, team_id, logo_url)
    apply_text_shadow(label)
    return label
