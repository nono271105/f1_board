"""
F1 Dashboard — Entry point
"""

import sys
import logging
from pathlib import Path

# ── FastF1 cache (doit être fait avant tout import fastf1) ──────────────────
import fastf1
_CACHE_DIR = Path(__file__).parent / "cache"
_CACHE_DIR.mkdir(exist_ok=True)
fastf1.Cache.enable_cache(str(_CACHE_DIR))

# ── Matplotlib backend Qt5 ──────────────────────────────────────────────────
import matplotlib
matplotlib.use("Qt5Agg")

# ── Logging ─────────────────────────────────────────────────────────────────
_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

# Console : INFO uniquement (pas de DEBUG)
_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.INFO)
_console.setFormatter(_fmt)

# Fichier : tout en DEBUG pour le diagnostic
_file = logging.FileHandler(_LOG_DIR / "f1_dashboard.log")
_file.setLevel(logging.DEBUG)
_file.setFormatter(_fmt)

# Logger racine
logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger().addHandler(_console)
logging.getLogger().addHandler(_file)

# Silencer les loggers externes verbeux
for _noisy in ("matplotlib", "matplotlib.font_manager", "fastf1", "urllib3", "requests"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
log = logging.getLogger("main")


def main() -> None:
    from PyQt5.QtWidgets import QApplication
    from gui import MainWindow

    log.info("Démarrage F1 Dashboard")
    app = QApplication(sys.argv)
    app.setApplicationName("F1 Dashboard")

    window = MainWindow()
    window.show()

    log.info("Fenêtre affichée")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()