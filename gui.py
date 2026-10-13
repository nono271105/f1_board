"""gui.py : fenêtre principale."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QSettings, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QProgressBar, QPushButton, QVBoxLayout, QWidget)

import plots
import theme
from data import DataUnavailable, SessionData, available_years
from widgets import ChartView, DriverStrip, GpList, Segmented

log = logging.getLogger(__name__)

SESSION_BUTTONS = ["R", "Q", "S", "SQ", "FP1", "FP2", "FP3"]


# ── Tâches en arrière-plan ───────────────────────────────────────────────────

class _Signals(QObject):
    ok = Signal(object)
    err = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn: Callable):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()
        self.setAutoDelete(False)          # la fenêtre garde la tâche vivante jusqu'au signal

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:           # noqa: BLE001 : remonté à l'interface
            self.signals.err.emit(exc)
        else:
            self.signals.ok.emit(result)


class Metric(QWidget):
    def __init__(self, caption: str, accent: Optional[str] = None, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        self._bar = QFrame()
        self._bar.setFixedWidth(3)
        h.addWidget(self._bar)
        v = QVBoxLayout()
        v.setSpacing(0)
        self._cap = QLabel(caption)
        self._cap.setObjectName("caption")
        self._val = QLabel("n/d")
        self._val.setObjectName("value")
        v.addWidget(self._cap)
        v.addWidget(self._val)
        h.addLayout(v)
        self.set("n/d", None)

    def set(self, text: str, accent: Optional[str], caption: Optional[str] = None,
            tip: str = "") -> None:
        if caption:
            self._cap.setText(caption)
        self._val.setText(text)
        self._val.setToolTip(tip)
        self._bar.setStyleSheet(f"background: {accent or theme.LINE};")


# ── Fenêtre principale ───────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, service_factory: Callable):
        super().__init__()
        self.setWindowTitle("F1 Board")
        self.setMinimumSize(1180, 720)

        self._factory = service_factory
        self._svc = None
        self._svc_lock = threading.Lock()
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(2)
        self._tasks: set[_Task] = set()
        self._busy = 0
        self._token = 0              # invalide les réponses d'une session déjà remplacée
        self._tel_token = 0

        self._settings = QSettings("f1board", "f1board")
        years = available_years()
        saved_year = int(self._settings.value("year", years[0]))
        self.year = saved_year if saved_year in years else years[0]
        self.code: str = str(self._settings.value("session", "R"))
        self.chart: plots.Chart = plots.BY_KEY.get(str(self._settings.value("chart", "")), plots.CHARTS[0])
        self.cur = None
        self.sd: Optional[SessionData] = None
        self._want_round = int(self._settings.value("round", 0))

        self._build(years)
        self._wire()
        geo = self._settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        else:
            self.resize(1440, 900)

        self._debounce_load = QTimer(self, singleShot=True, interval=220, timeout=self._load_session)
        self._debounce_sel = QTimer(self, singleShot=True, interval=120, timeout=self._render)
        QTimer.singleShot(0, self._load_schedule)

    # ── Construction ─────────────────────────────────────────────────────────

    def _build(self, years: list[int]) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QHBoxLayout()
        body.setSpacing(0)
        outer.addLayout(body, 1)

        # Panneau latéral
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(280)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(18, 18, 18, 14)
        sv.setSpacing(6)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        mark = QFrame()
        mark.setFixedSize(4, 22)
        mark.setStyleSheet(f"background: {theme.RED};")
        brand.addWidget(mark)
        name = QLabel("F1 Board")
        name.setObjectName("brand")
        brand.addWidget(name)
        brand.addStretch()
        sv.addLayout(brand)
        sv.addSpacing(14)

        sv.addWidget(self._caption("Saison"))
        self.year_box = QComboBox()
        self.year_box.addItems([str(y) for y in years])
        self.year_box.setCurrentText(str(self.year))
        sv.addWidget(self.year_box)
        sv.addSpacing(10)
        sv.addWidget(self._caption("Session"))
        self.seg = Segmented(SESSION_BUTTONS, columns=4)
        self.seg.set_current(self.code)
        sv.addWidget(self.seg)
        sv.addSpacing(10)
        sv.addWidget(self._caption("Grand Prix"))
        self.gp_list = GpList()
        sv.addWidget(self.gp_list, 1)
        body.addWidget(side)

        # Colonne principale
        main = QVBoxLayout()
        main.setSpacing(0)
        body.addLayout(main, 1)

        top = QFrame()
        top.setObjectName("topbar")
        top.setFixedHeight(96)
        th = QHBoxLayout(top)
        th.setContentsMargins(22, 12, 22, 12)
        th.setSpacing(30)
        tl = QVBoxLayout()
        tl.setSpacing(2)
        self.title = QLabel("F1 Board")
        self.title.setObjectName("h1")
        tl.addWidget(self.title)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("caption")
        tl.addWidget(self.subtitle)
        th.addLayout(tl, 1)
        self.m_lead = Metric("Vainqueur")
        self.m_fast = Metric("Meilleur tour")
        self.m_laps = Metric("Tours")
        self.m_temp = Metric("Piste / air")
        for m in (self.m_lead, self.m_fast, self.m_laps, self.m_temp):
            th.addWidget(m)
        main.addWidget(top)

        tabs = QFrame()
        tabs.setObjectName("tabbar")
        tb = QHBoxLayout(tabs)
        tb.setContentsMargins(10, 0, 10, 0)
        tb.setSpacing(0)
        self.tab_group = QButtonGroup(root)
        self.tab_buttons: dict[str, QPushButton] = {}
        for i, ch in enumerate(plots.CHARTS, 1):
            b = QPushButton(ch.label)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(f"Touche {i}")
            b.clicked.connect(lambda _=False, c=ch: self._set_chart(c))
            self.tab_group.addButton(b)
            self.tab_buttons[ch.key] = b
            tb.addWidget(b)
        tb.addStretch()
        main.addWidget(tabs)

        self.strip = DriverStrip()
        main.addWidget(self.strip)

        tools = QHBoxLayout()
        tools.setContentsMargins(20, 8, 20, 4)
        tools.setSpacing(6)
        self.hint = QLabel("")
        self.hint.setObjectName("hint")
        tools.addWidget(self.hint, 1)
        self.btn_pan = self._tool("Déplacer", checkable=True)
        self.btn_zoom = self._tool("Zoom", checkable=True)
        self.btn_pan.setChecked(True)
        mode = QButtonGroup(root)
        mode.addButton(self.btn_pan)
        mode.addButton(self.btn_zoom)
        self.btn_reset = self._tool("Réinitialiser")
        self.btn_export = self._tool("Exporter")
        for b in (self.btn_pan, self.btn_zoom, self.btn_reset, self.btn_export):
            tools.addWidget(b)
        main.addLayout(tools)

        self.view = ChartView()
        main.addWidget(self.view, 1)

        # Barre d'état
        status = QFrame()
        status.setObjectName("statusbar")
        status.setFixedHeight(28)
        sh = QHBoxLayout(status)
        sh.setContentsMargins(16, 0, 16, 0)
        self.status = QLabel("Prêt")
        self.status.setObjectName("caption")
        sh.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(140)
        self.progress.hide()
        sh.addWidget(self.progress)
        outer.addWidget(status)
        self.setCentralWidget(root)

        self.tab_buttons[self.chart.key].setChecked(True)
        self.hint.setText(self.chart.hint)

    @staticmethod
    def _caption(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("caption")
        return lbl

    @staticmethod
    def _tool(text: str, checkable: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("tool")
        b.setCheckable(checkable)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def _wire(self) -> None:
        self.year_box.currentTextChanged.connect(self._on_year)
        self.seg.changed.connect(self._on_session_clicked)
        self.gp_list.selected.connect(self._on_gp)
        self.strip.changed.connect(lambda: self._debounce_sel.start())
        self.btn_pan.clicked.connect(lambda: self.view.set_zoom_mode(False))
        self.btn_zoom.clicked.connect(lambda: self.view.set_zoom_mode(True))
        self.btn_reset.clicked.connect(self.view.reset)
        self.btn_export.clicked.connect(self._export)
        for i, ch in enumerate(plots.CHARTS, 1):
            QShortcut(QKeySequence(str(i)), self, activated=lambda c=ch: self._set_chart(c))
        QShortcut(QKeySequence.StandardKey.Refresh, self, activated=self._refresh)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._refresh)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self._export)

    # ── Tâches ───────────────────────────────────────────────────────────────

    def _service(self):
        with self._svc_lock:
            if self._svc is None:
                self._svc = self._factory()
            return self._svc

    def _submit(self, fn: Callable, ok: Callable, err: Callable) -> None:
        task = _Task(fn)
        self._tasks.add(task)
        self._set_busy(+1)

        def done(handler):
            def inner(arg):
                self._tasks.discard(task)
                self._set_busy(-1)
                handler(arg)
            return inner

        task.signals.ok.connect(done(ok))
        task.signals.err.connect(done(err))
        self._pool.start(task)

    def _set_busy(self, delta: int) -> None:
        self._busy = max(0, self._busy + delta)
        self.progress.setVisible(self._busy > 0)

    def _say(self, text: str) -> None:
        self.status.setText(text)

    # ── Calendrier ───────────────────────────────────────────────────────────

    def _load_schedule(self) -> None:
        year = self.year
        self._token += 1
        self.sd = None
        self.view.show_message(f"Calendrier {year}", "Chargement en cours", loading=True)
        self._say(f"Chargement du calendrier {year}")
        self._submit(lambda: self._service().schedule(year),
                     lambda ev, y=year: self._on_schedule(y, ev), self._on_schedule_error)

    def _on_schedule(self, year: int, events) -> None:
        if year != self.year:
            return
        done = [e for e in events if e.done]
        if not done:
            self.gp_list.set_events(events)
            self.view.show_message("Saison pas commencée", f"Aucune course n'a encore eu lieu en {year}.")
            self._say("Aucune course disputée")
            return
        wanted = next((e for e in done if e.round == self._want_round), done[-1])
        self.gp_list.set_events(events, select_round=wanted.round)
        self.cur = wanted
        self._apply_event_sessions()
        self._say(f"{len(events)} Grands Prix")
        self._load_session()

    def _on_schedule_error(self, exc: Exception) -> None:
        log.warning("Calendrier : %s", exc)
        msg = str(exc) if isinstance(exc, DataUnavailable) else f"Erreur inattendue : {exc}"
        self.view.show_message("Calendrier indisponible", msg)
        self._say("Calendrier indisponible")

    def _apply_event_sessions(self) -> None:
        self.seg.set_available(set(self.cur.sessions))
        if self.code not in self.cur.sessions:
            self.code = "R" if "R" in self.cur.sessions else self.cur.sessions[-1]
        self.seg.set_current(self.code)

    # ── Sélections ───────────────────────────────────────────────────────────

    def _on_year(self, text: str) -> None:
        self.year = int(text)
        self._want_round = 0
        self.cur = None
        self._load_schedule()

    def _on_gp(self, ev) -> None:
        self.cur = ev
        self._want_round = ev.round
        self._apply_event_sessions()
        self._debounce_load.start()

    def _on_session_clicked(self, code: str) -> None:
        self.code = code
        self._debounce_load.start()

    def _set_chart(self, chart: plots.Chart) -> None:
        if not chart.available(self.sd):
            self._say(f"« {chart.label} » n'existe que pour les courses et les sprints")
            self.tab_buttons[self.chart.key].setChecked(True)
            return
        self.chart = chart
        self.tab_buttons[chart.key].setChecked(True)
        self.hint.setText(chart.hint)
        self._render()

    # ── Session ──────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        if self.cur is not None and self._svc is not None:
            self._svc.drop(self.year, self.cur, self.code)
            self._load_session()

    def _load_session(self) -> None:
        if self.cur is None:
            return
        ev, code, year = self.cur, self.code, self.year
        self._token += 1
        token = self._token
        self._update_header(ev, code)
        self.view.show_message(f"{ev.short} {year}", "Chargement des tours et de la météo. "
                               "Le premier chargement d'une session peut prendre une minute.",
                               loading=True)
        self._say(f"Chargement de {ev.short} {year}")
        self._submit(lambda: self._service().session(year, ev, code),
                     lambda sd, t=token: self._on_session(sd, t),
                     lambda exc, t=token: self._on_session_error(exc, t))

    def _on_session(self, sd: SessionData, token: int) -> None:
        if token != self._token:
            return
        self.sd = sd
        keep = [c for c in self.strip.selected() if c in sd.codes]
        self.strip.set_drivers(sd.drivers, keep or sd.codes[:5])
        self._update_metrics(sd)
        for ch in plots.CHARTS:
            self.tab_buttons[ch.key].setEnabled(ch.available(sd))
        if not self.chart.available(sd):
            self.chart = plots.CHARTS[0]
            self.tab_buttons[self.chart.key].setChecked(True)
            self.hint.setText(self.chart.hint)
        self._say(f"{sd.event.short} {sd.year}, {sd.label}")
        self._render()

    def _on_session_error(self, exc: Exception, token: int) -> None:
        if token != self._token:
            return
        log.warning("Session : %s", exc)
        self.sd = None
        msg = str(exc) if isinstance(exc, DataUnavailable) else f"Erreur inattendue : {exc}"
        self.view.show_message("Données indisponibles", msg)
        self._clear_metrics()
        self._say("Données indisponibles")

    # ── En-tête ──────────────────────────────────────────────────────────────

    def _update_header(self, ev, code: str) -> None:
        from data import SESSION_LABELS
        self.title.setText(ev.name)
        self.subtitle.setText(f"Manche {ev.round}     {ev.location}, {ev.country}     "
                              f"{ev.date:%d/%m/%Y}     {SESSION_LABELS.get(code, code)}")

    def _clear_metrics(self) -> None:
        for m in (self.m_lead, self.m_fast, self.m_laps, self.m_temp):
            m.set("n/d", None)

    def _update_metrics(self, sd: SessionData) -> None:
        m = sd.metrics
        self.m_lead.set(m["lead_name"], m["lead_color"], caption=m["lead_label"], tip=m["lead_team"])
        self.m_fast.set(f"{m['fastest_code']}  {m['fastest_time']}", theme.PURPLE)
        self.m_laps.set(str(m["laps"]) if m["laps"] else "n/d", None)
        if m["track"] is not None and m["air"] is not None:
            rain = "  pluie" if m["rain"] else ""
            self.m_temp.set(f"{m['track']:.0f} / {m['air']:.0f} °C{rain}", None)
        else:
            self.m_temp.set("n/d", None)

    # ── Rendu ────────────────────────────────────────────────────────────────

    def _render(self) -> None:
        sd = self.sd
        if sd is None:
            return
        ch = self.chart
        self.strip.set_active(ch.drivers != "none")
        sel = self.strip.selected()

        if ch.telemetry:
            codes = plots.telemetry_codes(sel, sd)
            if sd.has_telemetry(codes):
                self._draw(ch, sd, sel, {c: sd._tel[c] for c in codes})
                return
            self._tel_token += 1
            token = self._tel_token
            self.view.show_message("Télémétrie", "Chargement des données du meilleur tour",
                                   loading=True)
            self._say("Chargement de la télémétrie")
            self._submit(lambda: self._service().telemetry(sd, codes),
                         lambda tel, t=token: self._on_telemetry(sd, sel, tel, t),
                         lambda exc, t=token: self._on_telemetry_error(exc, t))
            return
        self._draw(ch, sd, sel, None)

    def _on_telemetry(self, sd, sel, tel, token: int) -> None:
        if token != self._tel_token or sd is not self.sd or not self.chart.telemetry:
            return
        self._draw(self.chart, sd, sel, tel)

    def _on_telemetry_error(self, exc: Exception, token: int) -> None:
        if token != self._tel_token or not self.chart.telemetry:
            return
        msg = str(exc) if isinstance(exc, DataUnavailable) else f"Erreur inattendue : {exc}"
        self.view.show_message("Télémétrie indisponible", msg)
        self._say("Télémétrie indisponible")

    def _draw(self, ch: plots.Chart, sd: SessionData, sel, tel) -> None:
        try:
            plots.render(ch, self.view, sd, sel, tel)
            self._say(f"{sd.event.short} {sd.year}, {sd.label}")
        except plots.Notice as n:
            self.view.show_message(n.title, n.detail)
            self._say(n.title)
        except Exception as exc:                       # noqa: BLE001
            log.exception("Rendu %s", ch.key)
            self.view.show_message("Impossible de tracer ce graphique", str(exc))
            self._say("Erreur de rendu")

    # ── Export ───────────────────────────────────────────────────────────────

    def _export(self) -> None:
        if self.sd is None:
            self._say("Rien à exporter : charge d'abord une session")
            return
        start = Path(str(self._settings.value("export_dir", str(Path.home()))))
        stem = f"f1_{self.sd.year}_{self.sd.event.short}_{self.sd.code}_{self.chart.key}".replace(" ", "_")
        path, flt = QFileDialog.getSaveFileName(
            self, "Exporter le graphique", str(start / f"{stem}.png"),
            "Image PNG (*.png);;Document PDF (*.pdf);;Vectoriel SVG (*.svg)")
        if not path:
            return
        if Path(path).suffix.lower() not in (".png", ".pdf", ".svg"):
            path += ".pdf" if "PDF" in flt else ".svg" if "SVG" in flt else ".png"
        try:
            self.view.export(path)
        except Exception as exc:                       # noqa: BLE001
            log.exception("Export")
            self._say(f"Export impossible : {exc}")
            return
        self._settings.setValue("export_dir", str(Path(path).parent))
        self._say(f"Exporté : {path}")

    # ── Fermeture ────────────────────────────────────────────────────────────

    def closeEvent(self, e) -> None:
        s = self._settings
        s.setValue("geometry", self.saveGeometry())
        s.setValue("year", self.year)
        s.setValue("session", self.code)
        s.setValue("chart", self.chart.key)
        if self.cur is not None:
            s.setValue("round", self.cur.round)
        self._pool.waitForDone(1500)
        super().closeEvent(e)
