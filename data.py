"""
data.py — Couche données F1

Responsabilités :
- Accès FastF1 (sessions, calendrier, pilotes)
- Cache en mémoire pour éviter les rechargements
- Workers Qt pour ne jamais bloquer l'UI
"""

from __future__ import annotations

import logging
from typing import Optional

import fastf1
import pandas as pd
from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot

log = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

AVAILABLE_YEARS: list[int] = list(range(2018, 2027))


# ── Signals wrapper (QRunnable n'hérite pas de QObject) ──────────────────────

class _WorkerSignals(QObject):
    # IMPORTANT : `object` évite le mismatch PyQt_PyObject <-> QVariantList
    result = pyqtSignal(object)
    error  = pyqtSignal(str)


# ── Worker générique ─────────────────────────────────────────────────────────

class _Worker(QRunnable):
    """Exécute `fn(*args, **kwargs)` dans le thread pool global."""

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
            self.signals.result.emit(result)
        except Exception as exc:
            log.error("Worker error: %s", exc, exc_info=True)
            self.signals.error.emit(str(exc))


# ── DataManager ──────────────────────────────────────────────────────────────

class DataManager(QObject):
    """
    Singleton-like gestionnaire de données F1.

    Toutes les opérations réseau/disque sont exécutées dans le QThreadPool
    global ; les résultats remontent via des signaux Qt.

    Cache mémoire sur les sessions chargées : une session déjà chargée
    n'est JAMAIS rechargée.
    """

    # Signaux publics — tous `object` pour éviter les incompatibilités
    # PyQt5 entre PyQt_PyObject et QVariantList/QVariantMap
    schedule_ready = pyqtSignal(object)   # list[str]
    drivers_ready  = pyqtSignal(object)   # list[str]
    session_ready  = pyqtSignal(object)   # fastf1.Session
    error          = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool: QThreadPool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(2)          # pas besoin de plus

        # Cache : { (year, gp, session_type) -> fastf1.Session }
        self._session_cache: dict[tuple, fastf1.core.Session] = {}

    # ── API publique ─────────────────────────────────────────────────────────

    def fetch_schedule(self, year: int) -> None:
        """Lance le chargement asynchrone du calendrier d'une saison."""
        w = _Worker(self._load_schedule, year)
        w.signals.result.connect(self.schedule_ready)
        w.signals.error.connect(self.error)
        self._pool.start(w)

    def fetch_drivers(self, year: int, gp: str) -> None:
        """Lance le chargement asynchrone des pilotes pour un GP."""
        w = _Worker(self._load_drivers, year, gp)
        w.signals.result.connect(self.drivers_ready)
        w.signals.error.connect(self.error)
        self._pool.start(w)

    def fetch_session(self, year: int, gp: str, session_type: str = "R") -> None:
        """
        Lance le chargement asynchrone d'une session.
        Si déjà en cache → émet `session_ready` immédiatement dans le thread courant.
        """
        key = (year, gp, session_type)
        if key in self._session_cache:
            log.debug("Cache hit %s", key)
            self.session_ready.emit(self._session_cache[key])
            return

        w = _Worker(self._load_session, year, gp, session_type)
        w.signals.result.connect(lambda s: self._on_session_loaded(key, s))
        w.signals.error.connect(self.error)
        self._pool.start(w)

    def get_cached_session(
        self, year: int, gp: str, session_type: str = "R"
    ) -> Optional[fastf1.core.Session]:
        """Retourne la session si déjà en cache, None sinon."""
        return self._session_cache.get((year, gp, session_type))

    def clear_cache(self) -> None:
        self._session_cache.clear()
        log.info("Cache mémoire vidé")

    # ── Méthodes privées (exécutées dans les workers) ────────────────────────

    @staticmethod
    def _load_schedule(year: int) -> list[str]:
        log.info("Chargement calendrier %d", year)
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        # On filtre les rounds déjà passés ou tous selon préférence
        names = schedule["EventName"].tolist()
        log.info("%d GP chargés pour %d", len(names), year)
        return names

    def _load_drivers(self, year: int, gp: str) -> list[str]:
        """Charge la liste des pilotes via la session en cache si dispo."""
        key = (year, gp, "R")
        session = self._session_cache.get(key)
        if session is None:
            log.info("Chargement session pilotes %d %s", year, gp)
            session = fastf1.get_session(year, gp, "R")
            # Chargement minimal : juste les résultats (pas la télémétrie)
            session.load(laps=False, telemetry=False, weather=False, messages=False)
        drivers = [
            session.get_driver(d)["Abbreviation"]
            for d in session.drivers
        ]
        log.info("%d pilotes chargés", len(drivers))
        return drivers

    @staticmethod
    def _load_session(year: int, gp: str, session_type: str) -> fastf1.core.Session:
        log.info("Chargement session %d %s %s", year, gp, session_type)
        sess = fastf1.get_session(year, gp, session_type)
        sess.load(laps=True, telemetry=True, weather=True, messages=False)
        log.info("Session chargée : %s", sess.event["EventName"])
        return sess

    def _on_session_loaded(self, key: tuple, session: fastf1.core.Session) -> None:
        self._session_cache[key] = session
        self.session_ready.emit(session)