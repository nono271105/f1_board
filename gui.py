"""
gui.py — Interface utilisateur F1 Dashboard moderne et polie

Architecture :
  MainWindow
    ├── HeaderBar (Titre, Sélecteur de saison & session, Actions d'export)
    ├── MetricsBanner (Cartes de statistiques : Vainqueur, Tour rapide, Météo, Tours)
    ├── MainSplitter
    │     ├── Sidebar (Filtre GP, Liste des GP, Choix du graphique, Pilotes avec couleurs d'écurie)
    │     └── ChartArea (Canvas Matplotlib + Toolbar de navigation sombre interactive)
    └── StatusBar (Indicateur de statut & barre de chargement)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Any

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt, QRunnable, QThreadPool, QObject, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon, QPainter, QBrush
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QComboBox,
    QVBoxLayout,
    QWidget,
    QProgressBar,
)

from data import DataManager, AVAILABLE_YEARS, SESSION_TYPES
from charts import build_chart, CHART_LABELS

log = logging.getLogger(__name__)

# ── Design Tokens (Thème F1 Pro Dark) ────────────────────────────────────────

T = {
    "bg_base":          "#0a0b0d",
    "bg_sidebar":       "#101217",
    "bg_card":          "#151820",
    "bg_card_hover":    "#1c202a",
    "bg_input":         "#181b22",
    "border":           "#222732",
    "border_focus":     "#384050",
    "accent":           "#e10600",        # Rouge officiel Formule 1
    "accent_hover":     "#ff1e18",
    "accent_dim":       "#7a0805",
    "gold":             "#f5a623",        # Or (pole / tour rapide)
    "text_main":        "#f8f9fa",
    "text_muted":       "#8b949e",
    "text_dim":         "#565f6c",
    "success":          "#00e676",
}

_FONT_FAMILY = "Helvetica Neue, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"


# ── Worker de rendu graphique (exécuté dans QThreadPool) ──────────────────────

class _ChartSignals(QObject):
    done  = pyqtSignal(object)
    error = pyqtSignal(str)


class _ChartWorker(QRunnable):
    def __init__(self, chart_type: str, session: Any, drivers: list[str]):
        super().__init__()
        self.chart_type = chart_type
        self.session    = session
        self.drivers    = drivers
        self.signals    = _ChartSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        try:
            fig = build_chart(self.chart_type, self.session, self.drivers)
            if fig is not None:
                try:
                    self.signals.done.emit(fig)
                except RuntimeError:
                    pass
            else:
                try:
                    self.signals.error.emit(
                        f"Données insuffisantes pour générer la visualisation « {self.chart_type} »."
                    )
                except RuntimeError:
                    pass
        except Exception as exc:
            log.error("Erreur lors de la génération du graphique: %s", exc, exc_info=True)
            try:
                self.signals.error.emit(str(exc))
            except RuntimeError:
                pass


# ── Barre d'outils Matplotlib en thème sombre ─────────────────────────────────

class DarkNavToolbar(NavigationToolbar2QT):
    """Barre de navigation Matplotlib adaptée au thème sombre."""

    def __init__(self, canvas, parent=None):
        super().__init__(canvas, parent)
        self.setStyleSheet(
            f"QToolBar {{"
            f"  background: {T['bg_sidebar']}; border: none; border-bottom: 1px solid {T['border']};"
            f"  padding: 4px 10px; spacing: 8px;"
            f"}}"
            f"QToolButton {{"
            f"  background: transparent; color: {T['text_main']}; border-radius: 4px; padding: 4px;"
            f"}}"
            f"QToolButton:hover {{"
            f"  background: {T['bg_card_hover']};"
            f"}}"
            f"QLabel {{"
            f"  color: {T['text_muted']}; font-size: 11px;"
            f"}}"
        )


# ── Canvas Matplotlib ─────────────────────────────────────────────────────────

class ChartCanvas(QWidget):
    """Conteneur principal pour le graphique avec toolbar et états interactifs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._canvas: Optional[FigureCanvasQTAgg] = None
        self._toolbar: Optional[DarkNavToolbar]   = None
        self._figure: Optional[Figure]             = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._init_placeholder()

    def _init_placeholder(self) -> None:
        self._placeholder_widget = QWidget()
        ph_layout = QVBoxLayout(self._placeholder_widget)
        ph_layout.setAlignment(Qt.AlignCenter)
        ph_layout.setSpacing(12)

        icon_lbl = QLabel("🏎️")
        icon_lbl.setFont(QFont("Arial", 42))
        icon_lbl.setAlignment(Qt.AlignCenter)
        ph_layout.addWidget(icon_lbl)

        title_lbl = QLabel("Prêt pour la télémétrie")
        title_lbl.setFont(QFont("Helvetica Neue", 16, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {T['text_main']};")
        title_lbl.setAlignment(Qt.AlignCenter)
        ph_layout.addWidget(title_lbl)

        sub_lbl = QLabel("Sélectionnez un Grand Prix et cliquez sur « Générer l'analyse » dans le panneau latéral.")
        sub_lbl.setFont(QFont("Helvetica Neue", 12))
        sub_lbl.setStyleSheet(f"color: {T['text_muted']}; max-width: 500px;")
        sub_lbl.setWordWrap(True)
        sub_lbl.setAlignment(Qt.AlignCenter)
        ph_layout.addWidget(sub_lbl)

        self._layout.addWidget(self._placeholder_widget)

    def set_figure(self, fig: Figure) -> None:
        self._clear_content()
        self._figure = fig

        self._canvas = FigureCanvasQTAgg(fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._toolbar = DarkNavToolbar(self._canvas, self)
        self._layout.addWidget(self._toolbar)
        self._layout.addWidget(self._canvas)
        self._canvas.draw()

    def get_figure(self) -> Optional[Figure]:
        return self._figure

    def _clear_content(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()


# ── Bandeau de métriques de session ───────────────────────────────────────────

class MetricsBanner(QFrame):
    """Bandeau de cartes statistiques affichant les faits marquants du GP."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(74)
        self.setStyleSheet(
            f"QFrame {{"
            f"  background: {T['bg_sidebar']}; border-bottom: 1px solid {T['border']};"
            f"}}"
        )
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(14)

        self.card_winner  = self._create_card("🏆  VAINQUEUR / POLE", "—", "En attente de session")
        self.card_fastest = self._create_card("⚡  MEILLEUR TOUR", "—", "—")
        self.card_laps    = self._create_card("🏁  DISTANCE", "—", "—")
        self.card_weather = self._create_card("🌤️  CONDITIONS PISTE", "—", "Météo")

        layout.addWidget(self.card_winner)
        layout.addWidget(self.card_fastest)
        layout.addWidget(self.card_laps)
        layout.addWidget(self.card_weather)

    def _create_card(self, title: str, val_text: str, sub_text: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{"
            f"  background: {T['bg_card']}; border: 1px solid {T['border']};"
            f"  border-radius: 6px; padding: 4px 10px;"
            f"}}"
        )
        l = QVBoxLayout(card)
        l.setContentsMargins(8, 4, 8, 4)
        l.setSpacing(2)

        t_lbl = QLabel(title)
        t_lbl.setFont(QFont("Helvetica Neue", 8, QFont.Bold))
        t_lbl.setStyleSheet(f"color: {T['text_muted']}; letter-spacing: 1px;")

        v_lbl = QLabel(val_text)
        v_lbl.setFont(QFont("Helvetica Neue", 12, QFont.Bold))
        v_lbl.setStyleSheet(f"color: {T['text_main']};")

        s_lbl = QLabel(sub_text)
        s_lbl.setFont(QFont("Helvetica Neue", 8))
        s_lbl.setStyleSheet(f"color: {T['text_dim']};")

        l.addWidget(t_lbl)
        l.addWidget(v_lbl)
        l.addWidget(s_lbl)

        card._val_lbl = v_lbl
        card._sub_lbl = s_lbl
        return card

    def update_metrics(self, m: dict[str, Any]) -> None:
        """Met à jour les cartes avec les données réelles de la session."""
        winner = m.get("winner", "—")
        winner_team = m.get("winner_team", "")
        self.card_winner._val_lbl.setText(winner)
        self.card_winner._sub_lbl.setText(winner_team or "Écurie non renseignée")

        fastest = m.get("fastest_driver", "—")
        f_time  = m.get("fastest_time", "—")
        self.card_fastest._val_lbl.setText(f"{fastest} ({f_time})" if fastest != "—" else "—")
        self.card_fastest._sub_lbl.setText("Meilleur temps en piste")

        laps = m.get("total_laps", 0)
        drivers = m.get("drivers_count", 0)
        self.card_laps._val_lbl.setText(f"{laps} Tours" if laps else "—")
        self.card_laps._sub_lbl.setText(f"{drivers} pilotes classés" if drivers else "—")

        t_track = m.get("track_temp")
        t_air   = m.get("air_temp")
        if t_track is not None and t_air is not None:
            self.card_weather._val_lbl.setText(f"Piste {t_track}°C • Air {t_air}°C")
            self.card_weather._sub_lbl.setText("Températures moyennes")
        else:
            self.card_weather._val_lbl.setText("Données météo n/a")
            self.card_weather._sub_lbl.setText("Non disponible")


# ── Barre d'en-tête (Header) ─────────────────────────────────────────────────

class HeaderBar(QFrame):
    """Barre supérieure avec logo, titre, sélecteur de session et exports."""

    year_changed    = pyqtSignal(int)
    session_changed = pyqtSignal(str)
    export_png      = pyqtSignal()
    export_pdf      = pyqtSignal()
    refresh         = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setStyleSheet(
            f"QFrame {{"
            f"  background: {T['bg_sidebar']}; border-bottom: 1px solid {T['border']};"
            f"}}"
        )
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 18, 0)
        layout.setSpacing(12)

        # ── Logo F1 ──
        logo_box = QLabel("F1")
        logo_box.setFont(QFont("Impact", 18))
        logo_box.setStyleSheet(
            f"background: {T['accent']}; color: white; border-radius: 4px; padding: 2px 8px;"
        )
        layout.addWidget(logo_box)

        title = QLabel("ANALYTICS DASHBOARD")
        title.setFont(QFont("Helvetica Neue", 12, QFont.Bold))
        title.setStyleSheet(f"color: {T['text_main']}; letter-spacing: 2px;")
        layout.addWidget(title)

        layout.addSpacing(16)

        # ── Sélecteur de Saison ──
        season_lbl = QLabel("SAISON")
        season_lbl.setFont(QFont("Helvetica Neue", 8, QFont.Bold))
        season_lbl.setStyleSheet(f"color: {T['text_muted']};")
        layout.addWidget(season_lbl)

        self.year_combo = QComboBox()
        self.year_combo.addItems([str(y) for y in reversed(AVAILABLE_YEARS)])
        self.year_combo.setFont(QFont("Helvetica Neue", 10, QFont.Bold))
        self.year_combo.setStyleSheet(self._combo_style())
        self.year_combo.currentTextChanged.connect(lambda y: self.year_changed.emit(int(y)))
        layout.addWidget(self.year_combo)

        layout.addSpacing(12)

        # ── Sélecteur de Type de Session (Course, Qualif, etc.) ──
        sess_lbl = QLabel("SESSION")
        sess_lbl.setFont(QFont("Helvetica Neue", 8, QFont.Bold))
        sess_lbl.setStyleSheet(f"color: {T['text_muted']};")
        layout.addWidget(sess_lbl)

        self.session_combo = QComboBox()
        for code, label in SESSION_TYPES.items():
            self.session_combo.addItem(label, code)
        self.session_combo.setFont(QFont("Helvetica Neue", 9))
        self.session_combo.setStyleSheet(self._combo_style())
        self.session_combo.currentIndexChanged.connect(
            lambda: self.session_changed.emit(self.session_combo.currentData())
        )
        layout.addWidget(self.session_combo)

        layout.addStretch()

        # ── Bouton Rafraîchir ──
        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setToolTip("Recharger les données de session")
        self.btn_refresh.setStyleSheet(self._button_icon_style())
        self.btn_refresh.clicked.connect(self.refresh)
        layout.addWidget(self.btn_refresh)

        # ── Boutons d'export ──
        self.btn_png = QPushButton("💾 Exporter PNG")
        self.btn_png.setFont(QFont("Helvetica Neue", 9, QFont.Bold))
        self.btn_png.setStyleSheet(self._button_action_style())
        self.btn_png.clicked.connect(self.export_png)
        layout.addWidget(self.btn_png)

        self.btn_pdf = QPushButton("📄 Exporter PDF")
        self.btn_pdf.setFont(QFont("Helvetica Neue", 9, QFont.Bold))
        self.btn_pdf.setStyleSheet(self._button_action_style())
        self.btn_pdf.clicked.connect(self.export_pdf)
        layout.addWidget(self.btn_pdf)

    def _combo_style(self) -> str:
        return (
            f"QComboBox {{"
            f"  background: {T['bg_input']}; color: {T['text_main']};"
            f"  border: 1px solid {T['border']}; border-radius: 4px; padding: 4px 10px;"
            f"}}"
            f"QComboBox:hover {{ border-color: {T['border_focus']}; }}"
            f"QComboBox QAbstractItemView {{"
            f"  background: {T['bg_card']}; color: {T['text_main']};"
            f"  selection-background-color: {T['accent_dim']}; outline: none;"
            f"}}"
        )

    def _button_action_style(self) -> str:
        return (
            f"QPushButton {{"
            f"  background: {T['bg_card']}; color: {T['text_main']};"
            f"  border: 1px solid {T['border']}; border-radius: 4px; padding: 6px 12px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: {T['bg_card_hover']}; border-color: {T['text_muted']};"
            f"}}"
            f"QPushButton:pressed {{ background: {T['accent_dim']}; }}"
        )

    def _button_icon_style(self) -> str:
        return (
            f"QPushButton {{"
            f"  background: {T['bg_card']}; color: {T['text_main']};"
            f"  border: 1px solid {T['border']}; border-radius: 4px; padding: 6px 10px;"
            f"}}"
            f"QPushButton:hover {{ background: {T['bg_card_hover']}; }}"
        )


# ── Panneau latéral (Sidebar) ─────────────────────────────────────────────────

class Sidebar(QWidget):
    """Panneau de configuration : sélection du GP, filtre pilotes et visualisations."""

    gp_changed         = pyqtSignal(str)
    visualizer_changed = pyqtSignal(str)
    generate_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self.setStyleSheet(
            f"background-color: {T['bg_sidebar']};"
            f"border-right: 1px solid {T['border']};"
        )
        self._all_gps: list[dict] = []
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # ── 1. Filtre & Sélection Grand Prix ──
        layout.addWidget(self._section_label("GRAND PRIX DE LA SAISON"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Filtrer un GP ou un pays…")
        self.search_input.setFont(QFont("Helvetica Neue", 9))
        self.search_input.setStyleSheet(
            f"QLineEdit {{"
            f"  background: {T['bg_input']}; color: {T['text_main']};"
            f"  border: 1px solid {T['border']}; border-radius: 4px; padding: 5px 8px;"
            f"}}"
            f"QLineEdit:focus {{ border-color: {T['accent']}; }}"
        )
        self.search_input.textChanged.connect(self._filter_gps)
        layout.addWidget(self.search_input)

        self.gp_list = QListWidget()
        self.gp_list.setStyleSheet(self._list_style())
        self.gp_list.setFixedHeight(180)
        self.gp_list.itemSelectionChanged.connect(self._on_gp_selected)
        layout.addWidget(self.gp_list)

        layout.addWidget(self._separator())

        # ── 2. Sélection de la Visualisation ──
        layout.addWidget(self._section_label("ANALYSE GRAPHIQUE"))

        self.viz_combo = QComboBox()
        for key, label in CHART_LABELS.items():
            self.viz_combo.addItem(label, key)
        self.viz_combo.setFont(QFont("Helvetica Neue", 9, QFont.Bold))
        self.viz_combo.setStyleSheet(
            f"QComboBox {{"
            f"  background: {T['bg_input']}; color: {T['text_main']};"
            f"  border: 1px solid {T['border']}; border-radius: 4px; padding: 6px 10px;"
            f"}}"
            f"QComboBox QAbstractItemView {{"
            f"  background: {T['bg_card']}; color: {T['text_main']};"
            f"  selection-background-color: {T['accent_dim']};"
            f"}}"
        )
        self.viz_combo.currentIndexChanged.connect(self._on_viz_changed)
        layout.addWidget(self.viz_combo)

        layout.addWidget(self._separator())

        # ── 3. Pilotes (avec pastilles couleur) ──
        pilotes_header = QHBoxLayout()
        pilotes_header.addWidget(self._section_label("PILOTES"))
        pilotes_header.addStretch()

        btn_all = QPushButton("Tous")
        btn_top5 = QPushButton("Top 5")
        btn_none = QPushButton("Aucun")
        for b in (btn_all, btn_top5, btn_none):
            b.setFont(QFont("Helvetica Neue", 8))
            b.setStyleSheet(
                f"QPushButton {{"
                f"  background: transparent; color: {T['text_muted']}; border: none; padding: 0 4px;"
                f"}}"
                f"QPushButton:hover {{ color: {T['accent']}; }}"
            )
        btn_all.clicked.connect(lambda: self._set_all_drivers_checked(True))
        btn_top5.clicked.connect(self._set_top5_drivers_checked)
        btn_none.clicked.connect(lambda: self._set_all_drivers_checked(False))
        pilotes_header.addWidget(btn_all)
        pilotes_header.addWidget(btn_top5)
        pilotes_header.addWidget(btn_none)
        layout.addLayout(pilotes_header)

        self.drivers_list = QListWidget()
        self.drivers_list.setStyleSheet(self._list_style())
        self.drivers_list.setMaximumHeight(150)
        layout.addWidget(self.drivers_list)

        layout.addStretch()

        # ── 4. Bouton d'action Générer ──
        self.gen_btn = QPushButton("▶   GÉNÉRER L'ANALYSE")
        self.gen_btn.setFont(QFont("Helvetica Neue", 10, QFont.Bold))
        self.gen_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e10600, stop:1 #b50400);"
            f"  color: white; border: none; border-radius: 6px; padding: 12px;"
            f"  letter-spacing: 1.5px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff1e18, stop:1 #d90500);"
            f"}}"
            f"QPushButton:pressed {{"
            f"  background: {T['accent_dim']};"
            f"}}"
            f"QPushButton:disabled {{"
            f"  background: {T['border']}; color: {T['text_dim']};"
            f"}}"
        )
        self.gen_btn.clicked.connect(self.generate_requested)
        layout.addWidget(self.gen_btn)

    # ── Helpers UI ───────────────────────────────────────────────────────────

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Helvetica Neue", 7, QFont.Bold))
        lbl.setStyleSheet(f"color: {T['text_muted']}; letter-spacing: 1.5px;")
        return lbl

    def _separator(self) -> QWidget:
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {T['border']};")
        return sep

    def _list_style(self) -> str:
        return (
            f"QListWidget {{"
            f"  background: {T['bg_input']}; color: {T['text_main']};"
            f"  border: 1px solid {T['border']}; border-radius: 4px; outline: none;"
            f"}}"
            f"QListWidget::item {{"
            f"  padding: 6px 8px; border-bottom: 1px solid #14171d;"
            f"}}"
            f"QListWidget::item:hover {{"
            f"  background: {T['bg_card_hover']};"
            f"}}"
            f"QListWidget::item:selected {{"
            f"  background: {T['bg_card']}; color: white;"
            f"  border-left: 3px solid {T['accent']};"
            f"}}"
        )

    # ── Remplissage des listes ────────────────────────────────────────────────

    def update_gp_list(self, gps: list[Any]) -> None:
        """Accepte soit une liste de dicts soit une liste de chaînes."""
        self._all_gps = []
        for item in gps:
            if isinstance(item, dict):
                self._all_gps.append(item)
            else:
                self._all_gps.append({"name": str(item), "round": 0, "country": ""})

        self._render_gp_list(self._all_gps)

    def _render_gp_list(self, events: list[dict]) -> None:
        self.gp_list.blockSignals(True)
        self.gp_list.clear()

        for ev in events:
            rnd = ev.get("round", 0)
            prefix = f"R{rnd:02d} • " if rnd else ""
            item = QListWidgetItem(f"{prefix}{ev['name']}")
            item.setData(Qt.UserRole, ev["name"])
            self.gp_list.addItem(item)

        if events:
            self.gp_list.setCurrentRow(0)
        self.gp_list.blockSignals(False)

        if events:
            self.gp_changed.emit(events[0]["name"])

    def _filter_gps(self, query: str) -> None:
        q = query.lower().strip()
        if not q:
            self._render_gp_list(self._all_gps)
            return

        filtered = [
            ev for ev in self._all_gps
            if q in ev.get("name", "").lower() or q in ev.get("country", "").lower()
        ]
        self._render_gp_list(filtered)

    def update_drivers_list(self, drivers: list[Any]) -> None:
        self.drivers_list.clear()
        for idx, drv in enumerate(drivers):
            if isinstance(drv, dict):
                code  = drv.get("code", "")
                team  = drv.get("team", "")
                text  = f"●  {code}  ({team})"
                color = drv.get("color", T["text_main"])
            else:
                code  = str(drv)
                text  = code
                color = T["text_main"]

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            # Par défaut, cocher les 4 premiers pour les graphiques comparatifs
            item.setCheckState(Qt.Checked if idx < 4 else Qt.Unchecked)
            self.drivers_list.addItem(item)

    def _set_all_drivers_checked(self, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.drivers_list.count()):
            self.drivers_list.item(i).setCheckState(state)

    def _set_top5_drivers_checked(self) -> None:
        for i in range(self.drivers_list.count()):
            self.drivers_list.item(i).setCheckState(Qt.Checked if i < 5 else Qt.Unchecked)

    def get_selected_gp(self) -> Optional[str]:
        item = self.gp_list.currentItem()
        if not item:
            return None
        return item.data(Qt.UserRole) or item.text()

    def get_selected_drivers(self) -> list[str]:
        selected = []
        for i in range(self.drivers_list.count()):
            it = self.drivers_list.item(i)
            if it.checkState() == Qt.Checked:
                code = it.data(Qt.UserRole) or it.text()
                selected.append(code)
        return selected

    def get_chart_type(self) -> str:
        return self.viz_combo.currentData() or "laptimes"

    # ── Slots internes ────────────────────────────────────────────────────────

    def _on_gp_selected(self) -> None:
        gp = self.get_selected_gp()
        if gp:
            self.gp_changed.emit(gp)

    def _on_viz_changed(self) -> None:
        self.visualizer_changed.emit(self.get_chart_type())


# ── Barre de statut moderne ───────────────────────────────────────────────────

class ModernStatusBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet(
            f"QFrame {{"
            f"  background: {T['bg_sidebar']}; border-top: 1px solid {T['border']};"
            f"}}"
        )
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)

        self._dot = QLabel("●")
        self._dot.setFont(QFont("Arial", 8))
        self._dot.setStyleSheet(f"color: {T['success']}; margin-right: 4px;")
        layout.addWidget(self._dot)

        self._msg_lbl = QLabel("Prêt")
        self._msg_lbl.setFont(QFont("Helvetica Neue", 9))
        self._msg_lbl.setStyleSheet(f"color: {T['text_muted']};")
        layout.addWidget(self._msg_lbl)

        layout.addStretch()

        self._progress = QProgressBar()
        self._progress.setFixedWidth(140)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {T['border']}; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {T['accent']}; border-radius: 3px; }}"
        )
        layout.addWidget(self._progress)

    def set_status(self, text: str, loading: bool = False, is_error: bool = False) -> None:
        self._msg_lbl.setText(text)
        self._progress.setVisible(loading)
        if is_error:
            self._dot.setStyleSheet("color: #ff3b30;")
        elif loading:
            self._dot.setStyleSheet(f"color: {T['gold']};")
        else:
            self._dot.setStyleSheet(f"color: {T['success']};")


# ── Fenêtre principale (MainWindow) ───────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("F1 Dashboard — Analyse télémétrique & stratégique")
        self.setMinimumSize(1280, 800)
        self.setStyleSheet(f"background: {T['bg_base']}; color: {T['text_main']};")

        self._data = DataManager(self)
        self._pool = QThreadPool.globalInstance()

        self._current_year: int       = AVAILABLE_YEARS[-1]
        self._current_session_type: str = "R"
        self._current_gp: Optional[str]  = None
        self._current_fig: Optional[Figure] = None
        self._active_workers: set = set()

        self._build_ui()
        self._connect_signals()

        # Initialisation : chargement de la saison par défaut
        self._sidebar.search_input.clear()
        self._data.fetch_schedule(self._current_year)

    # ── Construction de l'interface ──────────────────────────────────────────

    def _build_ui(self) -> None:
        root_widget = QWidget()
        root_layout = QVBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. En-tête
        self._header = HeaderBar(self)
        root_layout.addWidget(self._header)

        # 2. Bandeau de métriques rapides
        self._metrics_banner = MetricsBanner(self)
        root_layout.addWidget(self._metrics_banner)

        # 3. Zone centrale (Splitter Sidebar / Canvas)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {T['border']}; width: 1px; }}"
        )

        self._sidebar = Sidebar()
        splitter.addWidget(self._sidebar)

        self._chart_canvas = ChartCanvas()
        splitter.addWidget(self._chart_canvas)
        splitter.setStretchFactor(1, 4)

        root_layout.addWidget(splitter, stretch=1)

        # 4. Barre de statut
        self._status_bar = ModernStatusBar(self)
        root_layout.addWidget(self._status_bar)

        self.setCentralWidget(root_widget)

    # ── Connexion des signaux ────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        # Header
        self._header.year_changed.connect(self._on_year_changed)
        self._header.session_changed.connect(self._on_session_type_changed)
        self._header.export_png.connect(lambda: self._export_chart("png"))
        self._header.export_pdf.connect(lambda: self._export_chart("pdf"))
        self._header.refresh.connect(self._on_refresh)

        # Sidebar
        self._sidebar.gp_changed.connect(self._on_gp_changed)
        self._sidebar.generate_requested.connect(self._on_generate)

        # DataManager
        self._data.schedule_ready.connect(self._on_schedule_ready)
        self._data.drivers_ready.connect(self._sidebar.update_drivers_list)
        self._data.session_ready.connect(self._on_session_ready)
        self._data.error.connect(self._on_data_error)

    # ── Gestion des actions et événements ─────────────────────────────────────

    def _on_year_changed(self, year: int) -> None:
        self._current_year = year
        self._current_gp   = None
        self._status_bar.set_status(f"Chargement du calendrier {year}…", loading=True)
        self._data.fetch_schedule(year)

    def _on_session_type_changed(self, session_type: str) -> None:
        self._current_session_type = session_type
        if self._current_gp:
            self._status_bar.set_status(f"Actualisation pilotes pour session {session_type}…", loading=True)
            self._data.fetch_drivers(self._current_year, self._current_gp, self._current_session_type)

    def _on_gp_changed(self, gp: str) -> None:
        self._current_gp = gp
        self._status_bar.set_status(f"Chargement des pilotes — {gp}…", loading=True)
        self._data.fetch_drivers(self._current_year, gp, self._current_session_type)

    def _on_refresh(self) -> None:
        self._data.clear_cache()
        if self._current_gp:
            self._on_generate()

    def _on_generate(self) -> None:
        if not self._current_gp:
            self._status_bar.set_status("Veuillez sélectionner un Grand Prix dans la liste.", is_error=True)
            return

        chart_type   = self._sidebar.get_chart_type()
        gp           = self._current_gp
        year         = self._current_year
        session_type = self._current_session_type

        self._status_bar.set_status(f"Téléchargement session {year} {gp} [{session_type}]…", loading=True)
        self._sidebar.gen_btn.setEnabled(False)

        self._pending_chart   = chart_type
        self._pending_drivers = self._sidebar.get_selected_drivers()
        self._data.fetch_session(year, gp, session_type)

    def _on_schedule_ready(self, gps: list[Any]) -> None:
        self._sidebar.update_gp_list(gps)
        self._status_bar.set_status(f"{len(gps)} Grands Prix chargés avec succès.")

    def _on_session_ready(self, session: Any) -> None:
        # Mise à jour des cartes métriques
        metrics = getattr(session, "dashboard_metrics", {})
        if metrics:
            self._metrics_banner.update_metrics(metrics)

        self._status_bar.set_status("Génération du rendu graphique haute précision…", loading=True)
        chart_type = getattr(self, "_pending_chart", "laptimes")
        drivers    = getattr(self, "_pending_drivers", [])

        worker = _ChartWorker(chart_type, session, drivers)
        worker.signals.done.connect(self._on_chart_ready)
        worker.signals.error.connect(self._on_chart_error)

        def _cleanup(*_):
            self._active_workers.discard(worker)

        worker.signals.done.connect(_cleanup)
        worker.signals.error.connect(_cleanup)
        self._active_workers.add(worker)
        self._pool.start(worker)

    def _on_chart_ready(self, fig: Figure) -> None:
        self._current_fig = fig
        self._chart_canvas.set_figure(fig)
        self._status_bar.set_status("Visualisation générée avec succès.")
        self._sidebar.gen_btn.setEnabled(True)

    def _on_chart_error(self, err_msg: str) -> None:
        log.error("Erreur graphique: %s", err_msg)
        self._status_bar.set_status(f"Erreur graphique : {err_msg}", is_error=True)
        self._sidebar.gen_btn.setEnabled(True)
        QMessageBox.warning(self, "Visualisation impossible", err_msg)

    def _on_data_error(self, err_msg: str) -> None:
        log.error("Erreur données: %s", err_msg)
        self._status_bar.set_status(f"Erreur données : {err_msg}", is_error=True)
        self._sidebar.gen_btn.setEnabled(True)
        QMessageBox.critical(self, "Erreur de données F1", err_msg)

    def _export_chart(self, fmt: str) -> None:
        fig = self._chart_canvas.get_figure()
        if fig is None:
            QMessageBox.information(
                self, "Aucun graphique", "Générez d'abord une visualisation avant de l'exporter."
            )
            return

        filter_str = f"{fmt.upper()} (*.{fmt})"
        default_name = f"f1_{self._current_year}_{self._current_gp}_{self._sidebar.get_chart_type()}.{fmt}"
        filepath, _ = QFileDialog.getSaveFileName(
            self, f"Exporter le graphique en {fmt.upper()}", default_name, filter_str
        )
        if not filepath:
            return

        try:
            fig.savefig(
                filepath, dpi=300, format=fmt,
                bbox_inches="tight", facecolor=T["bg_base"], edgecolor="none"
            )
            self._status_bar.set_status(f"Graphique exporté : {filepath}")
            QMessageBox.information(self, "Export réussi", f"Le fichier a été enregistré sous :\n{filepath}")
        except Exception as exc:
            log.error("Échec export %s: %s", fmt, exc)
            QMessageBox.critical(self, "Erreur d'export", f"Impossible d'enregistrer le fichier : {exc}")

    def closeEvent(self, event) -> None:
        self._pool.waitForDone(2000)
        event.accept()