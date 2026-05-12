from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logo_cache import LOGO_HEIGHT_PX, LogoCache
from models import Game, GameDetail, MLBDetail, NBADetail, NFLDetail, NHLDetail
from ui.section_header import apply_text_shadow
from urls import espn_game_url


class DetailPanel(QWidget):
    """Inline panel that shows live, sport-specific game detail."""

    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailPanel")
        self.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        # ---- Header row: matchup + close ----
        self._header_row = QWidget(self)
        header_layout = QHBoxLayout(self._header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self._away_logo = QLabel()
        self._away_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_text_shadow(self._away_logo)
        header_layout.addWidget(self._away_logo)

        self._away_label = QLabel("")
        self._away_label.setObjectName("DetailHeaderTeam")
        apply_text_shadow(self._away_label)
        header_layout.addWidget(self._away_label)

        self._score_label = QLabel("")
        self._score_label.setObjectName("DetailHeaderScore")
        apply_text_shadow(self._score_label)
        header_layout.addWidget(self._score_label)

        self._home_label = QLabel("")
        self._home_label.setObjectName("DetailHeaderTeam")
        apply_text_shadow(self._home_label)
        header_layout.addWidget(self._home_label)

        self._home_logo = QLabel()
        self._home_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_text_shadow(self._home_logo)
        header_layout.addWidget(self._home_logo)

        header_layout.addStretch(1)

        self._close_btn = QPushButton("×", self._header_row)
        self._close_btn.setObjectName("DetailCloseButton")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setFlat(True)
        self._close_btn.setToolTip("Close")
        self._close_btn.clicked.connect(self.closed.emit)
        header_layout.addWidget(self._close_btn)

        outer.addWidget(self._header_row)

        # ---- Body container: replaced on each set_detail / show_for ----
        self._body_container = QWidget(self)
        self._body_layout = QVBoxLayout(self._body_container)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(2)
        outer.addWidget(self._body_container)

        # ---- Footer: Open on ESPN link ----
        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.addStretch(1)
        self._open_espn_btn = QPushButton("Open on ESPN", self)
        self._open_espn_btn.setObjectName("DetailEspnButton")
        self._open_espn_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_espn_btn.setFlat(True)
        self._open_espn_btn.clicked.connect(self._open_on_espn)
        footer_row.addWidget(self._open_espn_btn)
        outer.addLayout(footer_row)

        self._current_url = ""
        self._current_event_id = ""

    # ---------- Public API ----------

    def show_for(self, game: Game) -> None:
        """Render the header skeleton immediately while the detail fetch is in flight."""
        self._current_event_id = game.event_id
        self._current_url = espn_game_url(game.league, game.event_id)

        self._set_team_pixmap(self._away_logo, game.league, game.away_team_id)
        self._set_team_pixmap(self._home_logo, game.league, game.home_team_id)
        self._away_label.setText(game.away_abbr)
        self._home_label.setText(game.home_abbr)
        self._score_label.setText(f"{game.away_score} - {game.home_score}")

        self._clear_body()
        loading = QLabel("Loading details...")
        loading.setObjectName("DetailLine")
        apply_text_shadow(loading)
        self._body_layout.addWidget(loading)

        self.setVisible(True)

    def set_detail(self, detail: GameDetail) -> None:
        """Replace body with sport-specific content. Ignored if stale (event id mismatch)."""
        if not detail.event_id or detail.event_id != self._current_event_id:
            return

        # Update score if ESPN gave us a fresher value
        if detail.away_score or detail.home_score:
            self._score_label.setText(f"{detail.away_score or '0'} - {detail.home_score or '0'}")

        self._clear_body()

        if detail.error and not any((detail.mlb, detail.nba, detail.nfl, detail.nhl)):
            msg = QLabel(f"Couldn't load details: {detail.error}")
            msg.setObjectName("DetailLastPlay")
            msg.setWordWrap(True)
            apply_text_shadow(msg)
            self._body_layout.addWidget(msg)
            return

        if detail.mlb is not None:
            if detail.state == "in":
                _render_mlb_live(self._body_layout, detail.mlb)
            else:
                _render_mlb_pre(self._body_layout, detail, detail.mlb)
        elif detail.nba is not None:
            if detail.state == "in":
                _render_nba_live(self._body_layout, detail.nba, detail)
            else:
                _render_nba_pre(self._body_layout, detail, detail.nba)
        elif detail.nfl is not None:
            if detail.state == "in":
                _render_nfl_live(self._body_layout, detail.nfl)
            else:
                _render_nfl_pre(self._body_layout, detail, detail.nfl)
        elif detail.nhl is not None:
            if detail.state == "in":
                _render_nhl_live(self._body_layout, detail.nhl, detail)
            else:
                _render_nhl_pre(self._body_layout, detail, detail.nhl)
        else:
            msg = QLabel("No detail data available yet.")
            msg.setObjectName("DetailLine")
            apply_text_shadow(msg)
            self._body_layout.addWidget(msg)

    def clear(self) -> None:
        self._current_event_id = ""
        self._current_url = ""
        self._clear_body()
        self.setVisible(False)

    def current_event_id(self) -> str:
        return self._current_event_id

    # ---------- Internal ----------

    def _clear_body(self) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _open_on_espn(self) -> None:
        if self._current_url:
            QDesktopServices.openUrl(QUrl(self._current_url))

    @staticmethod
    def _set_team_pixmap(label: QLabel, league: str, team_id: str) -> None:
        pix = LogoCache.instance().get(league, team_id)
        if pix is not None:
            label.setPixmap(pix)
            label.setText("")
            label.setFixedHeight(LOGO_HEIGHT_PX + 2)
        else:
            label.clear()


# ---------- Sport-specific renderers ----------

def _add_line(layout: QVBoxLayout, label: str, value: str) -> None:
    if not value:
        return
    row = QWidget()
    rl = QHBoxLayout(row)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.setSpacing(6)
    lbl = QLabel(label)
    lbl.setObjectName("DetailLabel")
    apply_text_shadow(lbl)
    rl.addWidget(lbl)
    val = QLabel(value)
    val.setObjectName("DetailLine")
    val.setWordWrap(True)
    apply_text_shadow(val)
    rl.addWidget(val, stretch=1)
    layout.addWidget(row)


def _add_last_play(layout: QVBoxLayout, text: str) -> None:
    if not text:
        return
    lp = QLabel(text)
    lp.setObjectName("DetailLastPlay")
    lp.setWordWrap(True)
    apply_text_shadow(lp)
    layout.addWidget(lp)


def _render_mlb_live(layout: QVBoxLayout, m: MLBDetail) -> None:
    if m.inning:
        _add_line(layout, "Inning:", m.inning)

    # Bases diamond
    diamond = QWidget()
    grid = QGridLayout(diamond)
    grid.setContentsMargins(0, 2, 0, 2)
    grid.setHorizontalSpacing(2)
    grid.setVerticalSpacing(2)

    def base_dot(occupied: bool) -> QLabel:
        d = QLabel("")
        d.setObjectName("BaseDot")
        d.setProperty("occupied", "true" if occupied else "false")
        d.setFixedSize(10, 10)
        return d

    # 2nd top center, 3rd left middle, 1st right middle
    grid.addWidget(base_dot(m.on_second), 0, 1)
    grid.addWidget(base_dot(m.on_third), 1, 0)
    grid.addWidget(base_dot(m.on_first), 1, 2)

    bases_row = QWidget()
    bl = QHBoxLayout(bases_row)
    bl.setContentsMargins(0, 0, 0, 0)
    bl.setSpacing(8)
    bases_label = QLabel("Bases:")
    bases_label.setObjectName("DetailLabel")
    apply_text_shadow(bases_label)
    bl.addWidget(bases_label)
    bl.addWidget(diamond)
    bl.addStretch(1)
    count_text = f"{m.balls}-{m.strikes} · {m.outs} out{'s' if m.outs != 1 else ''}"
    count_lbl = QLabel(count_text)
    count_lbl.setObjectName("DetailLine")
    apply_text_shadow(count_lbl)
    bl.addWidget(count_lbl)
    layout.addWidget(bases_row)

    if m.pitcher_name:
        pitcher_text = m.pitcher_name + (f"  ({m.pitcher_line})" if m.pitcher_line else "")
        _add_line(layout, "Pitcher:", pitcher_text)
    if m.batter_name:
        batter_text = m.batter_name + (f"  ({m.batter_line})" if m.batter_line else "")
        _add_line(layout, "Batter:", batter_text)
    _add_last_play(layout, m.last_play)


def _render_nba_live(layout: QVBoxLayout, n: NBADetail, detail: GameDetail) -> None:
    if n.period or n.clock:
        _add_line(layout, "Period:", f"{n.period}  {n.clock}".strip())
    if n.away_leaders or n.home_leaders:
        _add_leaders_grid(layout, detail.away_abbr, n.away_leaders, detail.home_abbr, n.home_leaders)
    _add_last_play(layout, n.last_play)


def _render_nfl_live(layout: QVBoxLayout, n: NFLDetail) -> None:
    if n.period or n.clock:
        _add_line(layout, "Period:", f"{n.period}  {n.clock}".strip())
    if n.possession_abbr:
        _add_line(layout, "Possession:", n.possession_abbr)
    if n.down_distance:
        _add_line(layout, "Down:", n.down_distance)
    if n.yard_line:
        _add_line(layout, "At:", n.yard_line)
    _add_last_play(layout, n.last_play)


def _render_nhl_live(layout: QVBoxLayout, n: NHLDetail, detail: GameDetail) -> None:
    if n.period or n.clock:
        _add_line(layout, "Period:", f"{n.period}  {n.clock}".strip())
    if n.away_shots or n.home_shots:
        _add_line(layout, "Shots:", f"{detail.away_abbr} {n.away_shots}  ·  {detail.home_abbr} {n.home_shots}")
    if n.power_play:
        _add_line(layout, "PP:", n.power_play)
    if n.away_leaders or n.home_leaders:
        _add_leaders_grid(layout, detail.away_abbr, n.away_leaders, detail.home_abbr, n.home_leaders)
    _add_last_play(layout, n.last_play)


def _render_mlb_pre(layout: QVBoxLayout, detail: GameDetail, m: MLBDetail) -> None:
    _add_record_row(layout, detail, m.away_record, m.home_record)

    # Starting pitchers row (blank slot if not announced)
    pitchers = QWidget()
    pg = QGridLayout(pitchers)
    pg.setContentsMargins(0, 2, 0, 2)
    pg.setHorizontalSpacing(12)
    pg.setVerticalSpacing(2)
    title = QLabel("Starting Pitchers")
    title.setObjectName("DetailLabel")
    apply_text_shadow(title)
    pg.addWidget(title, 0, 0, 1, 2)

    away_sp = QLabel(_label_value(detail.away_abbr or "Away", m.away_probable_pitcher or "TBD"))
    away_sp.setObjectName("DetailLine")
    apply_text_shadow(away_sp)
    home_sp = QLabel(_label_value(detail.home_abbr or "Home", m.home_probable_pitcher or "TBD"))
    home_sp.setObjectName("DetailLine")
    apply_text_shadow(home_sp)
    pg.addWidget(away_sp, 1, 0)
    pg.addWidget(home_sp, 1, 1)
    layout.addWidget(pitchers)

    # Lineups (two columns)
    if m.away_lineup or m.home_lineup:
        _add_two_column_list(
            layout,
            title="Lineups",
            left_header=detail.away_abbr or "Away",
            left_rows=[f"{pos}  {name}" if pos else name for pos, name in m.away_lineup],
            right_header=detail.home_abbr or "Home",
            right_rows=[f"{pos}  {name}" if pos else name for pos, name in m.home_lineup],
            empty_placeholder="Lineup not yet announced",
        )
    else:
        empty = QLabel("Lineups not yet announced.")
        empty.setObjectName("DetailLastPlay")
        apply_text_shadow(empty)
        layout.addWidget(empty)


def _render_nba_pre(layout: QVBoxLayout, detail: GameDetail, n: NBADetail) -> None:
    _add_record_row(layout, detail, n.away_record, n.home_record)
    # NBA pre-game: show season top leaders (already extracted) as a teaser
    if n.away_leaders or n.home_leaders:
        _add_leaders_grid(
            layout,
            detail.away_abbr,
            n.away_leaders,
            detail.home_abbr,
            n.home_leaders,
        )


def _render_nfl_pre(layout: QVBoxLayout, detail: GameDetail, n: NFLDetail) -> None:
    _add_record_row(layout, detail, n.away_record, n.home_record)


def _render_nhl_pre(layout: QVBoxLayout, detail: GameDetail, n: NHLDetail) -> None:
    _add_record_row(layout, detail, n.away_record, n.home_record)

    # Starting goalies (blank if not announced)
    goalies = QWidget()
    gg = QGridLayout(goalies)
    gg.setContentsMargins(0, 2, 0, 2)
    gg.setHorizontalSpacing(12)
    gg.setVerticalSpacing(2)
    title = QLabel("Starting Goalies")
    title.setObjectName("DetailLabel")
    apply_text_shadow(title)
    gg.addWidget(title, 0, 0, 1, 2)

    away_g = QLabel(_label_value(detail.away_abbr or "Away", n.away_goalie or "TBD"))
    away_g.setObjectName("DetailLine")
    apply_text_shadow(away_g)
    home_g = QLabel(_label_value(detail.home_abbr or "Home", n.home_goalie or "TBD"))
    home_g.setObjectName("DetailLine")
    apply_text_shadow(home_g)
    gg.addWidget(away_g, 1, 0)
    gg.addWidget(home_g, 1, 1)
    layout.addWidget(goalies)

    # Season leaders as a teaser
    if n.away_leaders or n.home_leaders:
        _add_leaders_grid(
            layout,
            detail.away_abbr,
            n.away_leaders,
            detail.home_abbr,
            n.home_leaders,
        )


def _label_value(label: str, value: str) -> str:
    return f"{label}:  {value}" if label else value


def _add_record_row(layout: QVBoxLayout, detail: GameDetail, away_rec: str, home_rec: str) -> None:
    if not (away_rec or home_rec):
        return
    row = QWidget()
    rl = QHBoxLayout(row)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.setSpacing(12)
    if away_rec:
        a = QLabel(f"{detail.away_abbr or 'Away'}  {away_rec}")
        a.setObjectName("DetailLine")
        apply_text_shadow(a)
        rl.addWidget(a)
    rl.addStretch(1)
    if home_rec:
        h = QLabel(f"{detail.home_abbr or 'Home'}  {home_rec}")
        h.setObjectName("DetailLine")
        apply_text_shadow(h)
        rl.addWidget(h)
    layout.addWidget(row)


def _add_two_column_list(
    layout: QVBoxLayout,
    *,
    title: str,
    left_header: str,
    left_rows: list[str],
    right_header: str,
    right_rows: list[str],
    empty_placeholder: str,
) -> None:
    container = QWidget()
    g = QGridLayout(container)
    g.setContentsMargins(0, 2, 0, 2)
    g.setHorizontalSpacing(12)
    g.setVerticalSpacing(2)

    if title:
        title_lbl = QLabel(title)
        title_lbl.setObjectName("DetailLabel")
        apply_text_shadow(title_lbl)
        g.addWidget(title_lbl, 0, 0, 1, 2)

    left_hdr = QLabel(left_header)
    left_hdr.setObjectName("DetailLabel")
    apply_text_shadow(left_hdr)
    right_hdr = QLabel(right_header)
    right_hdr.setObjectName("DetailLabel")
    apply_text_shadow(right_hdr)
    g.addWidget(left_hdr, 1, 0)
    g.addWidget(right_hdr, 1, 1)

    rows = max(len(left_rows), len(right_rows))
    if rows == 0:
        ph = QLabel(empty_placeholder)
        ph.setObjectName("DetailLastPlay")
        apply_text_shadow(ph)
        g.addWidget(ph, 2, 0, 1, 2)
    else:
        for i in range(rows):
            if i < len(left_rows):
                lbl = QLabel(left_rows[i])
                lbl.setObjectName("DetailLine")
                apply_text_shadow(lbl)
                g.addWidget(lbl, i + 2, 0)
            if i < len(right_rows):
                lbl = QLabel(right_rows[i])
                lbl.setObjectName("DetailLine")
                apply_text_shadow(lbl)
                g.addWidget(lbl, i + 2, 1)
    layout.addWidget(container)


def _add_leaders_grid(
    layout: QVBoxLayout,
    away_abbr: str,
    away: list[tuple[str, str]],
    home_abbr: str,
    home: list[tuple[str, str]],
) -> None:
    if not away and not home:
        return
    container = QWidget()
    g = QGridLayout(container)
    g.setContentsMargins(0, 2, 0, 2)
    g.setHorizontalSpacing(12)
    g.setVerticalSpacing(2)

    away_hdr = QLabel(away_abbr or "Away")
    away_hdr.setObjectName("DetailLabel")
    apply_text_shadow(away_hdr)
    home_hdr = QLabel(home_abbr or "Home")
    home_hdr.setObjectName("DetailLabel")
    apply_text_shadow(home_hdr)
    g.addWidget(away_hdr, 0, 0)
    g.addWidget(home_hdr, 0, 1)

    rows = max(len(away), len(home))
    for i in range(rows):
        a = away[i] if i < len(away) else None
        h = home[i] if i < len(home) else None
        if a:
            lbl = QLabel(f"{a[0]}  {a[1]}")
            lbl.setObjectName("DetailLine")
            apply_text_shadow(lbl)
            g.addWidget(lbl, i + 1, 0)
        if h:
            lbl = QLabel(f"{h[0]}  {h[1]}")
            lbl.setObjectName("DetailLine")
            apply_text_shadow(lbl)
            g.addWidget(lbl, i + 1, 1)
    layout.addWidget(container)
