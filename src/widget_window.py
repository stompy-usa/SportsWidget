from __future__ import annotations

from datetime import datetime, timezone
from typing import get_args

from PySide6.QtCore import QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QContextMenuEvent
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QMenu,
    QScrollArea,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from fetch_worker import FetchRunnable
from models import Game, League, LeagueSnapshot
from settings_store import SettingsStore
from ui.game_row import GameRow
from ui.header_bar import HeaderBar

LEAGUES: tuple[League, ...] = get_args(League)

REFRESH_INTERVAL_MS = 15_000


class WidgetWindow(QWidget):
    def __init__(self, settings: SettingsStore) -> None:
        super().__init__()
        self._settings = settings
        self._snapshots: dict[League, LeagueSnapshot] = {}
        self._favorites: set[str] = settings.load_favorites()
        self._favorites_only: bool = settings.load_favorites_only()
        self._locked: bool = settings.load_locked()

        self._build_window_flags()
        self._build_ui()
        self._restore_geometry()
        self._apply_locked(self._locked)

        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh_now)

    # ---------- Window setup ----------

    def _build_window_flags(self) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnBottomHint
            | Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Sports Widget")
        self.setMinimumSize(QSize(260, 200))

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Single rounded frame holds everything so the translucent background renders cleanly.
        self._frame = QFrame(self)
        self._frame.setObjectName("RootFrame")
        outer.addWidget(self._frame)

        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        self._header = HeaderBar(self._frame)
        self._header.set_favorites_only(self._favorites_only)
        self._header.favorites_toggled.connect(self._on_favorites_toggled)
        self._header.refresh_requested.connect(self.refresh_now)
        self._header.favorites_dialog_requested.connect(self._open_favorites_dialog)
        self._header.close_requested.connect(self.hide)
        frame_layout.addWidget(self._header)

        # Scrollable game list
        self._scroll = QScrollArea(self._frame)
        self._scroll.setObjectName("GamesScrollArea")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(6, 4, 6, 4)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._list_host)
        frame_layout.addWidget(self._scroll, stretch=1)

        # Resize grip in the bottom-right
        grip_row = QWidget(self._frame)
        grip_row_layout = QVBoxLayout(grip_row)
        grip_row_layout.setContentsMargins(0, 0, 4, 4)
        grip_row_layout.setSpacing(0)
        self._grip = QSizeGrip(grip_row)
        grip_row_layout.addWidget(self._grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        frame_layout.addWidget(grip_row)

    def _restore_geometry(self) -> None:
        geom = self._settings.load_geometry()
        if geom is not None:
            self.restoreGeometry(geom)
        else:
            self.resize(340, 520)
            screen = self.screen().availableGeometry() if self.screen() else None
            if screen:
                self.move(screen.right() - self.width() - 24, screen.top() + 60)

    # ---------- Public API ----------

    def start(self) -> None:
        self._timer.start()
        QTimer.singleShot(50, self.refresh_now)

    def refresh_now(self) -> None:
        self._header.set_status("Refreshing...")
        runnable = FetchRunnable()
        runnable.signals.snapshots_ready.connect(self._on_snapshots)
        QThreadPool.globalInstance().start(runnable)

    def set_favorites(self, favorites: set[str]) -> None:
        self._favorites = set(favorites)
        self._settings.save_favorites(self._favorites)
        self._render()

    def get_favorites(self) -> set[str]:
        return set(self._favorites)

    def toggle_lock(self) -> None:
        self._apply_locked(not self._locked)

    def is_locked(self) -> bool:
        return self._locked

    # ---------- Internal ----------

    def _apply_locked(self, locked: bool) -> None:
        self._locked = locked
        self._settings.save_locked(locked)
        self._header.set_locked(locked)
        self._grip.setVisible(not locked)

    def _on_favorites_toggled(self, on: bool) -> None:
        self._favorites_only = on
        self._settings.save_favorites_only(on)
        self._render()

    def _open_favorites_dialog(self) -> None:
        # Lazy import to avoid a cycle and keep startup quick.
        from favorites_dialog import FavoritesDialog

        dlg = FavoritesDialog(self._favorites, self)
        if dlg.exec():
            self.set_favorites(dlg.selected_favorites())

    def _on_snapshots(self, snapshots: list[LeagueSnapshot]) -> None:
        any_error = False
        for snap in snapshots:
            if snap.error and snap.league in self._snapshots:
                # Keep last known games for this league; mark error
                prev = self._snapshots[snap.league]
                prev.error = snap.error
                any_error = True
            else:
                self._snapshots[snap.league] = snap
                if snap.error:
                    any_error = True
        now = datetime.now().strftime("%H:%M")
        self._header.set_status(("Stale - " if any_error else "Updated ") + now)
        self._render()

    def _render(self) -> None:
        # Clear all but the trailing stretch
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        games = self._collect_games()
        if not games:
            empty = QLabel("No games to show.")
            empty.setObjectName("EmptyLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_layout.insertWidget(0, empty)
            return

        # Group: Live, Today, Tomorrow
        today_local = datetime.now().date()
        groups: dict[str, list[Game]] = {"LIVE": [], "TODAY": [], "TOMORROW": []}
        for g in games:
            if g.state == "in":
                groups["LIVE"].append(g)
                continue
            local_day = g.start_utc.astimezone().date()
            if local_day == today_local:
                groups["TODAY"].append(g)
            else:
                groups["TOMORROW"].append(g)

        insert_at = 0
        for label in ("LIVE", "TODAY", "TOMORROW"):
            bucket = groups[label]
            if not bucket:
                continue
            section = QLabel(label)
            section.setObjectName("SectionLabel")
            self._list_layout.insertWidget(insert_at, section)
            insert_at += 1
            for g in bucket:
                is_fav = g.involves_any(self._favorites)
                row = GameRow(g, is_favorite=is_fav)
                self._list_layout.insertWidget(insert_at, row)
                insert_at += 1

    def _collect_games(self) -> list[Game]:
        out: list[Game] = []
        for lg in LEAGUES:
            snap = self._snapshots.get(lg)
            if not snap:
                continue
            for g in snap.games:
                if self._favorites_only and not g.involves_any(self._favorites):
                    continue
                out.append(g)

        def sort_key(g: Game) -> tuple[int, datetime]:
            # Live first, then by start time
            state_rank = 0 if g.state == "in" else (1 if g.state == "pre" else 2)
            return (state_rank, g.start_utc.astimezone(timezone.utc))

        out.sort(key=sort_key)
        return out

    # ---------- Events ----------

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self)

        act_refresh = QAction("Refresh now", self)
        act_refresh.triggered.connect(self.refresh_now)
        menu.addAction(act_refresh)

        act_fav = QAction("Favorites...", self)
        act_fav.triggered.connect(self._open_favorites_dialog)
        menu.addAction(act_fav)

        act_lock = QAction("Unlock" if self._locked else "Lock", self)
        act_lock.triggered.connect(self.toggle_lock)
        menu.addAction(act_lock)

        menu.addSeparator()

        act_hide = QAction("Hide", self)
        act_hide.triggered.connect(self.hide)
        menu.addAction(act_hide)

        menu.exec(event.globalPos())

    def closeEvent(self, event: QCloseEvent) -> None:
        # Persist state, then hide instead of quit (tray handles quit).
        self._settings.save_geometry(self.saveGeometry())
        self._settings.sync()
        event.ignore()
        self.hide()

    def shutdown(self) -> None:
        """Called from main on real quit — persist final state."""
        self._settings.save_geometry(self.saveGeometry())
        self._settings.sync()
