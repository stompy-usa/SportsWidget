from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from models import Game
from ui.section_header import apply_text_shadow


class GameRow(QWidget):
    def __init__(self, game: Game, is_favorite: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GameRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(8)

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

        matchup = QLabel(f"{game.away_abbr}  @  {game.home_abbr}")
        matchup.setObjectName("Matchup")
        apply_text_shadow(matchup)
        layout.addWidget(matchup, stretch=1)

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
