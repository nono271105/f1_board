"""
data.py — Couche données F1

Responsabilités :
- Accès FastF1 (calendrier, sessions, pilotes)
- Support multi-saisons dynamique (2018 jusqu'à l'année en cours + 1)
- Cache mémoire et gestion des sessions asynchrones via QThreadPool
- Extraction de métriques de résumé de session (vainqueur, tour rapide, météo)
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional, Any

import fastf1
import pandas as pd
from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot

import charts

log = logging.getLogger(__name__)

# ── Saisons disponibles (dynamique) ──────────────────────────────────────────

_NOW_YEAR = datetime.date.today().year
AVAILABLE_YEARS: list[int] = list(range(2018, max(2027, _NOW_YEAR + 1)))

SESSION_TYPES: dict[str, str] = {
    "R":   "Course (Grand Prix)",
    "Q":   "Qualifications",
    "S":   "Course Sprint",
    "SQ":  "Qualifications Sprint",
    "FP1": "Essais Libres 1 (FP1)",
    "FP2": "Essais Libres 2 (FP2)",
    "FP3": "Essais Libres 3 (FP3)",
}


# ── Signals wrapper ───────────────────────────────────────────────────────────

class _WorkerSignals(QObject):
    result = pyqtSignal(object)
    error  = pyqtSignal(str)


# ── Worker générique ─────────────────────────────────────────────────────────

class _Worker(QRunnable):
    """Exécute une fonction dans le pool global sans bloquer le thread principal."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn      = fn
        self.args    = args
        self.kwargs  = kwargs
        self.signals = _WorkerSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
            try:
                self.signals.result.emit(result)
            except RuntimeError:
                pass
        except Exception as exc:
            log.error("Erreur worker (%s): %s", self.fn.__name__, exc, exc_info=True)
            try:
                self.signals.error.emit(str(exc))
            except RuntimeError:
                pass


# ── Extraction des métriques de session ──────────────────────────────────────

def extract_session_metrics(session: fastf1.core.Session) -> dict[str, Any]:
    """Extrait les métriques clés d'une session pour affichage dans le bandeau."""
    metrics: dict[str, Any] = {
        "event_name": str(session.event.get("EventName", "Grand Prix")),
        "year": int(session.event.year),
        "session_name": str(session.name),
        "winner": "—",
        "winner_team": "—",
        "fastest_driver": "—",
        "fastest_time": "—",
        "total_laps": 0,
        "drivers_count": len(session.drivers),
        "air_temp": None,
        "track_temp": None,
    }

    try:
        if hasattr(session, "results") and not session.results.empty:
            first = session.results.iloc[0]
            metrics["winner"] = str(first.get("FullName") or first.get("Abbreviation", "—"))
            metrics["winner_team"] = str(first.get("TeamName", "—"))
    except Exception as exc:
        log.debug("Impossible d'extraire le vainqueur: %s", exc)

    try:
        if hasattr(session, "laps") and not session.laps.empty:
            metrics["total_laps"] = int(session.laps["LapNumber"].max())
            quick = session.laps.pick_fastest()
            if quick is not None and not pd.isna(quick.get("LapTime")):
                time_str = str(quick["LapTime"]).split()[-1][:11]
                metrics["fastest_driver"] = str(quick.get("Driver", "—"))
                metrics["fastest_time"] = time_str
    except Exception as exc:
        log.debug("Impossible d'extraire le tour rapide: %s", exc)

    try:
        if hasattr(session, "weather_data") and not session.weather_data.empty:
            w = session.weather_data
            if "AirTemp" in w.columns and not w["AirTemp"].dropna().empty:
                metrics["air_temp"] = round(float(w["AirTemp"].mean()), 1)
            if "TrackTemp" in w.columns and not w["TrackTemp"].dropna().empty:
                metrics["track_temp"] = round(float(w["TrackTemp"].mean()), 1)
    except Exception as exc:
        log.debug("Météo non disponible: %s", exc)

    return metrics


# ── DataManager ──────────────────────────────────────────────────────────────

class DataManager(QObject):
    """
    Gestionnaire central des données FastF1.
    Toutes les opérations d'E/S et réseau sont asynchrones.
    """

    schedule_ready = pyqtSignal(object)   # list[dict] ou list[str]
    drivers_ready  = pyqtSignal(object)   # list[dict] avec code, nom, écurie, couleur
    session_ready  = pyqtSignal(object)   # fastf1.core.Session
    error          = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool: QThreadPool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(3)

        # Cache : { (year, gp, session_type) -> fastf1.Session }
        self._session_cache: dict[tuple, fastf1.core.Session] = {}
        # Références fortes pour éviter la suppression GC prématurée
        self._active_workers: set[_Worker] = set()

    def _run_worker(self, fn, *args, on_result=None, on_error=None, **kwargs) -> _Worker:
        """Lance un worker et conserve une référence active jusqu'à la fin."""
        w = _Worker(fn, *args, **kwargs)
        if on_result:
            w.signals.result.connect(on_result)
        if on_error:
            w.signals.error.connect(on_error)

        def _cleanup(*_):
            self._active_workers.discard(w)

        w.signals.result.connect(_cleanup)
        w.signals.error.connect(_cleanup)
        self._active_workers.add(w)
        self._pool.start(w)
        return w

    # ── API publique ─────────────────────────────────────────────────────────

    def fetch_schedule(self, year: int) -> None:
        """Charge le calendrier d'une saison de façon asynchrone."""
        self._run_worker(
            self._load_schedule, year,
            on_result=self.schedule_ready,
            on_error=self.error
        )

    def fetch_drivers(self, year: int, gp: str, session_type: str = "R") -> None:
        """Charge les pilotes participants pour un GP."""
        self._run_worker(
            self._load_drivers, year, gp, session_type,
            on_result=self.drivers_ready,
            on_error=self.error
        )

    def fetch_session(self, year: int, gp: str, session_type: str = "R") -> None:
        """Charge une session complète avec métriques."""
        key = (year, gp, session_type)
        if key in self._session_cache:
            log.debug("Session trouvée en cache mémoire: %s", key)
            self.session_ready.emit(self._session_cache[key])
            return

        def _on_loaded(session):
            self._session_cache[key] = session
            self.session_ready.emit(session)

        self._run_worker(
            self._load_session, year, gp, session_type,
            on_result=_on_loaded,
            on_error=self.error
        )

    def get_cached_session(
        self, year: int, gp: str, session_type: str = "R"
    ) -> Optional[fastf1.core.Session]:
        return self._session_cache.get((year, gp, session_type))

    def clear_cache(self) -> None:
        self._session_cache.clear()
        log.info("Cache mémoire vidé")

    # ── Workers internes ─────────────────────────────────────────────────────

    @staticmethod
    def _load_schedule(year: int) -> list[dict]:
        log.info("Chargement du calendrier F1 %d…", year)
        charts._ensure_season_constants(year)
        schedule = None

        # Tentative standard puis backend fastf1 direct
        try:
            schedule = fastf1.get_event_schedule(year, include_testing=False)
        except Exception as exc:
            log.warning("Échec get_event_schedule par défaut (%s), essai backend='fastf1'", exc)
            try:
                schedule = fastf1.get_event_schedule(year, backend="fastf1", include_testing=False)
            except Exception as exc2:
                raise ValueError(
                    f"Impossible de récupérer le calendrier pour la saison {year}. "
                    "Vérifiez votre connexion internet."
                )

        if schedule is None or schedule.empty:
            raise ValueError(f"Aucune course trouvée pour la saison {year}.")

        events = []
        for _, row in schedule.iterrows():
            rnd = row.get("RoundNumber")
            rnd_num = int(rnd) if pd.notna(rnd) else 0
            ev_name = str(row.get("EventName", "Grand Prix"))
            events.append({
                "round": rnd_num,
                "name": ev_name,
                "country": str(row.get("Country", "")),
                "location": str(row.get("Location", "")),
                "date": str(row.get("EventDate", ""))[:10],
                "format": str(row.get("EventFormat", "conventional")),
            })

        log.info("%d GP chargés avec succès pour %d", len(events), year)
        return events

    def _load_drivers(self, year: int, gp: str, session_type: str = "R") -> list[dict]:
        """Extrait la liste détaillée des pilotes."""
        key = (year, gp, session_type)
        session = self._session_cache.get(key)
        charts._ensure_season_constants(year)

        if session is None:
            log.info("Chargement des informations pilotes pour %d %s %s", year, gp, session_type)
            try:
                session = fastf1.get_session(year, gp, session_type)
                session.load(laps=False, telemetry=False, weather=False, messages=False)
            except Exception as exc:
                log.warning("Erreur chargement session pilotes: %s", exc)
                return []

        drivers_list: list[dict] = []
        for drv_id in session.drivers:
            try:
                drv = session.get_driver(drv_id)
                code = str(drv.get("Abbreviation", drv_id))
                name = str(drv.get("FullName", code))
                team = str(drv.get("TeamName", "Écurie"))
                color = charts.get_safe_driver_color(code, session)
                drivers_list.append({
                    "id": str(drv_id),
                    "code": code,
                    "name": name,
                    "team": team,
                    "color": color,
                })
            except Exception as exc:
                log.debug("Erreur extraction pilote %s: %s", drv_id, exc)

        log.info("%d pilotes configurés", len(drivers_list))
        return drivers_list

    @staticmethod
    def _load_session(year: int, gp: str, session_type: str) -> fastf1.core.Session:
        log.info("Chargement complet session %d %s [%s]", year, gp, session_type)
        charts._ensure_season_constants(year)
        sess = fastf1.get_session(year, gp, session_type)

        try:
            sess.load(laps=True, telemetry=True, weather=True, messages=False)
        except Exception as exc:
            log.warning("Chargement avec télémétrie échoué (%s), repli sur laps uniquement", exc)
            try:
                sess.load(laps=True, telemetry=False, weather=False, messages=False)
            except Exception as exc2:
                raise ValueError(
                    f"Données non disponibles pour cette session ({session_type}). "
                    "Il est possible que la course n'ait pas encore eu lieu."
                )

        # Calcul des métriques de session
        sess.dashboard_metrics = extract_session_metrics(sess)
        log.info("Session %s chargée avec succès", sess.event["EventName"])
        return sess

    def _on_session_loaded(self, key: tuple, session: fastf1.core.Session) -> None:
        self._session_cache[key] = session
        self.session_ready.emit(session)