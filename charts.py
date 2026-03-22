"""
charts.py — Visualisations F1 (matplotlib + fastf1.plotting)

Chaque classe expose une méthode statique `build(session, **opts) -> Figure`.
Toutes les figures utilisent le thème sombre F1.
"""

from __future__ import annotations

import logging
from typing import Optional

import fastf1
import fastf1.plotting
import matplotlib.patches as mpatches
import seaborn as sns
from matplotlib import pyplot as plt
from matplotlib.figure import Figure

log = logging.getLogger(__name__)

# Applique le schéma de couleurs FastF1 une seule fois au démarrage
fastf1.plotting.setup_mpl(mpl_timedelta_support=True, color_scheme="fastf1")

# ── Constantes esthétiques ───────────────────────────────────────────────────

_BG_DARK   = "#0f0f0f"
_BG_PANEL  = "#1a1a1a"
_FG        = "white"
_GRID      = dict(alpha=0.25, color="#444444")


def _base_fig(figsize: tuple) -> tuple[Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=figsize, facecolor=_BG_DARK)
    ax.set_facecolor(_BG_PANEL)
    ax.tick_params(colors=_FG, labelsize=9)
    ax.spines[:].set_color("#333333")
    return fig, ax


def _style_labels(ax, xlabel="", ylabel="", title="") -> None:
    kw = dict(color=_FG, fontsize=11)
    if xlabel: ax.set_xlabel(xlabel, **kw)
    if ylabel: ax.set_ylabel(ylabel, **kw)
    if title:  ax.set_title(title, color=_FG, fontsize=13, fontweight="bold", pad=12)


# ── 1. Distribution des temps au tour (violon + swarm) ──────────────────────

class LaptimesDistribution:

    @staticmethod
    def build(
        session: fastf1.core.Session,
        top_n: int = 10,
        figsize: tuple = (13, 6),
    ) -> Optional[Figure]:
        point_finishers = session.drivers[:top_n]
        driver_laps = (
            session.laps
            .pick_drivers(point_finishers)
            .pick_quicklaps()
            .reset_index()
        )
        if driver_laps.empty:
            log.warning("Aucun tour rapide disponible")
            return None

        finishing_order = [
            session.get_driver(i)["Abbreviation"] for i in point_finishers
        ]
        driver_laps["LapTime(s)"] = driver_laps["LapTime"].dt.total_seconds()

        # Mappings couleurs — récupérés une seule fois
        driver_colors   = fastf1.plotting.get_driver_color_mapping(session=session)
        compound_colors = fastf1.plotting.get_compound_mapping(session=session)

        fig, ax = _base_fig(figsize)

        sns.violinplot(
            data=driver_laps, x="Driver", y="LapTime(s)",
            hue="Driver", inner=None, density_norm="area",
            order=finishing_order, palette=driver_colors,
            ax=ax,
        )
        sns.swarmplot(
            data=driver_laps, x="Driver", y="LapTime(s)",
            order=finishing_order, hue="Compound",
            palette=compound_colors,
            hue_order=["SOFT", "MEDIUM", "HARD"],
            linewidth=0, size=3, ax=ax,
        )

        _style_labels(ax, "Pilote", "Temps au tour (s)", "Distribution des temps au tour")
        ax.grid(axis="y", **_GRID)
        sns.despine(left=True, bottom=True, ax=ax)
        plt.tight_layout()
        return fig


# ── 2. Évolution des positions ───────────────────────────────────────────────

class PositionChanges:

    @staticmethod
    def build(
        session: fastf1.core.Session,
        figsize: tuple = (11, 8),
    ) -> Optional[Figure]:
        fig, ax = _base_fig(figsize)

        for drv in session.drivers:
            drv_laps = session.laps.pick_drivers(drv)
            if drv_laps.empty:
                continue
            abb   = drv_laps["Driver"].iloc[0]
            style = fastf1.plotting.get_driver_style(
                identifier=abb, style=["color", "linestyle"], session=session
            )
            ax.plot(
                drv_laps["LapNumber"], drv_laps["Position"],
                label=abb, linewidth=2, **style,
            )

        ax.set_ylim([20.5, 0.5])
        ax.set_yticks([1, 5, 10, 15, 20])
        _style_labels(ax, "Tour", "Position", "Évolution des positions")
        ax.legend(
            bbox_to_anchor=(1.02, 1), loc="upper left",
            fontsize=8, facecolor=_BG_PANEL, edgecolor="#444",
            labelcolor=_FG, framealpha=0.9,
        )
        ax.grid(**_GRID)
        plt.tight_layout()
        return fig


# ── 3. Stratégie pneus ───────────────────────────────────────────────────────

class TyreStrategy:

    @staticmethod
    def build(
        session: fastf1.core.Session,
        figsize: tuple = (9, 13),
    ) -> Optional[Figure]:
        laps    = session.laps
        drivers = [session.get_driver(d)["Abbreviation"] for d in session.drivers]

        stints = (
            laps[["Driver", "Stint", "Compound", "LapNumber"]]
            .groupby(["Driver", "Stint", "Compound"])
            .count()
            .reset_index()
            .rename(columns={"LapNumber": "StintLength"})
        )

        fig, ax = _base_fig(figsize)

        for driver in drivers:
            driver_stints = stints[stints["Driver"] == driver]
            left = 0
            for _, row in driver_stints.iterrows():
                color = fastf1.plotting.get_compound_color(row["Compound"], session=session)
                ax.barh(
                    y=driver, width=row["StintLength"], left=left,
                    color=color, edgecolor="white", linewidth=0.4,
                )
                left += row["StintLength"]

        _style_labels(ax, "Tour", "", "Stratégie pneus")
        ax.tick_params(axis="y", labelsize=8)
        ax.invert_yaxis()
        ax.grid(axis="x", **_GRID)
        plt.tight_layout()
        return fig


# ── 4. Rythme des équipes ────────────────────────────────────────────────────

class TeamPace:

    @staticmethod
    def build(
        session: fastf1.core.Session,
        figsize: tuple = (14, 7),
    ) -> Optional[Figure]:
        laps = session.laps.pick_quicklaps().copy()
        if laps.empty:
            return None

        laps["LapTime(s)"] = laps["LapTime"].dt.total_seconds()

        team_order = (
            laps.groupby("Team")["LapTime(s)"]
            .median()
            .sort_values()
            .index
        )
        team_palette = {
            team: fastf1.plotting.get_team_color(team, session=session)
            for team in team_order
        }

        fig, ax = _base_fig(figsize)

        sns.boxplot(
            data=laps, x="Team", y="LapTime(s)",
            hue="Team", order=team_order, palette=team_palette,
            whiskerprops=dict(color=_FG),
            boxprops=dict(edgecolor=_FG),
            medianprops=dict(color="#FFD700", linewidth=2),
            capprops=dict(color=_FG),
            ax=ax,
        )

        _style_labels(ax, "", "Temps au tour (s)", "Comparaison du rythme des équipes")
        ax.tick_params(axis="x", rotation=30, labelsize=8)
        ax.grid(axis="y", **_GRID)
        plt.tight_layout()
        return fig


# ── 5. Progression pilotes sélectionnés ─────────────────────────────────────

class DriverLaptimes:

    @staticmethod
    def build(
        session: fastf1.core.Session,
        drivers: Optional[list[str]] = None,
        figsize: tuple = (11, 6),
    ) -> Optional[Figure]:
        if not drivers:
            drivers = list(session.drivers[:4])

        # Filtre global puis segmentation par pilote — évite N appels pick_drivers
        all_laps = (
            session.laps
            .pick_drivers(drivers)
            .pick_quicklaps()
            .reset_index()
        )
        if all_laps.empty:
            return None

        fig, ax = _base_fig(figsize)

        for drv in drivers:
            laps = all_laps[all_laps["Driver"] == drv]
            if laps.empty:
                continue
            style = fastf1.plotting.get_driver_style(
                identifier=drv, style=["color", "linestyle"], session=session
            )
            ax.plot(laps["LapNumber"], laps["LapTime"], label=drv, linewidth=2, **style)

        _style_labels(ax, "Tour", "Temps au tour", "Progression des temps au tour")
        ax.grid(**_GRID)
        try:
            fastf1.plotting.add_sorted_driver_legend(ax, session)
        except Exception:
            ax.legend(facecolor=_BG_PANEL, labelcolor=_FG)

        plt.tight_layout()
        return fig


# ── Registre des visualisations ──────────────────────────────────────────────

CHARTS: dict[str, type] = {
    "laptimes":      LaptimesDistribution,
    "positions":     PositionChanges,
    "strategy":      TyreStrategy,
    "team_pace":     TeamPace,
    "driver_style":  DriverLaptimes,
}

CHART_LABELS: dict[str, str] = {
    "laptimes":      "Distribution des temps",
    "positions":     "Évolution des positions",
    "strategy":      "Stratégie pneus",
    "team_pace":     "Rythme des équipes",
    "driver_style":  "Progression pilotes",
}


def build_chart(
    chart_type: str,
    session: fastf1.core.Session,
    drivers: Optional[list[str]] = None,
) -> Optional[Figure]:
    """Point d'entrée unique pour générer un graphique."""
    cls = CHARTS.get(chart_type)
    if cls is None:
        log.error("Type de graphique inconnu : %s", chart_type)
        return None
    try:
        if chart_type == "driver_style":
            return cls.build(session, drivers=drivers)
        return cls.build(session)
    except Exception as exc:
        log.error("Erreur génération %s : %s", chart_type, exc, exc_info=True)
        return None