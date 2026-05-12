from __future__ import annotations

import json
import logging
from typing import get_args

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from espn_client import fetch_teams
from models import League
from settings_store import TEAMS_CACHE_PATH

log = logging.getLogger(__name__)

LEAGUES: tuple[League, ...] = get_args(League)


def _load_cached_teams() -> dict[str, list[dict]]:
    if TEAMS_CACHE_PATH.exists():
        try:
            return json.loads(TEAMS_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to read teams cache: %s", exc)
    return {}


def _save_cached_teams(data: dict[str, list[dict]]) -> None:
    try:
        TEAMS_CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to write teams cache: %s", exc)


class _TeamsFetchSignals(QObject):
    done = Signal(dict)  # {league: [team dict, ...]}
    failed = Signal(str)


class _TeamsFetchRunnable(QRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.signals = _TeamsFetchSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        out: dict[str, list[dict]] = {}
        try:
            for lg in LEAGUES:
                out[lg] = fetch_teams(lg)
            _save_cached_teams(out)
            self.signals.done.emit(out)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))


class FavoritesDialog(QDialog):
    """Tabbed dialog letting the user star teams across MLB / NBA / NFL / NHL."""

    def __init__(self, current_favorites: set[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Favorites")
        self.resize(420, 480)
        self._favorites: set[str] = set(current_favorites)
        self._lists: dict[League, QListWidget] = {}

        layout = QVBoxLayout(self)

        self._status = QLabel("Loading teams...")
        layout.addWidget(self._status)

        self._tabs = QTabWidget(self)
        layout.addWidget(self._tabs, stretch=1)

        for lg in LEAGUES:
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            lw = QListWidget()
            lw.setSelectionMode(QListWidget.SelectionMode.NoSelection)
            self._lists[lg] = lw
            tab_layout.addWidget(lw)

            btn_row = QHBoxLayout()
            select_all = QPushButton("Select all")
            select_none = QPushButton("Select none")
            select_all.clicked.connect(lambda _=False, l=lg: self._set_all(l, True))
            select_none.clicked.connect(lambda _=False, l=lg: self._set_all(l, False))
            btn_row.addWidget(select_all)
            btn_row.addWidget(select_none)
            btn_row.addStretch(1)
            tab_layout.addLayout(btn_row)

            self._tabs.addTab(tab, lg.upper())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        cached = _load_cached_teams()
        if cached and all(cached.get(lg) for lg in LEAGUES):
            self._populate(cached)
            self._status.setText("Tip: Use the tabs to manage favorites for each league.")
            # Refresh in background to pick up roster changes
            self._kick_off_fetch(silent=True)
        else:
            self._kick_off_fetch(silent=False)

    def _kick_off_fetch(self, silent: bool) -> None:
        runnable = _TeamsFetchRunnable()
        runnable.signals.done.connect(self._on_teams_loaded)
        runnable.signals.failed.connect(self._on_teams_failed)
        QThreadPool.globalInstance().start(runnable)
        if not silent:
            self._status.setText("Fetching team rosters from ESPN...")

    def _on_teams_loaded(self, data: dict) -> None:
        self._populate(data)
        self._status.setText("Tip: Use the tabs to manage favorites for each league.")

    def _on_teams_failed(self, msg: str) -> None:
        cached = _load_cached_teams()
        if cached:
            self._status.setText(f"Showing cached teams (refresh failed: {msg})")
        else:
            self._status.setText(f"Failed to load teams: {msg}")

    def _populate(self, data: dict) -> None:
        for lg in LEAGUES:
            lw = self._lists[lg]
            lw.clear()
            for team in data.get(lg, []):
                abbr = team.get("abbreviation") or ""
                name = team.get("displayName") or abbr
                if not abbr:
                    continue
                item = QListWidgetItem(f"{name}  ({abbr})")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                key = f"{lg}:{abbr}"
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setCheckState(
                    Qt.CheckState.Checked
                    if key in self._favorites
                    else Qt.CheckState.Unchecked
                )
                lw.addItem(item)

    def _set_all(self, league: League, checked: bool) -> None:
        lw = self._lists[league]
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(lw.count()):
            lw.item(i).setCheckState(state)

    def _on_accept(self) -> None:
        selected: set[str] = set()
        for lw in self._lists.values():
            for i in range(lw.count()):
                item = lw.item(i)
                if item.checkState() == Qt.CheckState.Checked:
                    key = item.data(Qt.ItemDataRole.UserRole)
                    if key:
                        selected.add(str(key))
        self._favorites = selected
        self.accept()

    def selected_favorites(self) -> set[str]:
        return set(self._favorites)
