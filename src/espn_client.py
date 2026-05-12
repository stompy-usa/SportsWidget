from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Iterable

import requests

from models import Game, League, LeagueSnapshot

log = logging.getLogger(__name__)

LEAGUE_PATHS: dict[League, str] = {
    "mlb": "baseball/mlb",
    "nba": "basketball/nba",
    "nfl": "football/nfl",
    "nhl": "hockey/nhl",
}

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/{path}/teams"

REQUEST_TIMEOUT = 8  # seconds


def _format_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def fetch_scoreboard(league: League, days: Iterable[date]) -> LeagueSnapshot:
    """Fetch and parse games for one league across the given dates.

    Aggregates events from each requested day into a single snapshot.
    Raises nothing — errors are captured on the returned snapshot.
    """
    snapshot = LeagueSnapshot(league=league, games=[])
    path = LEAGUE_PATHS[league]
    url = SCOREBOARD_URL.format(path=path)

    try:
        seen: set[str] = set()
        for d in days:
            params = {"dates": _format_date(d)}
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
            for ev in payload.get("events", []):
                game = _parse_event(league, ev)
                if game and game.event_id not in seen:
                    seen.add(game.event_id)
                    snapshot.games.append(game)
        snapshot.games.sort(key=lambda g: g.start_utc)
        snapshot.fetched_at = datetime.now(timezone.utc)
    except Exception as exc:  # noqa: BLE001 — surface as snapshot error
        log.warning("ESPN fetch failed for %s: %s", league, exc)
        snapshot.error = str(exc)
    return snapshot


def _parse_event(league: League, ev: dict) -> Game | None:
    try:
        comp = ev["competitions"][0]
        competitors = comp["competitors"]
        home = next(c for c in competitors if c.get("homeAway") == "home")
        away = next(c for c in competitors if c.get("homeAway") == "away")
        status = ev.get("status", {}).get("type", {})
        state = status.get("state", "pre")
        if state not in ("pre", "in", "post"):
            state = "pre"
        start_iso = ev.get("date", "")
        start_utc = _parse_iso(start_iso)
        return Game(
            league=league,
            event_id=str(ev.get("id", "")),
            start_utc=start_utc,
            state=state,
            status_detail=status.get("shortDetail", "") or status.get("detail", ""),
            home_team_id=_team_id(home),
            home_abbr=_abbr(home),
            home_score=str(home.get("score", "") or ""),
            home_logo_url=_logo_url(home),
            away_team_id=_team_id(away),
            away_abbr=_abbr(away),
            away_score=str(away.get("score", "") or ""),
            away_logo_url=_logo_url(away),
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("Skipping malformed event for %s: %s", league, exc)
        return None


def _abbr(competitor: dict) -> str:
    team = competitor.get("team", {}) or {}
    return (
        team.get("abbreviation")
        or team.get("shortDisplayName")
        or team.get("displayName")
        or "?"
    )


def _team_id(competitor: dict) -> str:
    team = competitor.get("team", {}) or {}
    return str(team.get("id", "") or "")


def _logo_url(competitor: dict) -> str:
    team = competitor.get("team", {}) or {}
    # ESPN's scoreboard includes a "logo" key on the team object.
    return team.get("logo", "") or ""


def _parse_iso(s: str) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    # ESPN returns timestamps like "2026-05-11T23:10Z"
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.now(timezone.utc)


def fetch_teams(league: League) -> list[dict]:
    """Return a list of {'id', 'abbreviation', 'displayName'} for the league."""
    path = LEAGUE_PATHS[league]
    url = TEAMS_URL.format(path=path)
    resp = requests.get(url, params={"limit": 500}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    out: list[dict] = []
    for sport in payload.get("sports", []):
        for lg in sport.get("leagues", []):
            for entry in lg.get("teams", []):
                t = entry.get("team", {})
                out.append(
                    {
                        "id": str(t.get("id", "")),
                        "abbreviation": t.get("abbreviation", ""),
                        "displayName": t.get("displayName", ""),
                    }
                )
    out.sort(key=lambda t: t["displayName"])
    return out
