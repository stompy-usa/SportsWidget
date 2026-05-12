# Sports Widget

Minimalist Windows desktop widget showing MLB / NBA / NFL / NHL games (today + tomorrow) from ESPN's public scoreboard API. Sits on the desktop behind other windows, resizable, with favorites and persistent window state.

## Requirements

- Windows 10/11
- Python 3.11 or newer on PATH

## Install

```
install.bat
```

Creates a local `.venv` and installs PySide6 + requests.

## Run

```
run.bat
```

The widget appears on the desktop (behind active windows) and starts populating within a couple of seconds. It refreshes every 60 seconds.

## Auto-start at login (optional)

```
install_startup.bat
```

Creates a shortcut in your Windows Startup folder. To disable, delete `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SportsWidget.lnk`.

## Usage

- **Move:** drag the header strip.
- **Resize:** drag the bottom-right corner.
- **Favorites:** right-click the widget (or use the tray icon) -> Favorites... Star any teams across the four leagues.
- **Filter:** click the star button in the header to toggle Favorites-only.
- **Lock:** right-click -> Lock (prevents accidental move/resize).
- **Hide / Show:** click the tray icon, or use its menu.
- **Quit:** right-click the tray icon -> Quit.

Window position, size, lock state, favorites, and filter setting are saved between launches in `%APPDATA%\SportsWidget\settings.ini`.

## Data source

Uses ESPN's public site API (no key required). If a league fails to fetch, its last-known data is kept and a small "stale" indicator is shown until the next successful refresh.
