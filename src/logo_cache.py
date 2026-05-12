from __future__ import annotations

import logging
from pathlib import Path

import requests
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QPixmap

from settings_store import CONFIG_DIR

log = logging.getLogger(__name__)

LOGOS_DIR = CONFIG_DIR / "logos"
LOGOS_DIR.mkdir(parents=True, exist_ok=True)

# Logo render height in CSS pixels — close to the matchup font size.
# We download/store the original (typically 500px) and scale to this on read.
LOGO_HEIGHT_PX = 16


def _migrate_legacy_cache() -> None:
    """Remove pre-namespacing flat *.png files at the top of LOGOS_DIR.

    They were keyed only by team_id, which collides across leagues for
    same-city franchises (Cavaliers/Guardians both have id=5, etc.).
    Anything still at the top level is unsafe; logos will simply re-download
    under the new {league}/{team_id}.png layout. No-op after first run.
    """
    try:
        for entry in LOGOS_DIR.iterdir():
            if entry.is_file() and entry.suffix.lower() == ".png":
                try:
                    entry.unlink()
                except OSError as exc:
                    log.debug("Could not remove legacy logo %s: %s", entry, exc)
    except OSError:
        pass


class _LogoFetchSignals(QObject):
    done = Signal(str, str)        # league, team_id
    failed = Signal(str, str, str) # league, team_id, message


class _LogoFetch(QRunnable):
    def __init__(self, league: str, team_id: str, url: str, path: Path) -> None:
        super().__init__()
        self._league = league
        self._team_id = team_id
        self._url = url
        self._path = path
        self.signals = _LogoFetchSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            resp = requests.get(self._url, timeout=10)
            resp.raise_for_status()
            self._path.write_bytes(resp.content)
            self.signals.done.emit(self._league, self._team_id)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self._league, self._team_id, str(exc))


class LogoCache(QObject):
    """Lazy team-logo cache, namespaced per league.

    Cache keys are (league, team_id) everywhere — memory, on-disk, in-flight,
    failed — because ESPN reuses small numeric IDs across leagues (e.g.
    Cleveland Cavaliers NBA id=5 collides with Cleveland Guardians MLB id=5).

    Lookups return immediately from memory or disk. A miss returns None and,
    if a URL is known, dispatches a background download. When the download
    finishes the cache emits `logo_ready(league, team_id)` so widgets can
    re-render.
    """

    logo_ready = Signal(str, str)  # league, team_id

    _instance: "LogoCache | None" = None

    @classmethod
    def instance(cls) -> "LogoCache":
        if cls._instance is None:
            cls._instance = LogoCache()
        return cls._instance

    def __init__(self) -> None:
        super().__init__()
        _migrate_legacy_cache()
        self._memory: dict[tuple[str, str], QPixmap] = {}
        self._in_flight: set[tuple[str, str]] = set()
        self._failed: set[tuple[str, str]] = set()

    def get(self, league: str, team_id: str) -> QPixmap | None:
        if not league or not team_id:
            return None
        key = (league, team_id)
        cached = self._memory.get(key)
        if cached is not None:
            return cached if not cached.isNull() else None

        path = self._path(league, team_id)
        if path.exists():
            raw = QPixmap(str(path))
            if not raw.isNull():
                scaled = raw.scaledToHeight(
                    LOGO_HEIGHT_PX * 2,  # render at 2x for crispness
                    Qt.TransformationMode.SmoothTransformation,
                )
                scaled.setDevicePixelRatio(2.0)
                self._memory[key] = scaled
                return scaled
        return None

    def request(self, league: str, team_id: str, url: str) -> None:
        if not league or not team_id or not url:
            return
        key = (league, team_id)
        if key in self._memory or key in self._in_flight or key in self._failed:
            return
        if self._path(league, team_id).exists():
            return
        self._in_flight.add(key)
        runnable = _LogoFetch(league, team_id, url, self._path(league, team_id))
        runnable.signals.done.connect(self._on_done)
        runnable.signals.failed.connect(self._on_failed)
        QThreadPool.globalInstance().start(runnable)

    def _on_done(self, league: str, team_id: str) -> None:
        key = (league, team_id)
        self._in_flight.discard(key)
        self._memory.pop(key, None)  # force reload from disk
        if self.get(league, team_id) is not None:
            self.logo_ready.emit(league, team_id)

    def _on_failed(self, league: str, team_id: str, msg: str) -> None:
        key = (league, team_id)
        self._in_flight.discard(key)
        self._failed.add(key)
        log.debug("Logo fetch failed for %s/%s: %s", league, team_id, msg)

    @staticmethod
    def _path(league: str, team_id: str) -> Path:
        return LOGOS_DIR / league / f"{team_id}.png"
