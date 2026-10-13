"""cli.py : affichage de l'activité dans le terminal (étapes, spinner, durées).

Aucune dépendance. Les étapes sont thread-safe : les chargements FastF1 tournent dans
des threads de travail, le spinner continue de tourner pendant ce temps.
"""

import logging
import os
import sys
import threading
import time
from contextlib import contextmanager

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_TTY = sys.stdout.isatty()
if _TTY and os.name == "nt":
    os.system("")                       # active les séquences ANSI sous Windows


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def green(s): return _c("32", s)
def red(s): return _c("31", s)
def yellow(s): return _c("33", s)
def dim(s): return _c("2", s)
def bold(s): return _c("1", s)


_FRAMES = "|/-\\"
_lock = threading.RLock()
_active: list[list] = []                # [label, t0]
_spinner_started = False


def _fmt(sec: float) -> str:
    return f"{sec:.1f}s" if sec < 60 else f"{int(sec // 60)}m{int(sec % 60):02d}s"


def _spin() -> None:
    i = 0
    while True:
        time.sleep(0.1)
        with _lock:
            if not _active:
                continue
            label, t0 = _active[-1]
            extra = f" (+{len(_active) - 1})" if len(_active) > 1 else ""
            sys.stdout.write(f"\r\033[2K  [{yellow(_FRAMES[i % 4])}] {label}{extra} {dim(_fmt(time.time() - t0))}")
            sys.stdout.flush()
        i += 1


def _ensure_spinner() -> None:
    global _spinner_started
    if _TTY and not _spinner_started:
        _spinner_started = True
        threading.Thread(target=_spin, daemon=True).start()


def line(text: str = "") -> None:
    """Imprime une ligne complète sans casser le spinner."""
    with _lock:
        if _TTY:
            sys.stdout.write("\r\033[2K")
        print(text)
        sys.stdout.flush()


@contextmanager
def step(label: str):
    """Affiche une étape avec spinner, puis OK/ECHEC et sa durée."""
    entry = [label, time.time()]
    with _lock:
        _active.append(entry)
        if not _TTY:
            print(f"  [..] {label}", flush=True)
    _ensure_spinner()
    try:
        yield
    except BaseException as exc:
        with _lock:
            _active.remove(entry)
        line(f"  [{red('ECHEC')}] {label} {dim(_fmt(time.time() - entry[1]))}")
        line(f"          {red(type(exc).__name__)}: {exc}")
        raise
    else:
        with _lock:
            _active.remove(entry)
        line(f"  [{green(' OK ')}] {label} {dim(_fmt(time.time() - entry[1]))}")


def info(text: str) -> None:
    line(f"  [{dim('..')}] {text}")


def warn(text: str) -> None:
    line(f"  [{yellow('WARN')}] {text}")


class ConsoleHandler(logging.Handler):
    """Fait passer les warnings/erreurs des logs par le même canal que les étapes."""

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if record.levelno >= logging.ERROR:
            line(f"  [{red('ERR ')}] {record.name}: {msg}")
        elif record.levelno >= logging.WARNING:
            line(f"  [{yellow('WARN')}] {record.name}: {msg}")