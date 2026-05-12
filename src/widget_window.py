from __future__ import annotations

from datetime import datetime, timezone
from typing import get_args

from PySide6.QtCore import QPoint, QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from fetch_worker import DetailFetchRunnable, FetchRunnable
from logo_cache import LogoCache
from models import Game, GameDetail, League, LeagueSnapshot
from settings_store import SettingsStore
from ui.detail_panel import DetailPanel
from ui.game_row import GameRow
from ui.league_filter_bar import LeagueFilterBar
from ui.section_header import SectionHeader, apply_text_shadow

LEAGUES: tuple[League, ...] = get_args(League)

REFRESH_INTERVAL_MS = 15_000

SECTION_ORDER = ("LIVE", "TODAY", "TOMORROW")


class WidgetWindow(QWidget):
    def __init__(self, settings: SettingsStore) -> None:
        super().__init__()
        self._settings = settings
        self._snapshots: dict[League, LeagueSnapshot] = {}
        self._favorites: set[str] = settings.load_favorites()
        self._favorites_only: bool = settings.load_favorites_only()
        self._locked: bool = settings.load_locked()
        self._collapsed: dict[str, bool] = settings.load_collapsed_sections()
        self._enabled_leagues: set[str] = settings.load_enabled_leagues()
        self._drag_offset: QPoint | None = None
        self._open_detail_event_id: str | None = None
        self._open_detail_league: League | None = None
        self._open_detail_game: Game | None = None

        self._build_window_flags()
        self._build_ui()
        self._restore_geometry()
        self._apply_locked(self._locked)

        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh_now)

        # Debounce: many logos may finish within milliseconds of each other.
        self._logo_render_timer = QTimer(self)
        self._logo_render_timer.setSingleShot(True)
        self._logo_render_timer.setInterval(120)
        self._logo_render_timer.timeout.connect(self._render)
        LogoCache.instance().logo_ready.connect(self._on_logo_ready)

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
        self.setMinimumSize(QSize(240, 160))

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._frame = QFrame(self)
        self._frame.setObjectName("RootFrame")
        outer.addWidget(self._frame)

        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        # League filter bar
        self._filter_bar = LeagueFilterBar(self._enabled_leagues, self._frame)
        self._filter_bar.league_toggled.connect(self._on_league_toggled)
        frame_layout.addWidget(self._filter_bar)

        # Live-game detail panel (hidden until a row's "More detail" is clicked)
        self._detail_panel = DetailPanel(self._frame)
        self._detail_panel.closed.connect(self._close_detail)
        frame_layout.addWidget(self._detail_panel)

        # Scrollable game list
        self._scroll = QScrollArea(self._frame)
        self._scroll.setObjectName("GamesScrollArea")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.viewport().setAutoFillBackground(False)

        self._list_host = QWidget()
        self._list_host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(4, 4, 4, 4)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._list_host)
        frame_layout.addWidget(self._scroll, stretch=1)

        # Bottom row: stale indicator (left) + resize grip (right)
        bottom_row = QWidget(self._frame)
        bottom_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        bottom_layout = QHBoxLayout(bottom_row)
        bottom_layout.setContentsMargins(6, 0, 4, 4)
        bottom_layout.setSpacing(0)

        self._stale_label = QLabel("• stale", bottom_row)
        self._stale_label.setObjectName("StaleIndicator")
        self._stale_label.setVisible(False)
        apply_text_shadow(self._stale_label)
        bottom_layout.addWidget(self._stale_label)
        bottom_layout.addStretch(1)

        self._grip = QSizeGrip(bottom_row)
        bottom_layout.addWidget(self._grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        frame_layout.addWidget(bottom_row)

    def _restore_geometry(self) -> None:
        geom = self._settings.load_geometry()
        if geom is not None:
            self.restoreGeometry(geom)
        else:
            self.resize(320, 480)
            screen = self.screen().availableGeometry() if self.screen() else None
            if screen:
                self.move(screen.right() - self.width() - 24, screen.top() + 60)

    # ---------- Public API ----------

    def start(self) -> None:
        self._timer.start()
        QTimer.singleShot(50, self.refresh_now)

    def refresh_now(self) -> None:
        runnable = FetchRunnable()
        runnable.signals.snapshots_ready.connect(self._on_snapshots)
        QThreadPool.globalInstance().start(runnable)
        if self._open_detail_event_id and self._open_detail_league:
            self._dispatch_detail_fetch(self._open_detail_league, self._open_detail_event_id)

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
        self._grip.setVisible(not locked)
        if locked:
            self._drag_offset = None

    def _toggle_favorites_only(self) -> None:
        self._favorites_only = not self._favorites_only
        self._settings.save_favorites_only(self._favorites_only)
        self._render()

    def _open_favorites_dialog(self) -> None:
        from favorites_dialog import FavoritesDialog

        dlg = FavoritesDialog(self._favorites, self)
        if dlg.exec():
            self.set_favorites(dlg.selected_favorites())

    def _on_logo_ready(self, _league: str, _team_id: str) -> None:
        self._logo_render_timer.start()

    # ---------- Detail panel ----------

    def _on_detail_requested(self, league: str, event_id: str) -> None:
        # Toggle off if clicking the same row's button again
        if self._open_detail_event_id == event_id:
            self._close_detail()
            return

        game = self._find_game(league, event_id)
        if game is None:
            return
        self._open_detail_league = league  # type: ignore[assignment]
        self._open_detail_event_id = event_id
        self._open_detail_game = game
        self._detail_panel.show_for(game)
        self._dispatch_detail_fetch(league, event_id)  # type: ignore[arg-type]

    def _close_detail(self) -> None:
        self._open_detail_event_id = None
        self._open_detail_league = None
        self._open_detail_game = None
        self._detail_panel.clear()

    def _dispatch_detail_fetch(self, league: League, event_id: str) -> None:
        runnable = DetailFetchRunnable(league, event_id)
        runnable.signals.detail_ready.connect(self._on_detail_ready)
        QThreadPool.globalInstance().start(runnable)

    def _on_detail_ready(self, detail: GameDetail) -> None:
        if detail.event_id != self._open_detail_event_id:
            return
        self._detail_panel.set_detail(detail)

    def _find_game(self, league: str, event_id: str) -> Game | None:
        snap = self._snapshots.get(league)  # type: ignore[arg-type]
        if not snap:
            return None
        for g in snap.games:
            if g.event_id == event_id:
                return g
        return None

    def _on_league_toggled(self, league: str, enabled: bool) -> None:
        if enabled:
            self._enabled_leagues.add(league)
        else:
            self._enabled_leagues.discard(league)
        self._settings.save_enabled_leagues(self._enabled_leagues)
        self._render()

    def _on_section_toggled(self, key: str, collapsed: bool) -> None:
        self._collapsed[key] = collapsed
        self._settings.save_collapsed_sections(self._collapsed)
        self._render()

    def _on_snapshots(self, snapshots: list[LeagueSnapshot]) -> None:
        any_error = False
        error_msgs: list[str] = []
        for snap in snapshots:
            if snap.error and snap.league in self._snapshots:
                prev = self._snapshots[snap.league]
                prev.error = snap.error
                any_error = True
                error_msgs.append(f"{snap.league}: {snap.error}")
            else:
                self._snapshots[snap.league] = snap
                if snap.error:
                    any_error = True
                    error_msgs.append(f"{snap.league}: {snap.error}")

        self._stale_label.setVisible(any_error)
        self._stale_label.setToolTip("\n".join(error_msgs) if error_msgs else "")

        # Auto-close the detail panel if its game finished or vanished.
        if self._open_detail_event_id and self._open_detail_league:
            current = self._find_game(self._open_detail_league, self._open_detail_event_id)
            if current is None or current.state != "in":
                self._close_detail()

        self._render()

    def _render(self) -> None:
        # Clear all rows but keep the trailing stretch.
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
            apply_text_shadow(empty)
            self._list_layout.insertWidget(0, empty)
            return

        today_local = datetime.now().date()
        buckets: dict[str, list[Game]] = {k: [] for k in SECTION_ORDER}
        for g in games:
            if g.state == "in":
                buckets["LIVE"].append(g)
                continue
            local_day = g.start_utc.astimezone().date()
            if local_day == today_local:
                buckets["TODAY"].append(g)
            else:
                buckets["TOMORROW"].append(g)

        insert_at = 0
        for key in SECTION_ORDER:
            bucket = buckets[key]
            if not bucket:
                continue
            bucket.sort(key=lambda g: (g.league, g.start_utc.astimezone(timezone.utc)))
            collapsed = bool(self._collapsed.get(key, False))
            header = SectionHeader(key, key, collapsed)
            header.toggled.connect(self._on_section_toggled)
            self._list_layout.insertWidget(insert_at, header)
            insert_at += 1
            if collapsed:
                continue
            for g in bucket:
                is_fav = g.involves_any(self._favorites)
                row = GameRow(g, is_favorite=is_fav)
                row.detail_requested.connect(self._on_detail_requested)
                self._list_layout.insertWidget(insert_at, row)
                insert_at += 1

    def _collect_games(self) -> list[Game]:
        out: list[Game] = []
        for lg in LEAGUES:
            if lg not in self._enabled_leagues:
                continue
            snap = self._snapshots.get(lg)
            if not snap:
                continue
            for g in snap.games:
                if self._favorites_only and not g.involves_any(self._favorites):
                    continue
                out.append(g)
        return out

    # ---------- Events ----------

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        # A context menu opens via right-click — make sure no drag is mid-flight.
        self._drag_offset = None

        menu = QMenu(self)

        act_refresh = QAction("Refresh now", self)
        act_refresh.triggered.connect(self.refresh_now)
        menu.addAction(act_refresh)

        act_fav_only = QAction("Show favorites only", self, checkable=True)
        act_fav_only.setChecked(self._favorites_only)
        act_fav_only.triggered.connect(self._toggle_favorites_only)
        menu.addAction(act_fav_only)

        act_manage = QAction("Manage favorites...", self)
        act_manage.triggered.connect(self._open_favorites_dialog)
        menu.addAction(act_manage)

        menu.addSeparator()

        act_lock = QAction("Unlock" if self._locked else "Lock", self)
        act_lock.triggered.connect(self.toggle_lock)
        menu.addAction(act_lock)

        act_hide = QAction("Hide", self)
        act_hide.triggered.connect(self.hide)
        menu.addAction(act_hide)

        menu.exec(event.globalPos())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._locked or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is None or self._locked:
            return super().mouseMoveEvent(event)
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        self.move(event.globalPosition().toPoint() - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._settings.save_geometry(self.saveGeometry())
        self._settings.sync()
        event.ignore()
        self.hide()

    def shutdown(self) -> None:
        """Called from main on real quit — persist final state."""
        self._settings.save_geometry(self.saveGeometry())
        self._settings.sync()
