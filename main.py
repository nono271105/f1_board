"""
main.py — Point d'entrée de l'application F1 Dashboard
"""

import sys
import logging
from pathlib import Path

# ── Configuration du cache FastF1 (avant tout appel fastf1) ───────────────────
import fastf1
_CACHE_DIR = Path(__file__).parent / "cache"
_CACHE_DIR.mkdir(exist_ok=True)
try:
    fastf1.Cache.enable_cache(str(_CACHE_DIR))
except Exception as exc:
    # Mode fallback si enable_cache a été appelé
    pass

# ── Backend Matplotlib Qt5 ────────────────────────────────────────────────────
import matplotlib
matplotlib.use("Qt5Agg")

# ── Logging ───────────────────────────────────────────────────────────────────
_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.INFO)
_console.setFormatter(_fmt)

_file = logging.FileHandler(_LOG_DIR / "f1_dashboard.log", encoding="utf-8")
_file.setLevel(logging.DEBUG)
_file.setFormatter(_fmt)

logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger().addHandler(_console)
logging.getLogger().addHandler(_file)

for _noisy in ("matplotlib", "matplotlib.font_manager", "fastf1", "urllib3", "requests"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

log = logging.getLogger("main")


def main() -> None:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication
    from gui import MainWindow

    # Support haute résolution (Retina / High-DPI)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    log.info("Démarrage de F1 Dashboard Analytics")
    app = QApplication(sys.argv)
    app.setApplicationName("F1 Dashboard")
    app.setApplicationDisplayName("F1 Analytics Dashboard")

    window = MainWindow()
    window.show()

    log.info("Interface F1 Dashboard affichée avec succès")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()