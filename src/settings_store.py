from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings


def _config_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        d = Path(base) / "SportsWidget"
    else:
        d = Path.home() / ".sportswidget"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_DIR = _config_dir()
SETTINGS_PATH = CONFIG_DIR / "settings.ini"
TEAMS_CACHE_PATH = CONFIG_DIR / "teams.json"


class SettingsStore:
    """Thin wrapper around QSettings — portable INI in %APPDATA%\\SportsWidget."""

    def __init__(self) -> None:
        self._s = QSettings(str(SETTINGS_PATH), QSettings.Format.IniFormat)

    # --- Window geometry ---
    def save_geometry(self, geom: QByteArray) -> None:
        self._s.setValue("window/geometry", geom)

    def load_geometry(self) -> QByteArray | None:
        v = self._s.value("window/geometry")
        if isinstance(v, QByteArray) and not v.isEmpty():
            return v
        return None

    # --- Lock state ---
    def save_locked(self, locked: bool) -> None:
        self._s.setValue("window/locked", bool(locked))

    def load_locked(self) -> bool:
        return self._s.value("window/locked", False, type=bool)

    # --- Favorites filter ---
    def save_favorites_only(self, on: bool) -> None:
        self._s.setValue("view/favorites_only", bool(on))

    def load_favorites_only(self) -> bool:
        return self._s.value("view/favorites_only", False, type=bool)

    # --- Favorites set ---
    def save_favorites(self, favorites: set[str]) -> None:
        self._s.setValue("favorites/keys", sorted(favorites))

    def load_favorites(self) -> set[str]:
        v = self._s.value("favorites/keys", [])
        if v is None:
            return set()
        if isinstance(v, str):
            return {v} if v else set()
        try:
            return {str(x) for x in v if x}
        except TypeError:
            return set()

    def sync(self) -> None:
        self._s.sync()
