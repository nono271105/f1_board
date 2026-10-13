"""
data.py : couche données (aucune dépendance à Qt).

- Service : accès FastF1 (calendrier, sessions, télémétrie) avec cache mémoire.
- SessionData : copie normalisée et légère d'une session (DataFrames pandas simples),
  pour que les graphiques ne dépendent jamais directement de FastF1.
- Les fonctions build_* sont pures : on peut les tester avec des données synthétiques.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
import zlib
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

FIRST_SEASON = 2018

SESSION_LABELS = {
    "R": "Course",
    "Q": "Qualifications",
    "S": "Course sprint",
    "SQ": "Qualifications sprint",
    "FP1": "Essais libres 1",
    "FP2": "Essais libres 2",
    "FP3": "Essais libres 3",
}
SESSION_SHORT = {
    "R": "Course", "Q": "Qualifs", "S": "Sprint", "SQ": "Q. sprint",
    "FP1": "EL1", "FP2": "EL2", "FP3": "EL3",
}
SESSION_ORDER = ["FP1", "FP2", "FP3", "SQ", "S", "Q", "R"]
_NAME_TO_CODE = {
    "Practice 1": "FP1", "Practice 2": "FP2", "Practice 3": "FP3",
    "Qualifying": "Q", "Sprint Qualifying": "SQ", "Sprint Shootout": "SQ",
    "Sprint": "S", "Race": "R",
}

_FALLBACK_COLORS = [
    "#3671c6", "#27f4d2", "#e8002d", "#ff8000", "#229971", "#ff87bc",
    "#64c4ff", "#b6babd", "#6692ff", "#52e252", "#d4af37", "#b138dd",
]


class DataUnavailable(Exception):
    """Données absentes ou pas encore publiées : le message est affiché tel quel."""


def available_years() -> list[int]:
    """Saisons proposées, de la plus récente à 2018 (la nouvelle saison apparaît en novembre)."""
    today = dt.date.today()
    return list(range(today.year + (1 if today.month >= 11 else 0), FIRST_SEASON - 1, -1))


# ── Modèles ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Event:
    round: int
    name: str
    country: str
    location: str
    date: dt.date
    sessions: tuple[str, ...]

    @property
    def short(self) -> str:
        return self.name.replace(" Grand Prix", "").strip()

    @property
    def done(self) -> bool:
        return self.date <= dt.date.today()


@dataclass(frozen=True)
class Driver:
    code: str
    name: str
    team: str
    number: str
    color: str
    dashed: bool          # second pilote d'une écurie : trait en tirets pour les distinguer
    position: Optional[int]
    grid: Optional[int]


@dataclass
class TelemetryLap:
    code: str
    laptime_s: float
    df: pd.DataFrame      # colonnes : dist, speed, throttle, brake, gear, t


@dataclass
class SessionData:
    year: int
    event: Event
    code: str
    drivers: list[Driver]
    laps: pd.DataFrame
    metrics: dict
    _ff1: object = field(default=None, repr=False)
    _tel_loaded: bool = field(default=False, repr=False)
    _tel: dict = field(default_factory=dict, repr=False)

    @property
    def label(self) -> str:
        return SESSION_LABELS.get(self.code, self.code)

    @property
    def is_race(self) -> bool:
        return self.code in ("R", "S")

    @property
    def codes(self) -> list[str]:
        return [d.code for d in self.drivers]

    def has_telemetry(self, codes: list[str]) -> bool:
        return all(c in self._tel for c in codes)

    def driver(self, code: str) -> Driver:
        for d in self.drivers:
            if d.code == code:
                return d
        raise KeyError(code)


# ── Utilitaires ──────────────────────────────────────────────────────────────

def fmt_time(sec: float) -> str:
    """92.345 -> 1:32.345"""
    if sec is None or not np.isfinite(sec):
        return "n/d"
    m, s = divmod(float(sec), 60)
    return f"{int(m)}:{s:06.3f}" if m >= 1 else f"{s:.3f}"


def _luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _lighten(hex_color: str, t: float) -> str:
    ch = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    ch = [round(c + (255 - c) * t) for c in ch]
    return "#{:02x}{:02x}{:02x}".format(*ch)


def _team_color(raw_hex, team: str) -> str:
    """Couleur d'écurie fournie par FastF1 (sans '#'), sinon repli stable (pas de hash() aléatoire)."""
    h = str(raw_hex or "").strip().lstrip("#")
    if len(h) == 6 and all(c in "0123456789abcdefABCDEF" for c in h):
        color = "#" + h.lower()
    else:
        color = _FALLBACK_COLORS[zlib.crc32(team.encode()) % len(_FALLBACK_COLORS)]
    if _luminance(color) < 0.10:            # quasi noir : éclaircir pour rester lisible sur fond sombre
        color = _lighten(color, 0.45)
    return color


def _col(raw: pd.DataFrame, name: str, default=np.nan) -> pd.Series:
    if name in raw.columns:
        return raw[name]
    return pd.Series(default, index=raw.index)


def _seconds(s: pd.Series) -> pd.Series:
    return pd.to_timedelta(s, errors="coerce").dt.total_seconds()


# ── Normalisation (fonctions pures) ──────────────────────────────────────────

def normalize_laps(raw: pd.DataFrame) -> pd.DataFrame:
    raw = pd.DataFrame(raw).reset_index(drop=True)
    compound = _col(raw, "Compound", "UNKNOWN").astype(str).str.upper()
    compound = compound.replace({"NAN": "UNKNOWN", "NONE": "UNKNOWN", "": "UNKNOWN"})
    df = pd.DataFrame({
        "driver": _col(raw, "Driver", "").astype(str),
        "team": _col(raw, "Team", "").astype(str),
        "lap": pd.to_numeric(_col(raw, "LapNumber"), errors="coerce"),
        "time_s": _seconds(_col(raw, "Time", pd.NaT)),
        "laptime_s": _seconds(_col(raw, "LapTime", pd.NaT)),
        "position": pd.to_numeric(_col(raw, "Position"), errors="coerce"),
        "stint": pd.to_numeric(_col(raw, "Stint"), errors="coerce"),
        "compound": compound,
        "pit": _col(raw, "PitInTime", pd.NaT).notna() | _col(raw, "PitOutTime", pd.NaT).notna(),
        "deleted": _col(raw, "Deleted", False).map(lambda v: bool(v) if pd.notna(v) else False),
    })
    df = df[(df["driver"] != "") & df["lap"].notna()].copy()
    df["lap"] = df["lap"].astype(int)
    df["stint"] = (
        df.groupby("driver")["stint"].transform(lambda s: s.ffill().bfill()).fillna(1).astype(int)
    )
    return df.sort_values(["driver", "lap"]).reset_index(drop=True)


def build_drivers(results: Optional[pd.DataFrame], laps: pd.DataFrame) -> list[Driver]:
    best = laps.groupby("driver")["laptime_s"].min()
    with_laps = set(laps["driver"].unique())
    rows = []

    if results is not None and len(results):
        for _, r in results.iterrows():
            code = str(r.get("Abbreviation", "")).strip()
            if code in with_laps:
                rows.append({
                    "code": code,
                    "name": str(r.get("FullName") or code),
                    "team": str(r.get("TeamName") or ""),
                    "number": str(r.get("DriverNumber") or ""),
                    "hex": r.get("TeamColor"),
                    "pos": pd.to_numeric(r.get("Position"), errors="coerce"),
                    "grid": pd.to_numeric(r.get("GridPosition"), errors="coerce"),
                })
    known = {r["code"] for r in rows}
    for code in sorted(with_laps - known):                  # pilotes absents des résultats
        team = laps.loc[laps["driver"] == code, "team"].iloc[0]
        rows.append({"code": code, "name": code, "team": team, "number": "",
                     "hex": None, "pos": np.nan, "grid": np.nan})

    # Classement : position officielle si connue, sinon meilleur tour (essais libres)
    rank_by_lap = best.rank(method="first")
    for r in rows:
        r["key"] = r["pos"] if pd.notna(r["pos"]) else 1000 + rank_by_lap.get(r["code"], 999)
    rows.sort(key=lambda r: r["key"])

    seen: dict[str, int] = {}
    drivers = []
    for r in rows:
        n = seen.get(r["team"], 0)
        seen[r["team"]] = n + 1
        drivers.append(Driver(
            code=r["code"], name=r["name"], team=r["team"], number=r["number"],
            color=_team_color(r["hex"], r["team"]), dashed=n >= 1,
            position=int(r["pos"]) if pd.notna(r["pos"]) else None,
            grid=int(r["grid"]) if pd.notna(r["grid"]) and r["grid"] > 0 else None,
        ))
    return drivers


def build_metrics(code: str, drivers: list[Driver], laps: pd.DataFrame,
                  weather: Optional[pd.DataFrame]) -> dict:
    lead = drivers[0] if drivers else None
    lead_label = {"R": "Vainqueur", "S": "Vainqueur", "Q": "Pole position", "SQ": "Pole position"}.get(
        code, "Meilleur temps")
    if code.startswith("FP") and len(laps):          # essais : le plus rapide, pas un classement
        idx = laps.loc[~laps["deleted"], "laptime_s"].idxmin() if laps["laptime_s"].notna().any() else None
        if idx is not None:
            lead = next((d for d in drivers if d.code == laps.loc[idx, "driver"]), lead)

    valid = laps[laps["laptime_s"].notna() & ~laps["deleted"]]
    fastest = valid.loc[valid["laptime_s"].idxmin()] if len(valid) else None

    m = {
        "lead_label": lead_label,
        "lead_code": lead.code if lead else "n/d",
        "lead_name": lead.name if lead else "n/d",
        "lead_team": lead.team if lead else "",
        "lead_color": lead.color if lead else "#6d6e77",
        "fastest_code": str(fastest["driver"]) if fastest is not None else "n/d",
        "fastest_time": fmt_time(fastest["laptime_s"]) if fastest is not None else "n/d",
        "laps": int(laps["lap"].max()) if len(laps) else 0,
        "air": None, "track": None, "rain": False,
    }
    if weather is not None and len(weather):
        if "AirTemp" in weather and weather["AirTemp"].notna().any():
            m["air"] = float(weather["AirTemp"].mean())
        if "TrackTemp" in weather and weather["TrackTemp"].notna().any():
            m["track"] = float(weather["TrackTemp"].mean())
        if "Rainfall" in weather:
            m["rain"] = bool(weather["Rainfall"].fillna(False).astype(bool).any())
    return m


def build_session(year: int, event: Event, code: str, raw_laps, raw_results, raw_weather,
                  ff1_session=None) -> SessionData:
    laps = normalize_laps(raw_laps)
    if laps.empty:
        raise DataUnavailable("Cette session ne contient aucun tour chronométré.")
    drivers = build_drivers(raw_results, laps)
    metrics = build_metrics(code, drivers, laps, raw_weather)
    return SessionData(year, event, code, drivers, laps, metrics, _ff1=ff1_session)


# ── Service FastF1 ───────────────────────────────────────────────────────────

class Service:
    """Accès FastF1. Toutes les méthodes sont bloquantes : à appeler depuis un thread."""

    def __init__(self, cache_dir: Optional[Path] = None, memory: int = 6):
        import fastf1
        self._ff1 = fastf1
        if cache_dir:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            try:
                fastf1.Cache.enable_cache(str(cache_dir))
            except Exception as exc:                       # cache déjà activé
                log.debug("Cache FastF1 : %s", exc)
        self._lock = threading.Lock()                      # FastF1 n'aime pas les chargements parallèles
        self._memory = memory
        self._sessions: OrderedDict[tuple, SessionData] = OrderedDict()
        self._schedules: dict[int, list[Event]] = {}

    def schedule(self, year: int) -> list[Event]:
        if year in self._schedules:
            return self._schedules[year]
        try:
            with self._lock:
                sched = self._ff1.get_event_schedule(year, include_testing=False)
        except Exception as exc:
            raise DataUnavailable(
                f"Impossible de récupérer le calendrier {year}. Vérifie ta connexion internet.") from exc

        events = []
        for _, r in sched.iterrows():
            codes = []
            for i in range(1, 6):
                c = _NAME_TO_CODE.get(str(r.get(f"Session{i}", "")))
                if c:
                    codes.append(c)
            if not codes:
                codes = ["FP1", "FP2", "FP3", "Q", "R"]
            events.append(Event(
                round=int(r["RoundNumber"]), name=str(r["EventName"]),
                country=str(r.get("Country", "")), location=str(r.get("Location", "")),
                date=pd.Timestamp(r["EventDate"]).date(),
                sessions=tuple(sorted(codes, key=SESSION_ORDER.index)),
            ))
        events = [e for e in events if e.round > 0]
        self._schedules[year] = events
        return events

    def session(self, year: int, event: Event, code: str) -> SessionData:
        key = (year, event.round, code)
        if key in self._sessions:
            self._sessions.move_to_end(key)
            return self._sessions[key]

        with self._lock:
            try:
                s = self._ff1.get_session(year, event.round, code)
                s.load(laps=True, telemetry=False, weather=True, messages=False)
                laps = s.laps
            except Exception as exc:
                log.warning("Chargement %s : %s", key, exc)
                raise DataUnavailable(
                    "Les données de cette session ne sont pas disponibles. Si elle vient de se "
                    "terminer, FastF1 peut mettre quelques heures à les publier.") from exc
            try:
                results = s.results
            except Exception:
                results = None
            try:
                weather = s.weather_data
            except Exception:
                weather = None
            sd = build_session(year, event, code, laps, results, weather, ff1_session=s)

        self._sessions[key] = sd
        while len(self._sessions) > self._memory:
            self._sessions.popitem(last=False)
        return sd

    def drop(self, year: int, event: Event, code: str) -> None:
        """Oublie la session en mémoire (le cache disque FastF1 est conservé)."""
        self._sessions.pop((year, event.round, code), None)

    def telemetry(self, sd: SessionData, codes: list[str]) -> dict[str, TelemetryLap]:
        """Télémétrie du meilleur tour de chaque pilote (chargée à la demande seulement)."""
        msg = ("La télémétrie de cette session n'est pas encore disponible. "
               "Elle est publiée avec un délai après la fin de la session.")
        with self._lock:
            if sd._ff1 is None:
                raise DataUnavailable(msg)
            if not sd._tel_loaded:
                try:
                    sd._ff1.load(laps=True, telemetry=True, weather=False, messages=False)
                    sd._tel_loaded = True
                except Exception as exc:
                    raise DataUnavailable(msg) from exc
            for code in codes:
                if code in sd._tel:
                    continue
                try:
                    lap = sd._ff1.laps.pick_drivers(code).pick_fastest()
                    car = lap.get_car_data().add_distance()
                    t = (car["Time"] - car["Time"].iloc[0]).dt.total_seconds()
                    df = pd.DataFrame({
                        "dist": car["Distance"].to_numpy(), "speed": car["Speed"].to_numpy(),
                        "throttle": car["Throttle"].to_numpy(),
                        "brake": car["Brake"].astype(int).to_numpy(),
                        "gear": car["nGear"].to_numpy(), "t": t.to_numpy(),
                    })
                    sd._tel[code] = TelemetryLap(code, float(lap["LapTime"].total_seconds()), df)
                except Exception as exc:
                    log.warning("Télémétrie %s : %s", code, exc)
                    raise DataUnavailable(
                        f"Pas de télémétrie exploitable pour {code} sur cette session.") from exc
        return {c: sd._tel[c] for c in codes}
