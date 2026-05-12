from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Iterable

import requests

from models import (
    Game,
    GameDetail,
    League,
    LeagueSnapshot,
    MLBDetail,
    NBADetail,
    NFLDetail,
    NHLDetail,
)

log = logging.getLogger(__name__)

LEAGUE_PATHS: dict[League, str] = {
    "mlb": "baseball/mlb",
    "nba": "basketball/nba",
    "nfl": "football/nfl",
    "nhl": "hockey/nhl",
}

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/{path}/teams"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/{path}/summary"

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


def fetch_summary(league: League, event_id: str) -> GameDetail:
    """Fetch the rich per-event summary and parse the sport-specific live block.

    Returns a `GameDetail` with `error` set on any HTTP or parse failure.
    Never raises.
    """
    detail = GameDetail(event_id=event_id, league=league)
    if not event_id:
        detail.error = "missing event id"
        return detail

    path = LEAGUE_PATHS[league]
    url = SUMMARY_URL.format(path=path)
    try:
        resp = requests.get(url, params={"event": event_id}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("Summary fetch failed for %s/%s: %s", league, event_id, exc)
        detail.error = str(exc)
        return detail

    try:
        _populate_header(detail, data)
        situation = _pick_situation(data)
        if league == "mlb":
            detail.mlb = _parse_mlb_situation(data, situation)
        elif league == "nba":
            detail.nba = _parse_nba_summary(data, situation)
        elif league == "nfl":
            detail.nfl = _parse_nfl_summary(data, situation)
        elif league == "nhl":
            detail.nhl = _parse_nhl_summary(data, situation)
        detail.fetched_at = datetime.now(timezone.utc)
    except Exception as exc:  # noqa: BLE001
        log.debug("Summary parse trouble for %s/%s: %s", league, event_id, exc)
        detail.error = f"parse: {exc}"
    return detail


def _pick_situation(data: dict) -> dict:
    """ESPN sometimes nests `situation` under header.competitions[0]; sometimes top level.

    Return whichever exists, or an empty dict.
    """
    top = data.get("situation")
    if isinstance(top, dict) and top:
        return top
    try:
        return data["header"]["competitions"][0].get("situation") or {}
    except (KeyError, IndexError, TypeError):
        return {}


def _populate_header(detail: GameDetail, data: dict) -> None:
    try:
        comp = data["header"]["competitions"][0]
        competitors = comp.get("competitors") or []
        for c in competitors:
            ha = c.get("homeAway")
            team = c.get("team") or {}
            abbr = team.get("abbreviation") or ""
            tid = str(team.get("id") or "")
            score = str(c.get("score") or "")
            if ha == "home":
                detail.home_abbr = abbr or detail.home_abbr
                detail.home_team_id = tid or detail.home_team_id
                detail.home_score = score or detail.home_score
            elif ha == "away":
                detail.away_abbr = abbr or detail.away_abbr
                detail.away_team_id = tid or detail.away_team_id
                detail.away_score = score or detail.away_score
    except (KeyError, IndexError, TypeError):
        pass


def _status_period_clock(data: dict) -> tuple[str, str]:
    """Return (period_display, clock_display) for sports with a clock."""
    try:
        status = data["header"]["competitions"][0]["status"]
    except (KeyError, IndexError, TypeError):
        return ("", "")
    period = status.get("period")
    clock = status.get("displayClock") or ""
    short = (status.get("type") or {}).get("shortDetail") or ""
    if period:
        period_str = f"Q{period}" if data.get("header", {}).get("league", {}).get("name") == "" else str(period)
        # Use shortDetail if it already names the period (e.g. "End of 2nd Quarter"); otherwise just the number.
        if short:
            period_str = short
        return (period_str, clock)
    return (short, clock)


def _short_period(data: dict, prefix: str = "P") -> tuple[str, str]:
    """Period number with a sport-appropriate prefix, plus clock."""
    try:
        status = data["header"]["competitions"][0]["status"]
    except (KeyError, IndexError, TypeError):
        return ("", "")
    period = status.get("period")
    clock = status.get("displayClock") or ""
    short = (status.get("type") or {}).get("shortDetail") or ""
    if isinstance(period, int) and period > 0:
        return (f"{prefix}{period}", clock or short)
    return (short, clock)


def _team_leaders(data: dict, home_or_away: str) -> list[tuple[str, str]]:
    """Pick a couple of top stat leaders for one team.

    `home_or_away` is "home" or "away" — we match via the team id from header.
    """
    target_id = None
    try:
        comp = data["header"]["competitions"][0]
        for c in comp.get("competitors") or []:
            if c.get("homeAway") == home_or_away:
                target_id = str((c.get("team") or {}).get("id") or "")
                break
    except (KeyError, IndexError, TypeError):
        return []

    if not target_id:
        return []

    out: list[tuple[str, str]] = []
    for team_block in data.get("leaders") or []:
        team = team_block.get("team") or {}
        if str(team.get("id") or "") != target_id:
            continue
        for category in team_block.get("leaders") or []:
            cat_name = category.get("displayName") or category.get("name") or ""
            inner = category.get("leaders") or []
            if not inner:
                continue
            top = inner[0]
            athlete = top.get("athlete") or {}
            name = athlete.get("shortName") or athlete.get("displayName") or ""
            value = top.get("displayValue") or ""
            if name and value:
                out.append((name, f"{value} {cat_name}".strip()))
            if len(out) >= 3:
                return out
        return out
    return out


def _parse_mlb_situation(data: dict, situation: dict) -> MLBDetail:
    detail = MLBDetail()
    # Inning string
    try:
        detail.inning = (
            (data["header"]["competitions"][0]["status"].get("type") or {}).get("shortDetail")
            or ""
        )
    except (KeyError, IndexError, TypeError):
        pass

    if not situation:
        return detail

    detail.balls = int(situation.get("balls") or 0)
    detail.strikes = int(situation.get("strikes") or 0)
    detail.outs = int(situation.get("outs") or 0)
    # ESPN sometimes returns these as booleans, sometimes as objects describing the runner.
    detail.on_first = bool(situation.get("onFirst"))
    detail.on_second = bool(situation.get("onSecond"))
    detail.on_third = bool(situation.get("onThird"))

    pitcher = situation.get("pitcher") or {}
    p_ath = pitcher.get("athlete") or {}
    detail.pitcher_name = p_ath.get("shortName") or p_ath.get("displayName") or ""
    detail.pitcher_line = pitcher.get("summary") or ""

    batter = situation.get("batter") or {}
    b_ath = batter.get("athlete") or {}
    detail.batter_name = b_ath.get("shortName") or b_ath.get("displayName") or ""
    detail.batter_line = batter.get("summary") or ""

    last = situation.get("lastPlay") or {}
    detail.last_play = last.get("text") or ""
    return detail


def _parse_nba_summary(data: dict, situation: dict) -> NBADetail:
    detail = NBADetail()
    period, clock = _status_period_clock(data)
    detail.period = period
    detail.clock = clock
    detail.away_leaders = _team_leaders(data, "away")
    detail.home_leaders = _team_leaders(data, "home")
    last = situation.get("lastPlay") if isinstance(situation, dict) else None
    if isinstance(last, dict):
        detail.last_play = last.get("text") or ""
    return detail


def _parse_nfl_summary(data: dict, situation: dict) -> NFLDetail:
    detail = NFLDetail()
    period, clock = _status_period_clock(data)
    detail.period = period
    detail.clock = clock

    # Down / distance / yard line / possession come from situation when available,
    # otherwise from drives.current.
    if situation:
        detail.possession_abbr = (
            ((situation.get("possession") or {}).get("abbreviation"))
            or situation.get("possessionText")
            or ""
        )
        down = situation.get("down")
        distance = situation.get("distance")
        if down and distance is not None:
            detail.down_distance = f"{_ordinal(down)} & {distance}"
        elif situation.get("downDistanceText"):
            detail.down_distance = situation["downDistanceText"]
        detail.yard_line = situation.get("possessionText") or situation.get("yardLine") or ""
        last = situation.get("lastPlay") or {}
        detail.last_play = last.get("text") or ""

    try:
        drives = data.get("drives") or {}
        current = drives.get("current") or {}
        if not detail.possession_abbr:
            team = current.get("team") or {}
            detail.possession_abbr = team.get("abbreviation") or ""
        plays = current.get("plays") or []
        if plays and not detail.last_play:
            detail.last_play = (plays[-1].get("text") or plays[-1].get("type", {}).get("text") or "")
    except (AttributeError, TypeError):
        pass

    return detail


def _parse_nhl_summary(data: dict, situation: dict) -> NHLDetail:
    detail = NHLDetail()
    period, clock = _short_period(data, prefix="P")
    detail.period = period
    detail.clock = clock

    # Shots-on-goal from boxscore.
    try:
        for team_entry in (data.get("boxscore") or {}).get("teams") or []:
            ha = (team_entry.get("homeAway") or "").lower()
            for stat in team_entry.get("statistics") or []:
                name = (stat.get("name") or "").lower()
                if "shots" in name or "sog" in name:
                    try:
                        v = int((stat.get("displayValue") or "0").split()[0])
                    except (ValueError, IndexError):
                        continue
                    if ha == "home":
                        detail.home_shots = v
                    elif ha == "away":
                        detail.away_shots = v
                    break
    except (AttributeError, TypeError):
        pass

    if isinstance(situation, dict):
        # ESPN occasionally surfaces power-play info under situation; fall back silently.
        pp = situation.get("powerPlay") or situation.get("strength") or ""
        if isinstance(pp, dict):
            pp = pp.get("text") or pp.get("displayName") or ""
        detail.power_play = str(pp or "")
        last = situation.get("lastPlay") or {}
        if isinstance(last, dict):
            detail.last_play = last.get("text") or ""

    detail.away_leaders = _team_leaders(data, "away")
    detail.home_leaders = _team_leaders(data, "home")
    return detail


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


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
