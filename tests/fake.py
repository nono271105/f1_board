"""
Données synthétiques au format FastF1 : permettent de tester toute l'application sans réseau.
Les DataFrames suivent les colonnes et types réels (timedelta, NaT, flottants) et passent par
les mêmes fonctions de normalisation que les vraies données.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import data
from data import DataUnavailable, Event, SessionData, TelemetryLap

TEAMS = [
    ("Red Bull Racing", "3671C6", [("VER", "Max Verstappen", "1"), ("TSU", "Yuki Tsunoda", "22")]),
    ("Ferrari", "E80020", [("LEC", "Charles Leclerc", "16"), ("HAM", "Lewis Hamilton", "44")]),
    ("McLaren", "FF8000", [("NOR", "Lando Norris", "4"), ("PIA", "Oscar Piastri", "81")]),
    ("Mercedes", "27F4D2", [("RUS", "George Russell", "63"), ("ANT", "Kimi Antonelli", "12")]),
    ("Aston Martin", "229971", [("ALO", "Fernando Alonso", "14"), ("STR", "Lance Stroll", "18")]),
    ("Alpine", "FF87BC", [("GAS", "Pierre Gasly", "10"), ("COL", "Franco Colapinto", "43")]),
    ("Williams", "64C4FF", [("ALB", "Alexander Albon", "23"), ("SAI", "Carlos Sainz", "55")]),
    ("Racing Bulls", "6692FF", [("LAW", "Liam Lawson", "30"), ("HAD", "Isack Hadjar", "6")]),
    ("Audi", "", [("HUL", "Nico Hulkenberg", "27"), ("BOR", "Gabriel Bortoleto", "5")]),
    ("Haas F1 Team", "B6BABD", [("OCO", "Esteban Ocon", "31"), ("BEA", "Oliver Bearman", "87")]),
    ("Cadillac", "", [("PER", "Sergio Perez", "11"), ("BOT", "Valtteri Bottas", "77")]),
]
GP_NAMES = ["Australian", "Chinese", "Japanese", "Bahrain", "Saudi Arabian", "Miami", "Emilia Romagna",
            "Monaco", "Spanish", "Canadian", "Austrian", "British", "Belgian", "Hungarian", "Dutch",
            "Italian", "Azerbaijan", "Singapore", "United States", "Mexico City", "Sao Paulo",
            "Las Vegas", "Qatar", "Abu Dhabi"]


def _td(x):
    return pd.to_timedelta(x, unit="s")


def make_race(n_laps: int = 58, seed: int = 3, short: bool = False):
    rng = np.random.default_rng(seed)
    drivers = [(c, n, num, t[0], t[1]) for t in TEAMS for (c, n, num) in t[2]]
    if short:
        n_laps = 14
    rows, results = [], []
    sc = range(22, 27) if not short else range(0)
    cum = {}
    for gi, (code, name, num, team, hexcol) in enumerate(drivers):
        pace = 91.4 + (TEAMS.index(next(t for t in TEAMS if t[0] == team))) * 0.16 + rng.normal(0, 0.12)
        stops = sorted(rng.choice(range(14, 44), size=2, replace=False)) if not short else []
        retire = {10: 31, 14: 17}.get(gi, None) if not short else None
        comps = rng.choice([["MEDIUM", "HARD", "HARD"], ["SOFT", "HARD", "MEDIUM"], ["MEDIUM", "HARD", "MEDIUM"]])
        t, stint, age = 0.4 * gi, 1, 0
        last = retire or n_laps
        for lap in range(1, last + 1):
            pit_in = lap in stops
            pit_out = (lap - 1) in stops
            lt = pace + 0.07 * age + rng.normal(0, 0.22) - 0.04 * lap
            if lap == 1:
                lt += 6
            if lap in sc:
                lt += 28
            if pit_in:
                lt += 2.5
            if pit_out:
                lt += 19
            t += lt
            rows.append({
                "Driver": code, "Team": team, "LapNumber": float(lap), "Time": _td(t), "LapTime": _td(lt),
                "Stint": float(stint), "Compound": comps[stint - 1], "TyreLife": float(age + 1),
                "PitInTime": _td(t) if pit_in else pd.NaT, "PitOutTime": _td(t - lt + 20) if pit_out else pd.NaT,
                "Deleted": np.nan if rng.random() < 0.5 else False,
            })
            age += 1
            if pit_in:
                stint += 1
                age = 0
        cum[code] = (last, t)
    df = pd.DataFrame(rows)
    df["Position"] = df.groupby("LapNumber")["Time"].rank(method="first").astype(float)
    order = sorted(cum, key=lambda c: (-cum[c][0], cum[c][1]))
    for gi, (code, name, num, team, hexcol) in enumerate(drivers):
        results.append({"Abbreviation": code, "FullName": name, "TeamName": team, "TeamColor": hexcol,
                        "DriverNumber": num, "Position": float(order.index(code) + 1),
                        "GridPosition": float(gi + 1) if gi != 7 else 0.0})
    weather = pd.DataFrame({"AirTemp": rng.normal(29, 0.4, 40), "TrackTemp": rng.normal(35, 0.8, 40),
                            "Rainfall": [False] * 40})
    return df, pd.DataFrame(results), weather


def make_quali(seed: int = 5):
    df, res, weather = make_race(n_laps=5, seed=seed, short=True)
    df = df[df["LapNumber"] <= 5].copy()
    df["Position"] = np.nan
    df["Compound"] = "SOFT"
    df["PitInTime"] = pd.NaT
    df["PitOutTime"] = pd.NaT
    df["LapTime"] = df["LapTime"] - pd.to_timedelta(5, unit="s")
    return df, res, weather


def make_telemetry(code: str, scale: float) -> TelemetryLap:
    dist = np.linspace(0, 5063, 420)
    base = 215 + 95 * np.sin(dist / 5063 * 2 * np.pi * 3) + 40 * np.sin(dist / 5063 * 2 * np.pi * 7)
    speed = np.clip(base * scale, 70, 335)
    slope = np.gradient(speed)
    throttle = np.clip(50 + slope * 14, 0, 100)
    brake = (slope < -2.2).astype(int)
    gear = np.clip((speed / 42).astype(int) + 1, 1, 8)
    t = np.cumsum(np.r_[0, np.diff(dist) / (speed[1:] / 3.6)])
    df = pd.DataFrame({"dist": dist, "speed": speed, "throttle": throttle, "brake": brake, "gear": gear, "t": t})
    return TelemetryLap(code, float(t[-1]), df)


class FakeService:
    """Même interface que data.Service."""

    def __init__(self, fail_codes: tuple[str, ...] = ()):
        self.fail_codes = fail_codes
        self.calls = 0

    def schedule(self, year: int) -> list[Event]:
        today = dt.date.today()
        events = []
        for i, name in enumerate(GP_NAMES, 1):
            date = today - dt.timedelta(days=(19 - i) * 14 + 1)
            sessions = ("FP1", "SQ", "S", "Q", "R") if i in (2, 6, 19) else ("FP1", "FP2", "FP3", "Q", "R")
            events.append(Event(i, f"{name} Grand Prix", "Pays", f"Circuit {i}", date, sessions))
        return events

    def session(self, year, event, code) -> SessionData:
        self.calls += 1
        if code in self.fail_codes:
            raise DataUnavailable("Les données de cette session ne sont pas disponibles. "
                                  "Si elle vient de se terminer, FastF1 peut mettre quelques heures à les publier.")
        raw = make_race() if code in ("R", "S") else make_quali()
        return data.build_session(year, event, code, *raw)

    def telemetry(self, sd, codes):
        for i, c in enumerate(codes):
            if c not in sd._tel:
                sd._tel[c] = make_telemetry(c, 1.0 + 0.012 * i)
        return {c: sd._tel[c] for c in codes}

    def drop(self, *a):
        pass
