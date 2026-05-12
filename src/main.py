from __future__ import annotations

import logging
import sys
from pathlib import Path

# Make sibling modules importable when launched as `python src\main.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon  # noqa: E402

from settings_store import CONFIG_DIR, SettingsStore  # noqa: E402
from tray import SportsTray  # noqa: E402
from widget_window import WidgetWindow  # noqa: E402

LOG_PATH = CONFIG_DIR / "sportswidget.log"


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8")],
    )


def _load_stylesheet() -> str:
    qss_path = Path(__file__).resolve().parent / "ui" / "styles.qss"
    try:
        return qss_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def main() -> int:
    _configure_logging()
    log = logging.getLogger("main")
    log.info("Starting Sports Widget")

    app = QApplication(sys.argv)
    app.setApplicationName("SportsWidget")
    app.setOrganizationName("SportsWidget")
    app.setQuitOnLastWindowClosed(False)  # tray keeps app alive when window hidden
    app.setStyleSheet(_load_stylesheet())

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(
            None,
            "Sports Widget",
            "System tray is not available on this system. The widget will run, "
            "but you won't have a tray icon to manage it.",
        )

    settings = SettingsStore()
    window = WidgetWindow(settings)
    tray = SportsTray(window)
    tray.set_locked(window.is_locked())

    # Wire tray <-> window
    tray.show_requested.connect(window.show)
    tray.hide_requested.connect(window.hide)
    tray.refresh_requested.connect(window.refresh_now)
    tray.favorites_requested.connect(window._open_favorites_dialog)  # noqa: SLF001
    tray.toggle_lock_requested.connect(_toggle_lock_factory(window, tray))

    def on_quit() -> None:
        window.shutdown()
        app.quit()

    tray.quit_requested.connect(on_quit)
    app.aboutToQuit.connect(window.shutdown)

    tray.show()
    window.show()
    window.start()

    # Re-assert WindowStaysOnBottom after the window is mapped — some Windows
    # display drivers ignore the flag on first show until the window exists.
    QTimer.singleShot(200, window.lower)

    return app.exec()


def _toggle_lock_factory(window: WidgetWindow, tray: SportsTray):
    def _toggle() -> None:
        window.toggle_lock()
        tray.set_locked(window.is_locked())
    return _toggle


if __name__ == "__main__":
    sys.exit(main())
