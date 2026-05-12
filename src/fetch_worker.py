from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import get_args

from PySide6.QtCore import QObject, QRunnable, Signal

from espn_client import fetch_scoreboard, fetch_summary
from models import GameDetail, League, LeagueSnapshot

LEAGUES: tuple[League, ...] = get_args(League)


class FetchSignals(QObject):
    snapshots_ready = Signal(list)  # list[LeagueSnapshot]


class FetchRunnable(QRunnable):
    """Hits all 4 ESPN league scoreboards for today + tomorrow in parallel."""

    def __init__(self) -> None:
        super().__init__()
        self.signals = FetchSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        today = date.today()
        days = [today, today + timedelta(days=1)]

        snapshots: list[LeagueSnapshot] = []
        with ThreadPoolExecutor(max_workers=len(LEAGUES)) as pool:
            futures = {pool.submit(fetch_scoreboard, lg, days): lg for lg in LEAGUES}
            for fut in futures:
                try:
                    snapshots.append(fut.result())
                except Exception as exc:  # noqa: BLE001
                    lg = futures[fut]
                    snapshots.append(LeagueSnapshot(league=lg, error=str(exc)))

        snapshots.sort(key=lambda s: LEAGUES.index(s.league))
        self.signals.snapshots_ready.emit(snapshots)


class DetailFetchSignals(QObject):
    detail_ready = Signal(object)  # GameDetail


class DetailFetchRunnable(QRunnable):
    """Fetches the rich summary for a single live game."""

    def __init__(self, league: League, event_id: str) -> None:
        super().__init__()
        self.signals = DetailFetchSignals()
        self.setAutoDelete(True)
        self._league = league
        self._event_id = event_id

    def run(self) -> None:
        detail: GameDetail = fetch_summary(self._league, self._event_id)
        self.signals.detail_ready.emit(detail)
