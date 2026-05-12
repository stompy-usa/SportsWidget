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

# Logo render height in CSS pixels — close to the 12px font we use for matchups.
# We download/store the original (typically 500px) and scale to this on read.
LOGO_HEIGHT_PX = 14


class _LogoFetchSignals(QObject):
    done = Signal(str)            # team_id
    failed = Signal(str, str)     # team_id, message


class _LogoFetch(QRunnable):
    def __init__(self, team_id: str, url: str, path: Path) -> None:
        super().__init__()
        self._team_id = team_id
        self._url = url
        self._path = path
        self.signals = _LogoFetchSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            resp = requests.get(self._url, timeout=10)
            resp.raise_for_status()
            self._path.write_bytes(resp.content)
            self.signals.done.emit(self._team_id)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self._team_id, str(exc))


class LogoCache(QObject):
    """Lazy team-logo cache.

    Lookups return immediately from memory or disk. A miss returns None and,
    if a URL is known, dispatches a background download. When the download
    finishes the cache emits `logo_ready(team_id)` so widgets can re-render.
    """

    logo_ready = Signal(str)  # team_id

    _instance: "LogoCache | None" = None

    @classmethod
    def instance(cls) -> "LogoCache":
        if cls._instance is None:
            cls._instance = LogoCache()
        return cls._instance

    def __init__(self) -> None:
        super().__init__()
        self._memory: dict[str, QPixmap] = {}
        self._in_flight: set[str] = set()
        self._failed: set[str] = set()

    def get(self, team_id: str) -> QPixmap | None:
        if not team_id:
            return None
        cached = self._memory.get(team_id)
        if cached is not None:
            return cached if not cached.isNull() else None

        path = self._path(team_id)
        if path.exists():
            raw = QPixmap(str(path))
            if not raw.isNull():
                scaled = raw.scaledToHeight(
                    LOGO_HEIGHT_PX * 2,  # render at 2x for crispness
                    Qt.TransformationMode.SmoothTransformation,
                )
                scaled.setDevicePixelRatio(2.0)
                self._memory[team_id] = scaled
                return scaled
        return None

    def request(self, team_id: str, url: str) -> None:
        if not team_id or not url:
            return
        if team_id in self._memory or team_id in self._in_flight or team_id in self._failed:
            return
        if self._path(team_id).exists():
            return
        self._in_flight.add(team_id)
        runnable = _LogoFetch(team_id, url, self._path(team_id))
        runnable.signals.done.connect(self._on_done)
        runnable.signals.failed.connect(self._on_failed)
        QThreadPool.globalInstance().start(runnable)

    def _on_done(self, team_id: str) -> None:
        self._in_flight.discard(team_id)
        # Drop any stale memory entry so the next get() reloads from disk.
        self._memory.pop(team_id, None)
        if self.get(team_id) is not None:
            self.logo_ready.emit(team_id)

    def _on_failed(self, team_id: str, msg: str) -> None:
        self._in_flight.discard(team_id)
        self._failed.add(team_id)
        log.debug("Logo fetch failed for %s: %s", team_id, msg)

    @staticmethod
    def _path(team_id: str) -> Path:
        return LOGOS_DIR / f"{team_id}.png"
