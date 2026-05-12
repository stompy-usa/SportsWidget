from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from models import Game


class GameRow(QWidget):
    def __init__(self, game: Game, is_favorite: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GameRow")
        self.setProperty("favorite", "true" if is_favorite else "false")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        badge = QLabel(game.league.upper())
        badge.setObjectName("LeagueBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(badge)

        matchup = QLabel(f"{game.away_abbr}  @  {game.home_abbr}")
        matchup.setObjectName("Matchup")
        layout.addWidget(matchup, stretch=1)

        if game.state == "in":
            score = QLabel(f"{game.away_score} - {game.home_score}")
            score.setObjectName("ScoreText")
            layout.addWidget(score)
            status = QLabel(game.status_detail or "LIVE")
            status.setObjectName("StatusLive")
            layout.addWidget(status)
        elif game.state == "post":
            score = QLabel(f"{game.away_score} - {game.home_score}")
            score.setObjectName("ScoreText")
            layout.addWidget(score)
            status = QLabel(game.status_detail or "Final")
            status.setObjectName("StatusFinal")
            layout.addWidget(status)
        else:
            status = QLabel(game.status_detail or "Scheduled")
            status.setObjectName("StatusText")
            layout.addWidget(status)
