from __future__ import annotations

from models import League

_LEAGUE_URL_SLUG: dict[League, str] = {
    "mlb": "mlb",
    "nba": "nba",
    "nfl": "nfl",
    "nhl": "nhl",
}


def espn_game_url(league: str, event_id: str) -> str:
    slug = _LEAGUE_URL_SLUG.get(league)  # type: ignore[arg-type]
    if not slug or not event_id:
        return ""
    return f"https://www.espn.com/{slug}/game/_/gameId/{event_id}"
