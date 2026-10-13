"""
plots.py : les sept analyses, dessinées avec pyqtgraph.

Chaque analyse est une fonction render(view, sd, sel, tel) qui lève Notice si les données
ne permettent pas de la tracer (le message est alors affiché à la place du graphique).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainterPath
from PySide6.QtWidgets import QGraphicsPathItem

import theme
from data import SessionData, TelemetryLap, fmt_time
from widgets import ChartView

pg.setConfigOptions(antialias=True, background=theme.BG, foreground=theme.MUTED)


class Notice(Exception):
    def __init__(self, title: str, detail: str = ""):
        super().__init__(title)
        self.title, self.detail = title, detail


# ── Outils communs ───────────────────────────────────────────────────────────

class TimeAxis(pg.AxisItem):
    """Axe en secondes affiché m:ss.d"""

    def tickStrings(self, values, scale, spacing):
        dec = 1 if spacing >= 0.1 else 2
        out = []
        for v in values:
            m, s = divmod(v, 60)
            out.append(f"{int(m)}:{s:0{3 + dec}.{dec}f}")
        return out


def _qcolor(hex_color: str, alpha: int = 255) -> QColor:
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c


def _pen(driver, width: float = 2.0, alpha: int = 255):
    return pg.mkPen(_qcolor(driver.color, alpha), width=width,
                    style=Qt.PenStyle.DashLine if driver.dashed else Qt.PenStyle.SolidLine)


def new_plot(view: ChartView, row: int, x_label: str = "", y_label: str = "", grid: str = "xy",
             time_x: bool = False, time_y: bool = False, vline: bool = False) -> pg.PlotItem:
    axes = {}
    if time_y:
        axes["left"] = TimeAxis("left")
    if time_x:
        axes["bottom"] = TimeAxis("bottom")
    plot = view.glw.ci.addPlot(row=row, col=0, axisItems=axes)
    tick_font = theme.font(10)
    for name in ("left", "bottom"):
        ax = plot.getAxis(name)
        ax.setPen(pg.mkPen(theme.LINE))
        ax.setTextPen(pg.mkPen(theme.MUTED))
        ax.setStyle(tickFont=tick_font, tickTextOffset=8)
        ax.enableAutoSIPrefix(False)
    label_style = {"color": theme.MUTED, "font-size": "11pt"}
    if x_label:
        plot.setLabel("bottom", x_label, **label_style)
    if y_label:
        plot.setLabel("left", y_label, **label_style)
    plot.showGrid(x="x" in grid, y="y" in grid, alpha=0.8)
    plot.getViewBox().setDefaultPadding(0.04)
    view.register(plot, vline=vline)
    return plot


def _legend(plot: pg.PlotItem):
    return plot.addLegend(offset=(-14, 10), labelTextColor=theme.TEXT, labelTextSize="10pt",
                          brush=pg.mkBrush(_qcolor(theme.PANEL, 235)), pen=pg.mkPen(theme.LINE))


def _head(view: ChartView, sd: SessionData, title: str, extra: str = "",
          legend: Optional[list[tuple[str, str]]] = None) -> None:
    sub = f"{sd.event.short} {sd.year}, {sd.label}"
    text = f"{sub}. {extra}" if extra else sub
    if legend:
        text += "&nbsp;" * 6 + "&nbsp;&nbsp;".join(
            f"<span style='color:{c}'>&#9632;</span>&nbsp;{label}" for c, label in legend)
    view.add_title(title, text)


def _compound_legend(present) -> list[tuple[str, str]]:
    return [theme.COMPOUNDS[c] for c in theme.COMPOUNDS if c in set(present)]


def pick(sel: list[str], sd: SessionData, n: int) -> list[str]:
    """Sélection de l'utilisateur, sinon les n premiers du classement."""
    return list(sel) if sel else sd.codes[:n]


def clean_laps(sd: SessionData, codes: Optional[list[str]], thr: float = 1.07) -> pd.DataFrame:
    """Tours représentatifs : sans arrêt au stand, non annulés, à moins de 107 % du meilleur."""
    L = sd.laps
    ok = L["laptime_s"].notna() & ~L["pit"] & ~L["deleted"]
    if not ok.any():
        return L.iloc[0:0]
    ok &= L["laptime_s"] <= L.loc[ok, "laptime_s"].min() * thr
    if codes is not None:
        ok &= L["driver"].isin(codes)
    return L[ok]


def _short_team(name: str) -> str:
    for suffix in (" F1 Team", " Racing"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _need(df: pd.DataFrame, title: str, detail: str) -> None:
    if df.empty:
        raise Notice(title, detail)


# ── 1. Distribution des temps au tour ────────────────────────────────────────

def _kde(t: np.ndarray, n: int = 90):
    lo, hi = float(t.min()), float(t.max())
    pad = max((hi - lo) * 0.12, 0.25)
    ys = np.linspace(lo - pad, hi + pad, n)
    bw = max(1.06 * float(t.std(ddof=1)) * len(t) ** -0.2, 0.06)
    d = np.exp(-0.5 * ((ys[:, None] - t[None, :]) / bw) ** 2).sum(axis=1)
    return ys, d / d.max()


def distribution(view: ChartView, sd: SessionData, sel, tel) -> None:
    codes = pick(sel, sd, 10)
    laps = clean_laps(sd, codes)
    _need(laps, "Pas assez de tours", "Aucun tour représentatif pour les pilotes sélectionnés.")
    present = [c for c in codes if c in set(laps["driver"])]

    view.begin()
    _head(view, sd, "Distribution des temps au tour", "Un point par tour, médiane en blanc.",
          _compound_legend(laps.loc[laps["driver"].isin(present), "compound"]))
    plot = new_plot(view, 2, y_label="Temps au tour", grid="y", time_y=True)
    plot.setXRange(-0.7, len(present) - 0.3, padding=0)
    y_lo, y_hi = float("inf"), float("-inf")

    rng = np.random.default_rng(7)
    brushes = {k: pg.mkBrush(_qcolor(v[0], 235)) for k, v in theme.COMPOUNDS.items()}
    med_x, med_y = [], []
    for i, code in enumerate(present):
        drv = sd.driver(code)
        g = laps[laps["driver"] == code]
        t = g["laptime_s"].to_numpy()
        if len(t) >= 4:
            ys, d = _kde(t)
            y_lo, y_hi = min(y_lo, ys[0]), max(y_hi, ys[-1])
            w = 0.42 * d
            path = QPainterPath()
            path.moveTo(i + w[0], ys[0])
            for x, y in zip(i + w[1:], ys[1:]):
                path.lineTo(x, y)
            for x, y in zip(i - w[::-1], ys[::-1]):
                path.lineTo(x, y)
            path.closeSubpath()
            item = QGraphicsPathItem(path)
            item.setPen(pg.mkPen(_qcolor(drv.color, 210), width=1))
            item.setBrush(pg.mkBrush(_qcolor(drv.color, 70)))
            item.setZValue(1)
            plot.addItem(item, ignoreBounds=True)
        med_x += [i - 0.3, i + 0.3]
        med_y += [float(np.median(t))] * 2
        comp = g["compound"].tolist()
        sc = pg.ScatterPlotItem(x=i + rng.uniform(-0.2, 0.2, len(t)), y=t, size=5,
                                pen=pg.mkPen(None), brush=[brushes.get(c, brushes["UNKNOWN"]) for c in comp])
        sc.setZValue(3)
        plot.addItem(sc)
    plot.addItem(pg.PlotCurveItem(med_x, med_y, connect="pairs", pen=pg.mkPen(theme.TEXT, width=2.5)))
    if np.isfinite(y_lo):
        plot.setYRange(y_lo, y_hi, padding=0.02)
    plot.getAxis("bottom").setTicks([[(i, c) for i, c in enumerate(present)]])
    plot.getAxis("bottom").setStyle(tickFont=theme.font(11, theme.QFont.Weight.DemiBold))


# ── 2. Évolution des positions ───────────────────────────────────────────────

def positions(view: ChartView, sd: SessionData, sel, tel) -> None:
    L = sd.laps[sd.laps["position"].notna()]
    _need(L, "Positions indisponibles", "Cette session ne contient pas de positions tour par tour.")
    n = max(len(sd.drivers), int(L["position"].max()))
    last_lap = int(L["lap"].max())
    hl = set(sel) if sel else set(sd.codes)

    view.begin()
    _head(view, sd, "Évolution des positions", "Les pilotes cochés sont mis en avant.")
    plot = new_plot(view, 2, x_label="Tour", y_label="Position", grid="xy", vline=True)
    plot.invertY(True)
    for d in reversed(sd.drivers):                   # les pilotes en avant dessinés en dernier
        g = L[L["driver"] == d.code].sort_values("lap")
        if g.empty:
            continue
        x, y = g["lap"].to_numpy(float), g["position"].to_numpy(float)
        if d.grid:
            x, y = np.r_[0.0, x], np.r_[float(d.grid), y]
        on = d.code in hl
        curve = pg.PlotCurveItem(x, y, pen=_pen(d, 2.8 if on else 1.2, 255 if on else 55))
        curve.setZValue(3 if on else 1)
        plot.addItem(curve)
        if on:
            t = pg.TextItem(d.code, color=d.color, anchor=(0, 0.5))
            t.setFont(theme.font(10, theme.QFont.Weight.DemiBold))
            t.setPos(x[-1] + 0.5, y[-1])
            plot.addItem(t, ignoreBounds=True)
    plot.setXRange(0, last_lap + 4, padding=0)
    plot.setYRange(0.5, n + 0.5, padding=0)
    plot.getViewBox().setLimits(xMin=-1, yMin=0.5, yMax=n + 0.5)
    ticks = sorted({1, 5, 10, 15, 20, n})
    plot.getAxis("left").setTicks([[(t, str(t)) for t in ticks if t <= n]])

    pivot = L.pivot_table(index="lap", columns="driver", values="position", aggfunc="first")
    colors = {d.code: d.color for d in sd.drivers}

    def probe(x: float) -> Optional[str]:
        lap = int(round(x))
        if lap not in pivot.index:
            return None
        row = pivot.loc[lap].dropna().sort_values()
        rows = [c for c in row.index if c in hl][:12]
        lines = [f"<b>Tour {lap}</b>"]
        lines += [f"P{int(row[c]):<3}<span style='color:{colors[c]}'>&#9632;</span> {c}" for c in rows]
        return "<br>".join(lines)

    view.set_probe(probe)


# ── 3. Stratégie pneumatique ─────────────────────────────────────────────────

def strategy(view: ChartView, sd: SessionData, sel, tel) -> None:
    L = sd.laps
    stints = (L.groupby(["driver", "stint", "compound"])["lap"].agg(["min", "max"]).reset_index())
    _need(stints, "Stratégie indisponible", "Aucun relais détecté dans cette session.")
    stints["start"] = stints["min"] - 1
    row = {d.code: i for i, d in enumerate(sd.drivers)}
    stints = stints[stints["driver"].isin(row)]
    stints["y"] = stints["driver"].map(row)

    view.begin()
    _head(view, sd, "Stratégie pneumatique", "Nombre de tours dans chaque relais.",
          _compound_legend(stints["compound"]))
    plot = new_plot(view, 2, x_label="Tour", grid="x")
    plot.invertY(True)
    for comp, (col, _label) in theme.COMPOUNDS.items():
        s = stints[stints["compound"] == comp]
        if s.empty:
            continue
        bar = pg.BarGraphItem(x0=s["start"].to_numpy(float), x1=s["max"].to_numpy(float),
                              y=s["y"].to_numpy(float), height=0.64, brush=col,
                              pen=pg.mkPen(theme.BG, width=1.5))
        plot.addItem(bar)
        ink = theme.BG if comp in ("MEDIUM", "HARD") else "#ffffff"
        for _, r in s.iterrows():
            width = int(r["max"] - r["start"])
            if width >= 4:
                t = pg.TextItem(str(width), color=ink, anchor=(0.5, 0.5))
                t.setFont(theme.font(9, theme.QFont.Weight.DemiBold))
                t.setPos((r["start"] + r["max"]) / 2, r["y"])
                plot.addItem(t, ignoreBounds=True)
    n = len(sd.drivers)
    plot.setXRange(0, int(L["lap"].max()) + 1, padding=0)
    plot.setYRange(-0.6, n - 0.4, padding=0)
    plot.getAxis("left").setTicks([[(i, d.code) for i, d in enumerate(sd.drivers)]])
    plot.getViewBox().setLimits(xMin=-2, yMin=-1, yMax=n)


# ── 4. Rythme des écuries ────────────────────────────────────────────────────

def teams(view: ChartView, sd: SessionData, sel, tel) -> None:
    laps = clean_laps(sd, None)
    _need(laps, "Pas assez de tours", "Aucun tour représentatif dans cette session.")
    laps = laps[laps.groupby("team")["laptime_s"].transform("size") >= 4]
    _need(laps, "Pas assez de tours", "Aucune écurie n'a assez de tours représentatifs.")
    order = laps.groupby("team")["laptime_s"].median().sort_values()
    color: dict[str, str] = {}
    for d in sd.drivers:
        color.setdefault(d.team, d.color)

    view.begin()
    _head(view, sd, "Rythme des écuries", "Du plus rapide au plus lent, médiane en blanc.")
    plot = new_plot(view, 2, x_label="Temps au tour", grid="x", time_x=True)
    plot.invertY(True)

    whisk_x, whisk_y, med_x, med_y, out_x, out_y = [], [], [], [], [], []
    lows, highs = [], []
    fastest = float(order.iloc[0])
    for i, (team, med) in enumerate(order.items()):
        v = laps.loc[laps["team"] == team, "laptime_s"].to_numpy()
        q1, q3 = np.percentile(v, [25, 75])
        iqr = q3 - q1
        lo = float(v[v >= q1 - 1.5 * iqr].min())
        hi = float(v[v <= q3 + 1.5 * iqr].max())
        col = color.get(team, theme.MUTED)
        lows.append(lo)
        highs.append(hi)
        plot.addItem(pg.BarGraphItem(x0=[q1], x1=[q3], y=[i], height=0.58,
                                     brush=_qcolor(col), pen=pg.mkPen(_qcolor(col))))
        whisk_x += [lo, q1, q3, hi, lo, lo, hi, hi]                  # moustaches et butées
        whisk_y += [i, i, i, i, i - 0.15, i + 0.15, i - 0.15, i + 0.15]
        med_x += [med, med]
        med_y += [i - 0.29, i + 0.29]
        out = v[(v < lo) | (v > hi)]
        out_x += out.tolist()
        out_y += [i] * len(out)
        if i:
            t = pg.TextItem(f"+{med - fastest:.3f} s", color=theme.MUTED, anchor=(0, 0.5))
            t.setFont(theme.font(10))
            t.setPos(hi + 0.12, i)
            plot.addItem(t, ignoreBounds=True)
    plot.addItem(pg.PlotCurveItem(whisk_x, whisk_y, connect="pairs", pen=pg.mkPen(theme.MUTED, width=1.2)))
    plot.addItem(pg.PlotCurveItem(med_x, med_y, connect="pairs", pen=pg.mkPen(theme.TEXT, width=3)))
    if out_x:
        plot.addItem(pg.ScatterPlotItem(x=out_x, y=out_y, size=4, pen=pg.mkPen(None),
                                        brush=pg.mkBrush(_qcolor(theme.MUTED, 150))))
    n = len(order)
    span = max(highs) - min(lows)
    plot.setXRange(min(lows) - 0.03 * span, max(highs) + 0.16 * span, padding=0)
    plot.setYRange(-0.6, n - 0.4, padding=0)
    plot.getAxis("left").setTicks([[(i, _short_team(t)) for i, t in enumerate(order.index)]])
    plot.getAxis("left").setStyle(tickFont=theme.font(11, theme.QFont.Weight.DemiBold))
    plot.getViewBox().setLimits(yMin=-1, yMax=n)


# ── 5. Progression des temps au tour ─────────────────────────────────────────

def _pivot_probe(pivot: pd.DataFrame, colors: dict, fmt: Callable[[float], str], head: str):
    def probe(x: float) -> Optional[str]:
        lap = int(round(x))
        if lap not in pivot.index:
            return None
        row = pivot.loc[lap].dropna()
        lines = [f"<b>{head} {lap}</b>"]
        lines += [f"<span style='color:{colors[c]}'>&#9632;</span> {c}  {fmt(v)}" for c, v in row.items()]
        return "<br>".join(lines) if len(lines) > 1 else None
    return probe


def progression(view: ChartView, sd: SessionData, sel, tel) -> None:
    codes = pick(sel, sd, 4)
    laps = clean_laps(sd, codes)
    _need(laps, "Pas assez de tours", "Aucun tour représentatif pour les pilotes sélectionnés.")

    view.begin()
    _head(view, sd, "Progression des temps au tour",
          "Tours d'arrêt au stand et tours lents exclus.")
    plot = new_plot(view, 2, x_label="Tour", y_label="Temps au tour", grid="xy",
                    time_y=True, vline=True)
    _legend(plot)
    colors = {}
    for code in codes:
        g = laps[laps["driver"] == code].sort_values("lap")
        if g.empty:
            continue
        d = sd.driver(code)
        colors[code] = d.color
        plot.plot(g["lap"].to_numpy(float), g["laptime_s"].to_numpy(), pen=_pen(d, 2.0),
                  symbol="o", symbolSize=5, symbolBrush=_qcolor(d.color), symbolPen=pg.mkPen(None),
                  name=code)
    pivot = laps.pivot_table(index="lap", columns="driver", values="laptime_s", aggfunc="first")
    view.set_probe(_pivot_probe(pivot[[c for c in colors]], colors, fmt_time, "Tour"))


# ── 6. Télémétrie du meilleur tour ───────────────────────────────────────────

def telemetry_codes(sel: list[str], sd: SessionData) -> list[str]:
    return (list(sel) if sel else sd.codes)[:2]


def telemetry(view: ChartView, sd: SessionData, sel, tel: Optional[dict[str, TelemetryLap]]) -> None:
    if not tel:
        raise Notice("Télémétrie indisponible", "Aucune donnée reçue pour les pilotes choisis.")
    codes = list(tel)
    a = codes[0]
    sub = "  contre  ".join(f"{c} {fmt_time(tel[c].laptime_s)}" for c in codes)
    extra = ""
    if len(codes) > 1:
        extra = f"Écart positif : {codes[1]} est derrière {a}."

    view.begin()
    _head(view, sd, "Télémétrie du meilleur tour", f"{sub}. {extra}".strip())
    panels = [("Vitesse (km/h)", 3), ("Accélérateur (%)", 2), ("Frein (appui)", 1)]
    if len(codes) > 1:
        panels.append(("Écart (s)", 2))
    plots = []
    for i, (label, stretch) in enumerate(panels):
        last = i == len(panels) - 1
        p = new_plot(view, 2 + i, x_label="Distance (m)" if last else "", y_label=label,
                     grid="xy", vline=True)
        view.glw.ci.layout.setRowStretchFactor(2 + i, stretch)
        p.getAxis("left").setWidth(64)
        if not last:
            p.getAxis("bottom").setStyle(showValues=False)
            p.getAxis("bottom").setHeight(6)
        if plots:
            p.setXLink(plots[0])
        plots.append(p)

    for code in codes:
        d, df = sd.driver(code), tel[code].df
        x = df["dist"].to_numpy()
        plots[0].plot(x, df["speed"].to_numpy(), pen=_pen(d, 1.8))
        plots[1].plot(x, df["throttle"].to_numpy(), pen=_pen(d, 1.8))
        plots[2].plot(x, df["brake"].to_numpy(float), pen=_pen(d, 1.6),
                      fillLevel=0, fillBrush=_qcolor(d.color, 35))
    plots[1].setYRange(-4, 104, padding=0)
    plots[2].setYRange(-0.1, 1.15, padding=0)
    plots[2].getAxis("left").setStyle(showValues=False)

    grid = delta = None
    if len(codes) > 1:
        da, db = tel[a].df, tel[codes[1]].df
        grid = np.linspace(0, min(da["dist"].max(), db["dist"].max()), 700)
        delta = np.interp(grid, db["dist"], db["t"]) - np.interp(grid, da["dist"], da["t"])
        plots[3].addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(theme.DIM, width=1)))
        plots[3].plot(grid, delta, pen=_pen(sd.driver(codes[1]), 2.0))

    for p in plots:
        p.setXRange(0, max(float(tel[c].df["dist"].max()) for c in codes), padding=0.01)
    plots[0].getViewBox().setLimits(xMin=-50)

    def probe(x: float) -> Optional[str]:
        lines = [f"<b>{int(x)} m</b>"]
        for c in codes:
            df = tel[c].df
            if not df["dist"].iloc[0] <= x <= df["dist"].iloc[-1]:
                continue
            sp, th, br, ge = (float(np.interp(x, df["dist"], df[k]))
                              for k in ("speed", "throttle", "brake", "gear"))
            lines.append(f"<span style='color:{sd.driver(c).color}'>&#9632;</span> {c}  "
                         f"{sp:.0f} km/h  {th:.0f} %  rapport {ge:.0f}{'  frein' if br > 0.5 else ''}")
        if delta is not None and grid[0] <= x <= grid[-1]:
            lines.append(f"Écart {np.interp(x, grid, delta):+.3f} s")
        return "<br>".join(lines) if len(lines) > 1 else None

    view.set_probe(probe)


# ── 7. Écart au leader ───────────────────────────────────────────────────────

def gap(view: ChartView, sd: SessionData, sel, tel) -> None:
    L = sd.laps[sd.laps["time_s"].notna()]
    _need(L, "Écarts indisponibles", "Cette session ne contient pas de chronométrage cumulé.")
    codes = pick(sel, sd, 6)
    lead = L.groupby("lap")["time_s"].min()
    L = L.assign(gap=L["time_s"].to_numpy() - lead.reindex(L["lap"]).to_numpy())
    L = L[L["driver"].isin(codes)]
    _need(L, "Écarts indisponibles", "Aucun tour pour les pilotes sélectionnés.")

    view.begin()
    _head(view, sd, "Écart au leader", "Temps cumulé à chaque passage sur la ligne.")
    plot = new_plot(view, 2, x_label="Tour", y_label="Écart au leader (s)", grid="xy", vline=True)
    plot.invertY(True)
    plot.addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(theme.DIM, width=1)))
    colors = {}
    for code in codes:
        g = L[L["driver"] == code].sort_values("lap")
        if g.empty:
            continue
        d = sd.driver(code)
        colors[code] = d.color
        x, y = g["lap"].to_numpy(float), g["gap"].to_numpy()
        plot.addItem(pg.PlotCurveItem(x, y, pen=_pen(d, 2.4)))
        t = pg.TextItem(code, color=d.color, anchor=(0, 0.5))
        t.setFont(theme.font(10, theme.QFont.Weight.DemiBold))
        t.setPos(x[-1] + 0.5, y[-1])
        plot.addItem(t, ignoreBounds=True)
    plot.setXRange(0, int(L["lap"].max()) + 4, padding=0)
    pivot = L.pivot_table(index="lap", columns="driver", values="gap", aggfunc="first")
    view.set_probe(_pivot_probe(pivot[[c for c in colors]], colors, lambda v: f"+{v:.3f} s", "Tour"))


# ── Registre ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Chart:
    key: str
    label: str
    hint: str
    drivers: str                    # "none" : ignore la sélection, sinon "highlight" ou "select"
    fn: Callable
    races_only: bool = False
    telemetry: bool = False

    def available(self, sd: Optional[SessionData]) -> bool:
        return sd is None or sd.is_race or not self.races_only


CHARTS: list[Chart] = [
    Chart("distribution", "Distribution",
          "Sans sélection : les 10 premiers.", "select", distribution),
    Chart("positions", "Positions",
          "Les pilotes cochés sont mis en avant. Survole le graphique pour lire le classement.",
          "highlight", positions, races_only=True),
    Chart("strategy", "Pneus", "Tous les pilotes, dans l'ordre d'arrivée.",
          "none", strategy, races_only=True),
    Chart("teams", "Écuries", "Toutes les écuries, sans sélection de pilotes.", "none", teams),
    Chart("progression", "Rythme", "Sans sélection : les 4 premiers.", "select", progression),
    Chart("telemetry", "Télémétrie", "Compare les deux premiers pilotes cochés.",
          "select", telemetry, telemetry=True),
    Chart("gap", "Écarts", "Sans sélection : les 6 premiers.", "select", gap, races_only=True),
]
BY_KEY = {c.key: c for c in CHARTS}


def render(chart: Chart, view: ChartView, sd: SessionData, sel: list[str],
           tel: Optional[dict[str, TelemetryLap]] = None) -> None:
    chart.fn(view, sd, sel, tel)
