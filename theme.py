"""
theme.py : jetons de design, police et feuille de style Qt.

Direction : écran de chronométrage F1. Fond graphite, texte clair, un seul accent (rouge F1)
réservé aux indicateurs d'état actif. Les couleurs vives viennent des données (écuries,
gommes Pirelli, violet du meilleur tour). Aucun dégradé, aucune ombre.
"""

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

BG = "#16171b"        # fond des graphiques et de la zone centrale
PANEL = "#1c1d22"     # barre du haut et panneau latéral
RAISED = "#26272d"    # champs, survol, élément actif
LINE = "#33343b"      # filets et bordures
TEXT = "#ecedef"
MUTED = "#a0a1aa"
DIM = "#6d6e77"
RED = "#e10600"       # accent : élément actif uniquement
PURPLE = "#b24df0"    # meilleur tour (convention des écrans de chronométrage)
GREEN = "#2fd07a"

COMPOUNDS = {          # gommes Pirelli
    "SOFT": ("#ee3340", "Tendre"),
    "MEDIUM": ("#ffd12e", "Medium"),
    "HARD": ("#f2f2f0", "Dur"),
    "INTERMEDIATE": ("#43b02a", "Intermédiaire"),
    "WET": ("#2a8bd8", "Pluie"),
    "UNKNOWN": ("#6d6e77", "Inconnue"),
}

FONT = "Titillium Web"
_FALLBACK_FONT = "Helvetica Neue"
_loaded = False


def load_fonts() -> str:
    global _loaded
    families = []
    for ttf in sorted((Path(__file__).parent / "assets" / "fonts").glob("*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(ttf))
        if fid >= 0:
            families += QFontDatabase.applicationFontFamilies(fid)
    _loaded = FONT in families
    return FONT if _loaded else _FALLBACK_FONT


def font(size: float = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(FONT if _loaded else _FALLBACK_FONT)
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


STYLESHEET = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: 14px; }}
QLabel {{ background: transparent; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {LINE}; padding: 4px 6px; }}

QFrame#sidebar {{ background: {PANEL}; border-right: 1px solid {LINE}; }}
QFrame#sidebar QWidget {{ background: transparent; }}
QFrame#topbar {{ background: {PANEL}; border-bottom: 1px solid {LINE}; }}
QFrame#topbar QWidget {{ background: transparent; }}
QFrame#statusbar {{ background: {PANEL}; border-top: 1px solid {LINE}; }}
QFrame#statusbar QWidget {{ background: transparent; }}
QFrame#tabbar {{ background: {PANEL}; border-bottom: 1px solid {LINE}; }}
QFrame#tabbar QWidget {{ background: transparent; }}
QFrame#strip {{ background: {BG}; border-bottom: 1px solid {LINE}; }}
QFrame#strip QWidget {{ background: transparent; }}

QLabel#caption {{ color: {MUTED}; font-size: 12px; }}
QLabel#h1 {{ font-size: 26px; font-weight: 700; }}
QLabel#value {{ font-size: 17px; font-weight: 600; }}
QLabel#brand {{ font-size: 17px; font-weight: 700; }}
QLabel#hint {{ color: {MUTED}; font-size: 12px; }}
QLabel#msgtitle {{ font-size: 20px; font-weight: 600; }}
QLabel#msgbody {{ color: {MUTED}; font-size: 14px; }}
QLabel#readout {{ background: {PANEL}; border: 1px solid {LINE}; padding: 6px 8px; font-size: 12px; }}

QComboBox {{
    background: {RAISED}; border: 1px solid {LINE}; border-radius: 3px;
    padding: 5px 10px; min-height: 22px; font-weight: 600;
}}
QComboBox:hover, QComboBox:focus {{ border-color: {DIM}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {RAISED}; border: 1px solid {LINE};
    selection-background-color: {LINE}; selection-color: {TEXT}; outline: 0;
}}

QListWidget {{ background: transparent; border: none; outline: 0; }}
QListWidget::item {{ border: none; }}

QPushButton {{
    background: transparent; border: 1px solid {LINE}; border-radius: 3px;
    padding: 5px 12px; color: {TEXT};
}}
QPushButton:hover {{ background: {RAISED}; }}
QPushButton:focus {{ border-color: {DIM}; }}
QPushButton:disabled {{ color: {DIM}; background: transparent; }}

QPushButton#seg {{ padding: 5px 0; border: 1px solid {LINE}; border-bottom: 2px solid {LINE}; color: {MUTED}; }}
QPushButton#seg:checked {{ background: {RAISED}; color: {TEXT}; border-bottom: 2px solid {RED}; }}
QPushButton#seg:disabled {{ color: {DIM}; border-color: {LINE}; background: transparent; }}

QPushButton#tab {{
    border: none; border-bottom: 2px solid transparent; border-radius: 0;
    padding: 11px 16px; color: {MUTED};
}}
QPushButton#tab:hover {{ background: transparent; color: {TEXT}; }}
QPushButton#tab:checked {{ color: {TEXT}; border-bottom: 2px solid {RED}; }}
QPushButton#tab:disabled {{ color: {DIM}; }}

QPushButton#chip {{
    border: 1px solid {LINE}; border-left: 4px solid {DIM}; border-radius: 2px;
    padding: 3px 4px; color: {DIM}; font-weight: 600; min-width: 0;
}}
QPushButton#chip:checked {{ background: {RAISED}; color: {TEXT}; border-color: {DIM}; }}
QPushButton#chip:disabled {{ color: {DIM}; }}

QPushButton#link {{ border: none; padding: 2px 6px; color: {MUTED}; font-size: 12px; text-align: left; }}
QPushButton#link:hover {{ color: {TEXT}; background: transparent; }}

QPushButton#quick {{
    background: {RAISED}; border: 1px solid {LINE}; border-radius: 3px;
    padding: 2px 4px; color: {TEXT}; font-size: 11px; font-weight: 600;
    text-align: center;
}}
QPushButton#quick:hover {{ background: {LINE}; border-color: {DIM}; color: #ffffff; }}
QPushButton#quick:pressed {{ background: {RED}; border-color: {RED}; color: #ffffff; }}
QPushButton#quick:disabled {{ color: {DIM}; background: transparent; border-color: {LINE}; }}

QPushButton#tool {{ padding: 4px 12px; font-size: 13px; }}
QPushButton#tool:checked {{ background: {RAISED}; border-color: {DIM}; }}

QProgressBar {{ background: {LINE}; border: none; border-radius: 1px; max-height: 3px; }}
QProgressBar::chunk {{ background: {RED}; }}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {LINE}; min-height: 24px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: {DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
