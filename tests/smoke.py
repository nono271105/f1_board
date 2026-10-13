"""
Test de fumée hors écran : lance la vraie fenêtre avec des données synthétiques, parcourt
les 7 analyses, teste les erreurs et l'export, et enregistre des captures dans /tmp/f1_shots.

    python tests/smoke.py
"""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

import plots  # noqa: E402
import theme  # noqa: E402
from gui import MainWindow  # noqa: E402
from tests.fake import FakeService  # noqa: E402

OUT = Path("/tmp/f1_shots")
OUT.mkdir(exist_ok=True)


def pump(app, seconds=0.5, until=None, timeout=15):
    end = time.time() + (timeout if until else seconds)
    while time.time() < end:
        app.processEvents()
        if until and until():
            break
        time.sleep(0.01)
    app.processEvents()


def shot(win, name):
    win.grab().save(str(OUT / f"{name}.png"))


def main() -> int:
    app = QApplication(sys.argv)
    theme.load_fonts()
    app.setFont(theme.font(10.5))
    app.setStyleSheet(theme.STYLESHEET)
    win = MainWindow(lambda: FakeService(fail_codes=("FP1",)))
    win._settings.clear()
    win.resize(1440, 900)
    win.show()
    pump(app, until=lambda: win.sd is not None)
    assert win.sd is not None, "la session ne s'est pas chargée"
    assert len(win.sd.drivers) == 22
    print("session chargée :", win.sd.event.name, win.sd.code, len(win.sd.laps), "tours")

    for ch in plots.CHARTS:
        win._set_chart(ch)
        pump(app, 0.7)
        shown = win.view._stack.currentWidget() is win.view.glw
        print(f"{ch.key:13s} graphique affiché : {shown}")
        assert shown, f"{ch.key} : {win.view._msg_title.text()} / {win.view._msg_body.text()}"
        shot(win, f"1_{ch.key}")

    # survol : lecture au curseur
    win._set_chart(plots.BY_KEY["positions"])
    pump(app, 0.4)
    assert win.view._probe is not None
    html = win.view._probe(30.0)
    assert html and "Tour 30" in html
    print("lecture au survol ok :", html.split("<br>")[1])

    # sélection de pilotes
    win.strip.select_top(2)
    pump(app, 0.5)
    shot(win, "2_positions_top2")

    # qualifications : analyses de course désactivées
    win.seg._buttons["Q"].click()
    pump(app, until=lambda: win.sd is not None and win.sd.code == "Q")
    assert win.sd.code == "Q"
    assert not win.tab_buttons["positions"].isEnabled()
    assert win.tab_buttons["distribution"].isEnabled()
    print("qualifs : onglets de course grisés, graphique =", win.chart.key)
    pump(app, 0.5)
    shot(win, "3_quali")

    # session indisponible
    win.seg._buttons["FP1"].click()
    pump(app, until=lambda: win.view._stack.currentWidget() is win.view._msg, timeout=5)
    pump(app, 0.4)
    assert "indisponibles" in win.view._msg_title.text().lower()
    shot(win, "4_erreur")
    print("erreur de session affichée :", win.view._msg_title.text())

    # export (retour à la course)
    win.seg._buttons["R"].click()
    pump(app, until=lambda: win.sd is not None and win.sd.code == "R")
    win._set_chart(plots.BY_KEY["distribution"])
    pump(app, 0.5)
    for ext in ("png", "pdf", "svg"):
        p = OUT / f"export.{ext}"
        win.view.export(str(p))
        assert p.stat().st_size > 1000, ext
        print(f"export {ext} : {p.stat().st_size // 1024} Ko")

    # fenêtre à la taille minimale
    win.resize(1180, 720)
    pump(app, 0.6)
    shot(win, "5_taille_min")
    win._settings.clear()
    win.close()
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
