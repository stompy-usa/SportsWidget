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
            home_short_name=_short_name(home),
            away_short_name=_short_name(away),
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


def _short_name(competitor: dict) -> str:
    team = competitor.get("team", {}) or {}
    return (
        team.get("shortDisplayName")
        or team.get("name")
        or team.get("displayName")
        or team.get("abbreviation")
        or "?"
    )


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
            detail.mlb = _parse_mlb_summary(detail, data, situation)
        elif league == "nba":
            detail.nba = _parse_nba_summary(detail, data, situation)
        elif league == "nfl":
            detail.nfl = _parse_nfl_summary(detail, data, situation)
        elif league == "nhl":
            detail.nhl = _parse_nhl_summary(detail, data, situation)
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
        # Game state ("pre" / "in" / "post")
        state_value = ((comp.get("status") or {}).get("type") or {}).get("state")
        if state_value in ("pre", "in", "post"):
            detail.state = state_value  # type: ignore[assignment]
    except (KeyError, IndexError, TypeError):
        pass


def _team_records(data: dict) -> tuple[str, str]:
    """Return (away_record, home_record) using each competitor's 'total' record."""
    away_rec = ""
    home_rec = ""
    try:
        for c in data["header"]["competitions"][0]["competitors"]:
            ha = c.get("homeAway")
            records = c.get("record") or []
            rec_str = ""
            for r in records:
                if r.get("type") == "total":
                    rec_str = r.get("displayValue") or r.get("summary") or ""
                    break
            if ha == "away":
                away_rec = rec_str
            elif ha == "home":
                home_rec = rec_str
    except (KeyError, IndexError, TypeError):
        pass
    return (away_rec, home_rec)


def _short_athlete_name(athlete: dict) -> str:
    return athlete.get("shortName") or athlete.get("displayName") or athlete.get("fullName") or ""


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


def _parse_mlb_summary(parent: GameDetail, data: dict, situation: dict) -> MLBDetail:
    m = MLBDetail()

    # In-game (situation) fields
    try:
        m.inning = (
            (data["header"]["competitions"][0]["status"].get("type") or {}).get("shortDetail")
            or ""
        )
    except (KeyError, IndexError, TypeError):
        pass

    if situation:
        m.balls = int(situation.get("balls") or 0)
        m.strikes = int(situation.get("strikes") or 0)
        m.outs = int(situation.get("outs") or 0)
        m.on_first = bool(situation.get("onFirst"))
        m.on_second = bool(situation.get("onSecond"))
        m.on_third = bool(situation.get("onThird"))
        pitcher = situation.get("pitcher") or {}
        m.pitcher_name = _short_athlete_name(pitcher.get("athlete") or {})
        m.pitcher_line = pitcher.get("summary") or ""
        batter = situation.get("batter") or {}
        m.batter_name = _short_athlete_name(batter.get("athlete") or {})
        m.batter_line = batter.get("summary") or ""
        last = situation.get("lastPlay") or {}
        m.last_play = last.get("text") or ""

    # Pre-game: probable starting pitchers from competitor.probables[]
    try:
        for c in data["header"]["competitions"][0]["competitors"]:
            ha = c.get("homeAway")
            probables = c.get("probables") or []
            if not probables:
                continue
            # The starter is typically the first item with name=probableStartingPitcher;
            # fall back to the first entry.
            sp = next(
                (p for p in probables if (p.get("name") or "").lower().startswith("probable")),
                probables[0],
            )
            name = _short_athlete_name(sp.get("athlete") or {})
            if ha == "away":
                m.away_probable_pitcher = name
            elif ha == "home":
                m.home_probable_pitcher = name
    except (KeyError, IndexError, TypeError):
        pass

    # Pre-game: starting lineup from rosters[]
    for entry in data.get("rosters") or []:
        team_id = str((entry.get("team") or {}).get("id") or "")
        roster = entry.get("roster") or []
        lineup: list[tuple[str, str]] = []
        for r in roster:
            if not r.get("starter"):
                continue
            ath = r.get("athlete") or {}
            pos = (r.get("position") or {}).get("abbreviation") or ""
            name = _short_athlete_name(ath)
            if name:
                lineup.append((pos, name))
            if len(lineup) >= 9:
                break
        if not lineup:
            continue
        if team_id and team_id == parent.away_team_id:
            m.away_lineup = lineup
        elif team_id and team_id == parent.home_team_id:
            m.home_lineup = lineup

    m.away_record, m.home_record = _team_records(data)
    return m


def _parse_nba_summary(parent: GameDetail, data: dict, situation: dict) -> NBADetail:
    n = NBADetail()
    period, clock = _status_period_clock(data)
    n.period = period
    n.clock = clock
    n.away_leaders = _team_leaders(data, "away")
    n.home_leaders = _team_leaders(data, "home")
    last = situation.get("lastPlay") if isinstance(situation, dict) else None
    if isinstance(last, dict):
        n.last_play = last.get("text") or ""
    n.away_record, n.home_record = _team_records(data)
    return n


def _parse_nfl_summary(parent: GameDetail, data: dict, situation: dict) -> NFLDetail:
    n = NFLDetail()
    period, clock = _status_period_clock(data)
    n.period = period
    n.clock = clock

    if situation:
        n.possession_abbr = (
            ((situation.get("possession") or {}).get("abbreviation"))
            or situation.get("possessionText")
            or ""
        )
        down = situation.get("down")
        distance = situation.get("distance")
        if down and distance is not None:
            n.down_distance = f"{_ordinal(down)} & {distance}"
        elif situation.get("downDistanceText"):
            n.down_distance = situation["downDistanceText"]
        n.yard_line = situation.get("possessionText") or situation.get("yardLine") or ""
        last = situation.get("lastPlay") or {}
        n.last_play = last.get("text") or ""

    try:
        drives = data.get("drives") or {}
        current = drives.get("current") or {}
        if not n.possession_abbr:
            team = current.get("team") or {}
            n.possession_abbr = team.get("abbreviation") or ""
        plays = current.get("plays") or []
        if plays and not n.last_play:
            n.last_play = (plays[-1].get("text") or plays[-1].get("type", {}).get("text") or "")
    except (AttributeError, TypeError):
        pass

    n.away_record, n.home_record = _team_records(data)
    return n


def _parse_nhl_summary(parent: GameDetail, data: dict, situation: dict) -> NHLDetail:
    n = NHLDetail()
    period, clock = _short_period(data, prefix="P")
    n.period = period
    n.clock = clock

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
                        n.home_shots = v
                    elif ha == "away":
                        n.away_shots = v
                    break
    except (AttributeError, TypeError):
        pass

    if isinstance(situation, dict):
        pp = situation.get("powerPlay") or situation.get("strength") or ""
        if isinstance(pp, dict):
            pp = pp.get("text") or pp.get("displayName") or ""
        n.power_play = str(pp or "")
        last = situation.get("lastPlay") or {}
        if isinstance(last, dict):
            n.last_play = last.get("text") or ""

    n.away_leaders = _team_leaders(data, "away")
    n.home_leaders = _team_leaders(data, "home")

    # Pre-game: starting goalies from top-level goalies = {homeTeam, awayTeam}
    goalies = data.get("goalies")
    if isinstance(goalies, dict):
        away_g = goalies.get("awayTeam") or {}
        home_g = goalies.get("homeTeam") or {}
        away_athletes = away_g.get("athletes") or []
        home_athletes = home_g.get("athletes") or []
        if away_athletes:
            n.away_goalie = _short_athlete_name(away_athletes[0])
        if home_athletes:
            n.home_goalie = _short_athlete_name(home_athletes[0])

    n.away_record, n.home_record = _team_records(data)
    return n


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
