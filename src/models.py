from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

League = Literal["mlb", "nba", "nfl", "nhl"]
GameState = Literal["pre", "in", "post"]


@dataclass(frozen=True)
class Team:
    league: League
    team_id: str
    abbreviation: str
    display_name: str

    @property
    def key(self) -> str:
        return f"{self.league}:{self.abbreviation}"


@dataclass
class Game:
    league: League
    event_id: str
    start_utc: datetime
    state: GameState
    status_detail: str  # e.g. "7:10 PM ET", "Top 5th", "Final"
    home_abbr: str
    home_score: str
    away_abbr: str
    away_score: str

    @property
    def home_key(self) -> str:
        return f"{self.league}:{self.home_abbr}"

    @property
    def away_key(self) -> str:
        return f"{self.league}:{self.away_abbr}"

    def involves_any(self, favorite_keys: set[str]) -> bool:
        return self.home_key in favorite_keys or self.away_key in favorite_keys


@dataclass
class LeagueSnapshot:
    league: League
    games: list[Game] = field(default_factory=list)
    error: str | None = None  # set if last fetch failed
    fetched_at: datetime | None = None
