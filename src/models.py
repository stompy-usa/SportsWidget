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
    home_team_id: str
    home_abbr: str
    home_score: str
    home_logo_url: str
    away_team_id: str
    away_abbr: str
    away_score: str
    away_logo_url: str
    home_short_name: str = ""   # "Rangers", "White Sox", etc.
    away_short_name: str = ""

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


# --- Per-game live detail (summary endpoint) ---

@dataclass
class MLBDetail:
    inning: str = ""           # "Top 5th"
    balls: int = 0
    strikes: int = 0
    outs: int = 0
    on_first: bool = False
    on_second: bool = False
    on_third: bool = False
    pitcher_name: str = ""
    pitcher_line: str = ""     # e.g. "67 P"
    batter_name: str = ""
    batter_line: str = ""      # e.g. "0-2"
    last_play: str = ""
    # Pre-game
    away_probable_pitcher: str = ""
    home_probable_pitcher: str = ""
    away_lineup: list[tuple[str, str]] = field(default_factory=list)  # (position, name)
    home_lineup: list[tuple[str, str]] = field(default_factory=list)
    away_record: str = ""
    home_record: str = ""


@dataclass
class NBADetail:
    period: str = ""           # "Q3"
    clock: str = ""            # "4:32"
    away_leaders: list[tuple[str, str]] = field(default_factory=list)
    home_leaders: list[tuple[str, str]] = field(default_factory=list)
    last_play: str = ""
    # Pre-game
    away_record: str = ""
    home_record: str = ""


@dataclass
class NFLDetail:
    period: str = ""
    clock: str = ""
    possession_abbr: str = ""
    down_distance: str = ""    # "3rd & 7"
    yard_line: str = ""        # "NYG 35"
    last_play: str = ""
    # Pre-game
    away_record: str = ""
    home_record: str = ""


@dataclass
class NHLDetail:
    period: str = ""
    clock: str = ""
    away_shots: int = 0
    home_shots: int = 0
    power_play: str = ""       # e.g. "TOR PP 2:14" or ""
    away_leaders: list[tuple[str, str]] = field(default_factory=list)
    home_leaders: list[tuple[str, str]] = field(default_factory=list)
    last_play: str = ""
    # Pre-game
    away_goalie: str = ""
    home_goalie: str = ""
    away_record: str = ""
    home_record: str = ""


@dataclass
class GameDetail:
    event_id: str
    league: League
    state: GameState = "pre"       # so the panel knows which renderer to use
    away_abbr: str = ""
    home_abbr: str = ""
    away_score: str = ""
    home_score: str = ""
    away_team_id: str = ""
    home_team_id: str = ""
    mlb: MLBDetail | None = None
    nba: NBADetail | None = None
    nfl: NFLDetail | None = None
    nhl: NHLDetail | None = None
    fetched_at: datetime | None = None
    error: str | None = None
