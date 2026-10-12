"""
charts.py — Visualisations F1 (Matplotlib + FastF1)

Thème sombre Formule 1 moderne, rendu thread-safe (sans plt.subplots)
et gestion robuste des saisons récentes (2024, 2025, 2026+) avec support
des nouvelles écuries (Audi, Cadillac) et fallbacks systématiques.
"""

from __future__ import annotations

import copy
import logging
from typing import Optional, Union

import fastf1
import fastf1.plotting
from fastf1.plotting._backend import Constants
from fastf1.plotting._constants.base import TeamConst, TeamColorsConst
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
import numpy as np
import pandas as pd
import seaborn as sns

log = logging.getLogger(__name__)

# Initialisation sûre de fastf1.plotting
try:
    fastf1.plotting.setup_mpl(mpl_timedelta_support=True, color_scheme="fastf1")
except Exception as exc:
    log.warning("setup_mpl warning: %s", exc)

# ── Palette et constantes d'affichage ────────────────────────────────────────

_BG_DARK    = "#0d0f12"
_BG_PANEL   = "#161920"
_BG_CARD    = "#1c202a"
_FG         = "#f5f6f8"
_FG_MUTED   = "#8b949e"
_GRID_COLOR = "#232834"
_GRID       = dict(alpha=0.35, color=_GRID_COLOR, linestyle="--", linewidth=0.8)

# Palette de secours pour pilotes/écuries inconnus
_FALLBACK_PALETTE = [
    "#e10600", "#ff8000", "#27f4d2", "#e80020", "#3671c6",
    "#229971", "#6692ff", "#b6babd", "#64c4ff", "#52e252",
    "#f50537", "#d4af37", "#b138dd", "#ff87bc", "#ffb800",
    "#00e5ff", "#a8ff00", "#ff5252", "#90caf9", "#ce93d8",
]

_COMPOUND_COLORS = {
    "SOFT":         "#ff3333",
    "MEDIUM":       "#ffd12e",
    "HARD":         "#f0f0ec",
    "INTERMEDIATE": "#39b54a",
    "WET":          "#00a0dd",
    "TEST-UNKNOWN": "#6c757d",
    "UNKNOWN":      "#888888",
}


# ── Compatibilité saisons récentes (2026+ Audi, Cadillac, etc.) ─────────────

def _ensure_season_constants(year: Union[int, str]) -> None:
    """Enregistre les données écuries pour les saisons 2026+ si absentes."""
    y_str = str(year)
    if y_str not in Constants:
        # Cloner la dernière saison connue
        latest_key = sorted(Constants.keys())[-1] if Constants else "2025"
        base = copy.deepcopy(Constants.get(latest_key, next(iter(Constants.values()))))
        Constants[y_str] = base

    # Ajouter les écuries apparues en 2026 si absentes
    teams_dict = Constants[y_str].Teams
    if "audi" not in teams_dict:
        teams_dict["audi"] = TeamConst(
            ShortName="Audi",
            TeamColor=TeamColorsConst(Official="#e20613", FastF1="#f50537")
        )
    if "cadillac" not in teams_dict:
        teams_dict["cadillac"] = TeamConst(
            ShortName="Cadillac",
            TeamColor=TeamColorsConst(Official="#c8a951", FastF1="#d4af37")
        )


# ── Fonctions utilitaires de couleurs sécurisées ──────────────────────────────

def get_safe_driver_color(driver: str, session: fastf1.core.Session) -> str:
    """Récupère la couleur d'un pilote sans jamais planter."""
    _ensure_season_constants(session.event.year)
    try:
        color = fastf1.plotting.get_driver_color(driver, session=session)
        if color and str(color).startswith("#"):
            return color
    except Exception:
        pass

    # Essai via team
    try:
        drv_info = session.get_driver(driver)
        team = drv_info.get("TeamName")
        if team:
            t_color = get_safe_team_color(team, session)
            if t_color:
                return t_color
    except Exception:
        pass

    # Hash déterministe vers la palette de secours
    idx = abs(hash(str(driver))) % len(_FALLBACK_PALETTE)
    return _FALLBACK_PALETTE[idx]


def get_safe_driver_colors(session: fastf1.core.Session, drivers: list[str]) -> dict[str, str]:
    """Retourne un mapping de couleurs garanti pour tous les pilotes fournis."""
    _ensure_season_constants(session.event.year)
    colors = {}
    try:
        fast_colors = fastf1.plotting.get_driver_color_mapping(session=session)
        if isinstance(fast_colors, dict):
            colors.update(fast_colors)
    except Exception as exc:
        log.debug("Impossible d'obtenir le mapping fastf1 complet: %s", exc)

    # Compléter tous les pilotes manquants
    for idx, drv in enumerate(drivers):
        if drv not in colors or not colors[drv]:
            colors[drv] = get_safe_driver_color(drv, session)

    return colors


def get_safe_team_color(team: str, session: fastf1.core.Session) -> str:
    """Récupère la couleur d'une écurie sans jamais planter."""
    _ensure_season_constants(session.event.year)
    try:
        color = fastf1.plotting.get_team_color(team, session=session)
        if color and str(color).startswith("#"):
            return color
    except Exception:
        pass

    team_lower = str(team).lower()
    if "audi" in team_lower:
        return "#f50537"
    if "cadillac" in team_lower:
        return "#d4af37"
    if "red bull" in team_lower:
        return "#3671c6"
    if "ferrari" in team_lower:
        return "#e80020"
    if "mercedes" in team_lower:
        return "#27f4d2"
    if "mclaren" in team_lower:
        return "#ff8000"
    if "aston martin" in team_lower:
        return "#229971"
    if "alpine" in team_lower:
        return "#ff87bc"
    if "williams" in team_lower:
        return "#64c4ff"
    if "haas" in team_lower:
        return "#b6babd"
    if "sauber" in team_lower:
        return "#52e252"
    if "racing bulls" in team_lower or "rb" in team_lower:
        return "#6692ff"

    idx = abs(hash(str(team))) % len(_FALLBACK_PALETTE)
    return _FALLBACK_PALETTE[idx]


def get_safe_compound_color(compound: str, session: Optional[fastf1.core.Session] = None) -> str:
    """Récupère la couleur Pirelli d'un train de pneus."""
    comp_upper = str(compound).strip().upper()
    if session:
        _ensure_season_constants(session.event.year)
        try:
            c = fastf1.plotting.get_compound_color(comp_upper, session=session)
            if c:
                return c
        except Exception:
            pass

    return _COMPOUND_COLORS.get(comp_upper, "#888888")


def get_safe_driver_style(identifier: str, session: fastf1.core.Session) -> dict:
    """Récupère le style (couleur + style de ligne) d'un pilote."""
    _ensure_season_constants(session.event.year)
    try:
        return fastf1.plotting.get_driver_style(
            identifier=identifier, style=["color", "linestyle"], session=session
        )
    except Exception:
        return {
            "color": get_safe_driver_color(identifier, session),
            "linestyle": "solid",
        }


# ── Figure de base (Thread-Safe avec API Figure directe) ─────────────────────

def _base_fig(figsize: tuple) -> tuple[Figure, any]:
    """Crée une Figure de manière purement OO sans toucher au pyplot global."""
    fig = Figure(figsize=figsize, facecolor=_BG_DARK)
    ax = fig.add_subplot(111)
    ax.set_facecolor(_BG_PANEL)
    ax.tick_params(colors=_FG, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(_GRID_COLOR)
    return fig, ax


def _style_labels(ax, xlabel="", ylabel="", title="", subtitle="") -> None:
    kw = dict(color=_FG, fontsize=11, fontweight="medium")
    if xlabel: ax.set_xlabel(xlabel, **kw)
    if ylabel: ax.set_ylabel(ylabel, **kw)
    if title:
        full_title = f"{title}\n{subtitle}" if subtitle else title
        ax.set_title(full_title, color=_FG, fontsize=13, fontweight="bold", pad=14)


# ── 1. Distribution des temps au tour (Violon + Swarm) ────────────────────────

class LaptimesDistribution:

    @staticmethod
    def build(
        session: fastf1.core.Session,
        top_n: int = 10,
        figsize: tuple = (13, 6.5),
    ) -> Optional[Figure]:
        _ensure_season_constants(session.event.year)
        point_finishers = list(session.drivers[:top_n])
        driver_laps = (
            session.laps
            .pick_drivers(point_finishers)
            .pick_quicklaps()
            .reset_index(drop=True)
        )
        if driver_laps.empty:
            log.warning("Aucun tour rapide disponible pour la distribution")
            return None

        finishing_order = [
            session.get_driver(i)["Abbreviation"] for i in point_finishers
            if i in session.drivers
        ]
        # Garder uniquement les pilotes présents dans le jeu de données
        finishing_order = [d for d in finishing_order if d in driver_laps["Driver"].unique()]
        driver_laps["LapTime(s)"] = driver_laps["LapTime"].dt.total_seconds()

        driver_colors = get_safe_driver_colors(session, finishing_order)
        compound_colors = {c: get_safe_compound_color(c, session) for c in ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]}

        fig, ax = _base_fig(figsize)

        try:
            sns.violinplot(
                data=driver_laps, x="Driver", y="LapTime(s)",
                hue="Driver", inner=None, density_norm="area",
                order=finishing_order, palette=driver_colors,
                ax=ax, legend=False,
            )
        except Exception:
            # Fallback simple sans hue si incompatibilité de version seaborn
            sns.violinplot(
                data=driver_laps, x="Driver", y="LapTime(s)",
                inner=None, density_norm="area",
                order=finishing_order, palette=driver_colors,
                ax=ax,
            )

        sns.swarmplot(
            data=driver_laps, x="Driver", y="LapTime(s)",
            order=finishing_order, hue="Compound",
            palette=compound_colors,
            hue_order=[c for c in ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"] if c in driver_laps["Compound"].values],
            linewidth=0, size=3.5, ax=ax,
        )

        _style_labels(
            ax,
            xlabel="Pilote",
            ylabel="Temps au tour (secondes)",
            title="Distribution des temps au tour",
            subtitle=f"{session.event['EventName']} {session.event.year} — {session.name}"
        )
        ax.grid(axis="y", **_GRID)
        sns.despine(fig=fig, ax=ax, left=True, bottom=True)
        fig.tight_layout()
        return fig


# ── 2. Évolution des positions ───────────────────────────────────────────────

class PositionChanges:

    @staticmethod
    def build(
        session: fastf1.core.Session,
        figsize: tuple = (12, 7.5),
    ) -> Optional[Figure]:
        _ensure_season_constants(session.event.year)
        fig, ax = _base_fig(figsize)
        total_drivers = len(session.drivers)

        for drv in session.drivers:
            drv_laps = session.laps.pick_drivers(drv)
            if drv_laps.empty:
                continue
            abb = drv_laps["Driver"].iloc[0]
            style = get_safe_driver_style(abb, session)
            ax.plot(
                drv_laps["LapNumber"], drv_laps["Position"],
                label=abb, linewidth=2, alpha=0.9, **style,
            )

        max_pos = max(20, total_drivers)
        ax.set_ylim([max_pos + 0.5, 0.5])
        ticks = [1, 5, 10, 15, 20]
        if max_pos > 20:
            ticks.append(max_pos)
        ax.set_yticks(ticks)

        _style_labels(
            ax,
            xlabel="Numéro de tour",
            ylabel="Position en course",
            title="Évolution des positions au fil des tours",
            subtitle=f"{session.event['EventName']} {session.event.year}"
        )
        ax.legend(
            bbox_to_anchor=(1.02, 1), loc="upper left",
            fontsize=8.5, facecolor=_BG_PANEL, edgecolor=_GRID_COLOR,
            labelcolor=_FG, framealpha=0.95,
        )
        ax.grid(**_GRID)
        fig.tight_layout()
        return fig


# ── 3. Stratégie pneumatique ─────────────────────────────────────────────────

class TyreStrategy:

    @staticmethod
    def build(
        session: fastf1.core.Session,
        figsize: tuple = (10, 9),
    ) -> Optional[Figure]:
        _ensure_season_constants(session.event.year)
        laps = session.laps
        drivers = [session.get_driver(d)["Abbreviation"] for d in session.drivers]

        stints = (
            laps[["Driver", "Stint", "Compound", "LapNumber"]]
            .groupby(["Driver", "Stint", "Compound"])
            .count()
            .reset_index()
            .rename(columns={"LapNumber": "StintLength"})
        )

        fig, ax = _base_fig(figsize)
        compounds_seen = set()

        for driver in drivers:
            driver_stints = stints[stints["Driver"] == driver]
            left = 0
            for _, row in driver_stints.iterrows():
                comp = str(row["Compound"]).upper()
                compounds_seen.add(comp)
                color = get_safe_compound_color(comp, session)
                ax.barh(
                    y=driver, width=row["StintLength"], left=left,
                    color=color, edgecolor="#222222", linewidth=0.6,
                    height=0.65,
                )
                left += row["StintLength"]

        _style_labels(
            ax,
            xlabel="Tours en course",
            ylabel="",
            title="Stratégie pneumatique par pilote",
            subtitle=f"{session.event['EventName']} {session.event.year}"
        )
        ax.tick_params(axis="y", labelsize=8.5)
        ax.invert_yaxis()
        ax.grid(axis="x", **_GRID)

        # Légende des gommes
        legend_patches = [
            mpatches.Patch(color=get_safe_compound_color(c, session), label=c)
            for c in ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]
            if c in compounds_seen
        ]
        if legend_patches:
            ax.legend(
                handles=legend_patches, loc="upper right",
                facecolor=_BG_PANEL, edgecolor=_GRID_COLOR,
                labelcolor=_FG, fontsize=9,
            )

        fig.tight_layout()
        return fig


# ── 4. Rythme des équipes ────────────────────────────────────────────────────

class TeamPace:

    @staticmethod
    def build(
        session: fastf1.core.Session,
        figsize: tuple = (13, 6.5),
    ) -> Optional[Figure]:
        _ensure_season_constants(session.event.year)
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
            team: get_safe_team_color(team, session=session)
            for team in team_order
        }

        fig, ax = _base_fig(figsize)

        try:
            sns.boxplot(
                data=laps, x="Team", y="LapTime(s)",
                order=team_order, palette=team_palette,
                whiskerprops=dict(color=_FG),
                boxprops=dict(edgecolor=_FG, linewidth=1.2),
                medianprops=dict(color="#FFD700", linewidth=2.5),
                capprops=dict(color=_FG),
                ax=ax,
            )
        except Exception:
            sns.boxplot(
                data=laps, x="Team", y="LapTime(s)",
                order=team_order,
                ax=ax,
            )

        _style_labels(
            ax,
            xlabel="",
            ylabel="Temps au tour (secondes)",
            title="Comparaison du rythme de course des écuries",
            subtitle=f"{session.event['EventName']} {session.event.year} (Classé du plus rapide au plus lent)"
        )
        ax.tick_params(axis="x", rotation=25, labelsize=8.5)
        ax.grid(axis="y", **_GRID)
        sns.despine(fig=fig, ax=ax, left=True, bottom=True)
        fig.tight_layout()
        return fig


# ── 5. Progression chronométrique des pilotes ────────────────────────────────

class DriverLaptimes:

    @staticmethod
    def build(
        session: fastf1.core.Session,
        drivers: Optional[list[str]] = None,
        figsize: tuple = (12, 6.5),
    ) -> Optional[Figure]:
        _ensure_season_constants(session.event.year)

        # Résoudre les abréviations si des numéros sont passés ou par défaut
        resolved_drivers: list[str] = []
        if drivers:
            for d in drivers:
                if str(d).isdigit():
                    try:
                        resolved_drivers.append(session.get_driver(d)["Abbreviation"])
                    except Exception:
                        resolved_drivers.append(str(d))
                else:
                    resolved_drivers.append(str(d))
        else:
            # Top 4 par défaut
            for num in session.drivers[:4]:
                try:
                    resolved_drivers.append(session.get_driver(num)["Abbreviation"])
                except Exception:
                    pass

        if not resolved_drivers:
            return None

        all_laps = (
            session.laps
            .pick_drivers(resolved_drivers)
            .pick_quicklaps()
            .reset_index(drop=True)
        )
        if all_laps.empty:
            log.warning("Aucun tour rapide trouvé pour les pilotes sélectionnés")
            return None

        fig, ax = _base_fig(figsize)
        plotted_any = False

        for drv in resolved_drivers:
            laps = all_laps[all_laps["Driver"] == drv]
            if laps.empty:
                continue
            style = get_safe_driver_style(drv, session)
            # Conversion en secondes pour une échelle fluide
            sec = laps["LapTime"].dt.total_seconds()
            ax.plot(
                laps["LapNumber"], sec,
                label=drv, linewidth=2, alpha=0.9, marker="o", markersize=3, **style
            )
            plotted_any = True

        if not plotted_any:
            return None

        _style_labels(
            ax,
            xlabel="Numéro de tour",
            ylabel="Temps au tour (s)",
            title="Progression des temps au tour par pilote",
            subtitle=f"{session.event['EventName']} {session.event.year}"
        )
        ax.grid(**_GRID)
        ax.legend(
            loc="upper right", facecolor=_BG_PANEL,
            edgecolor=_GRID_COLOR, labelcolor=_FG, framealpha=0.95
        )
        fig.tight_layout()
        return fig


# ── 6. NOUVEAU : Télémétrie comparative (Tour le plus rapide) ────────────────

class TelemetryComparison:

    @staticmethod
    def build(
        session: fastf1.core.Session,
        drivers: Optional[list[str]] = None,
        figsize: tuple = (13, 8),
    ) -> Optional[Figure]:
        """Compare la télémétrie (Vitesse, Accélérateur, Freinage) des meilleurs tours."""
        _ensure_season_constants(session.event.year)

        # Déterminer les pilotes à comparer (2 pilotes)
        comp_drivers: list[str] = []
        if drivers and len(drivers) >= 2:
            comp_drivers = drivers[:2]
        elif drivers and len(drivers) == 1:
            comp_drivers = [drivers[0]]
            # Ajouter le leader ou le pilote le plus rapide
            for d in session.drivers:
                abb = session.get_driver(d)["Abbreviation"]
                if abb != comp_drivers[0]:
                    comp_drivers.append(abb)
                    break
        else:
            # Top 2 de la session
            for num in session.drivers[:2]:
                comp_drivers.append(session.get_driver(num)["Abbreviation"])

        fig = Figure(figsize=figsize, facecolor=_BG_DARK)
        ax_speed = fig.add_subplot(311)
        ax_throttle = fig.add_subplot(312, sharex=ax_speed)
        ax_brake = fig.add_subplot(313, sharex=ax_speed)

        for ax in (ax_speed, ax_throttle, ax_brake):
            ax.set_facecolor(_BG_PANEL)
            ax.tick_params(colors=_FG, labelsize=8.5)
            for spine in ax.spines.values():
                spine.set_color(_GRID_COLOR)
            ax.grid(**_GRID)

        plotted = 0
        for drv in comp_drivers:
            try:
                drv_laps = session.laps.pick_drivers(drv)
                if drv_laps.empty:
                    continue
                fastest = drv_laps.pick_fastest()
                car_data = fastest.get_car_data().add_distance()
                if car_data.empty or "Speed" not in car_data:
                    continue

                style = get_safe_driver_style(drv, session)
                color = style.get("color", get_safe_driver_color(drv, session))
                lap_str = str(fastest["LapTime"]).split()[-1][:11]

                label = f"{drv} ({lap_str})"
                ax_speed.plot(car_data["Distance"], car_data["Speed"], label=label, color=color, linewidth=1.8)
                ax_throttle.plot(car_data["Distance"], car_data["Throttle"], label=label, color=color, linewidth=1.5)
                ax_brake.plot(car_data["Distance"], car_data["Brake"], label=label, color=color, linewidth=1.5)
                plotted += 1
            except Exception as exc:
                log.warning("Erreur télémétrie %s: %s", drv, exc)

        if plotted == 0:
            log.warning("Aucune donnée de télémétrie disponible pour cette session")
            return None

        ax_speed.set_title(
            f"Comparaison Télémétrie — Meilleurs Tours\n{session.event['EventName']} {session.event.year}",
            color=_FG, fontsize=12, fontweight="bold", pad=10
        )
        ax_speed.set_ylabel("Vitesse (km/h)", color=_FG, fontsize=9.5)
        ax_speed.legend(loc="upper right", facecolor=_BG_PANEL, edgecolor=_GRID_COLOR, labelcolor=_FG, fontsize=8)

        ax_throttle.set_ylabel("Accélérateur (%)", color=_FG, fontsize=9.5)
        ax_throttle.set_ylim(-5, 105)

        ax_brake.set_ylabel("Frein", color=_FG, fontsize=9.5)
        ax_brake.set_xlabel("Distance sur le circuit (m)", color=_FG, fontsize=10)
        ax_brake.set_ylim(-0.1, 1.1)

        fig.tight_layout()
        return fig


# ── 7. NOUVEAU : Écart au leader (Gap to leader) ──────────────────────────────

class GapToLeader:

    @staticmethod
    def build(
        session: fastf1.core.Session,
        drivers: Optional[list[str]] = None,
        figsize: tuple = (12, 6.5),
    ) -> Optional[Figure]:
        """Affiche l'écart en secondes par rapport au leader tour par tour."""
        _ensure_season_constants(session.event.year)
        laps = session.laps.reset_index(drop=True)
        if laps.empty:
            return None

        # Leader par tour
        leader_laps = laps[laps["Position"] == 1].set_index("LapNumber")["Time"]

        target_drivers = drivers if drivers else [session.get_driver(d)["Abbreviation"] for d in session.drivers[:6]]
        fig, ax = _base_fig(figsize)
        plotted = False

        for drv in target_drivers:
            drv_laps = laps[laps["Driver"] == drv]
            if drv_laps.empty:
                continue
            drv_laps = drv_laps.set_index("LapNumber")
            common_laps = drv_laps.index.intersection(leader_laps.index)
            if common_laps.empty:
                continue

            delta = (drv_laps.loc[common_laps, "Time"] - leader_laps.loc[common_laps]).dt.total_seconds()
            style = get_safe_driver_style(drv, session)
            ax.plot(common_laps, delta, label=drv, linewidth=2, alpha=0.9, **style)
            plotted = True

        if not plotted:
            return None

        _style_labels(
            ax,
            xlabel="Numéro de tour",
            ylabel="Écart au leader (secondes)",
            title="Évolution de l'écart chronométrique au leader",
            subtitle=f"{session.event['EventName']} {session.event.year}"
        )
        ax.grid(**_GRID)
        ax.legend(
            loc="upper left", facecolor=_BG_PANEL,
            edgecolor=_GRID_COLOR, labelcolor=_FG, framealpha=0.95, fontsize=8.5
        )
        fig.tight_layout()
        return fig


# ── Registre des visualisations ──────────────────────────────────────────────

CHARTS: dict[str, type] = {
    "laptimes":      LaptimesDistribution,
    "positions":     PositionChanges,
    "strategy":      TyreStrategy,
    "team_pace":     TeamPace,
    "driver_style":  DriverLaptimes,
    "telemetry":     TelemetryComparison,
    "gap_leader":    GapToLeader,
}

CHART_LABELS: dict[str, str] = {
    "laptimes":      "🏎️  Distribution des temps",
    "positions":     "📈  Évolution des positions",
    "strategy":      "🛞  Stratégie pneumatique",
    "team_pace":     "⏱️  Rythme des écuries",
    "driver_style":  "📊  Progression pilotes",
    "telemetry":     "⚡  Télémétrie (Tour rapide)",
    "gap_leader":    "🏁  Écart au leader",
}


def build_chart(
    chart_type: str,
    session: fastf1.core.Session,
    drivers: Optional[list[str]] = None,
) -> Optional[Figure]:
    """Point d'entrée unique et sécurisé pour générer un graphique."""
    cls = CHARTS.get(chart_type)
    if cls is None:
        log.error("Type de graphique inconnu : %s", chart_type)
        return None
    try:
        if chart_type in ("driver_style", "telemetry", "gap_leader"):
            return cls.build(session, drivers=drivers)
        return cls.build(session)
    except Exception as exc:
        log.error("Erreur génération %s : %s", chart_type, exc, exc_info=True)
        return None