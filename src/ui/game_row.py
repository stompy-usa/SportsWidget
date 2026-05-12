from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from logo_cache import LOGO_HEIGHT_PX, LogoCache
from models import Game
from ui.section_header import apply_text_shadow


class GameRow(QWidget):
    def __init__(self, game: Game, is_favorite: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GameRow")

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

        layout.addWidget(_team_widget(game.away_team_id, game.away_abbr, game.away_logo_url))

        at_label = QLabel("@")
        at_label.setObjectName("Matchup")
        apply_text_shadow(at_label)
        layout.addWidget(at_label)

        layout.addWidget(_team_widget(game.home_team_id, game.home_abbr, game.home_logo_url))

        # Push the score/status to the right.
        layout.addStretch(1)

        if game.state == "in":
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


def _team_widget(team_id: str, abbreviation: str, logo_url: str) -> QLabel:
    """Return a QLabel showing the team's logo if cached, otherwise its abbreviation.

    If the logo isn't cached yet but a URL is known, queues a background download.
    The widget tree re-renders on the LogoCache.logo_ready signal.
    """
    cache = LogoCache.instance()
    pix = cache.get(team_id)
    label = QLabel()
    label.setObjectName("Matchup")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
    if pix is not None:
        label.setPixmap(pix)
        label.setFixedHeight(LOGO_HEIGHT_PX + 2)
    else:
        label.setText(abbreviation)
        if logo_url and team_id:
            cache.request(team_id, logo_url)
    apply_text_shadow(label)
    return label
