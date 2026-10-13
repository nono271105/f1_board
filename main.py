"""main.py : point d'entrée de F1 Board."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE = Path(__file__).parent


def _setup_logging() -> None:
    logs = BASE / "logs"
    logs.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    file = RotatingFileHandler(logs / "f1_board.log", maxBytes=512_000, backupCount=2, encoding="utf-8")
    file.setFormatter(fmt)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[file, console])
    for noisy in ("fastf1", "requests_cache", "urllib3", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def make_service():
    from data import Service
    return Service(cache_dir=BASE / "cache")


def main() -> int:
    _setup_logging()
    from PySide6.QtWidgets import QApplication

    import theme
    from gui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("F1 Board")
    app.setFont(theme.font(10.5))
    app.setStyleSheet(theme.STYLESHEET)

    window = MainWindow(make_service)     # FastF1 n'est importé qu'en arrière-plan
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
