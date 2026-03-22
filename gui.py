"""
gui.py — Interface utilisateur F1 Dashboard

Structure :
  MainWindow
    ├── Toolbar (export PNG)
    ├── Sidebar (année / GP / visualisation / pilotes)
    └── ChartArea (canvas matplotlib)

Tout est dans ce fichier pour garder l'UI centralisée.
Les workers de données sont dans data.py.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt, QRunnable, QThreadPool, QObject, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QComboBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QProgressBar,
)

from data import DataManager, AVAILABLE_YEARS
from charts import build_chart, CHART_LABELS

log = logging.getLogger(__name__)

# ── Thème ────────────────────────────────────────────────────────────────────

T = {
    "bg":          "#0d0d0d",
    "bg_panel":    "#161616",
    "bg_sidebar":  "#111111",
    "border":      "#2a2a2a",
    "accent":      "#e10600",        # Rouge F1
    "accent_dim":  "#8b0000",
    "text":        "#f0f0f0",
    "text_dim":    "#888888",
    "success":     "#00c853",
    "warning":     "#ff6d00",
}

_FONT_TITLE  = QFont("Helvetica Neue", 11, QFont.Bold)
_FONT_LABEL  = QFont("Helvetica Neue", 8)
_FONT_HEADER = QFont("Helvetica Neue", 9, QFont.Bold)

# ── Worker Qt pour la génération de graphiques ───────────────────────────────

class _ChartSignals(QObject):
    done  = pyqtSignal(object)
    error = pyqtSignal(str)


class _ChartWorker(QRunnable):
    def __init__(self, chart_type, session, drivers):
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
            if fig:
                self.signals.done.emit(fig)
            else:
                self.signals.error.emit(f"Impossible de générer « {self.chart_type} »")
        except Exception as exc:
            log.error("ChartWorker: %s", exc, exc_info=True)
            self.signals.error.emit(str(exc))


# ── Canvas matplotlib ─────────────────────────────────────────────────────────

class ChartCanvas(QWidget):
    """Conteneur pour le FigureCanvas matplotlib."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._canvas: Optional[FigureCanvasQTAgg] = None
        self._figure: Optional[Figure]             = None

        self._placeholder = QLabel("Sélectionnez un Grand Prix pour afficher le graphique")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(f"color: {T['text_dim']}; font-size: 14px;")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._placeholder)

    def set_figure(self, fig: Figure) -> None:
        """Remplace le canvas par une nouvelle figure."""
        # Supprime l'ancien widget
        self._clear_layout()

        self._figure = fig
        self._canvas = FigureCanvasQTAgg(fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._layout.addWidget(self._canvas)
        self._canvas.draw()

    def get_figure(self) -> Optional[Figure]:
        return self._figure

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()


# ── Sidebar ───────────────────────────────────────────────────────────────────

class Sidebar(QWidget):
    """Panneau gauche de contrôle."""

    year_changed        = pyqtSignal(int)
    gp_changed          = pyqtSignal(str)
    visualizer_changed  = pyqtSignal(str)
    drivers_changed     = pyqtSignal(list)
    generate_requested  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(230)
        self.setStyleSheet(
            f"background-color: {T['bg_sidebar']};"
            f"border-right: 1px solid {T['border']};"
        )
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(10)

        # ── Logo / titre ──
        logo = QLabel("F1")
        logo.setFont(QFont("Helvetica Neue", 28, QFont.Black))
        logo.setStyleSheet(f"color: {T['accent']}; letter-spacing: 3px;")
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)

        sub = QLabel("DASHBOARD")
        sub.setFont(QFont("Helvetica Neue", 8, QFont.Bold))
        sub.setStyleSheet(f"color: {T['text_dim']}; letter-spacing: 5px;")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)

        layout.addWidget(self._separator())

        # ── Année ──
        layout.addWidget(self._section_label("SAISON"))
        self.year_combo = self._combo([str(y) for y in reversed(AVAILABLE_YEARS)])
        self.year_combo.setCurrentText("2024")
        self.year_combo.currentTextChanged.connect(lambda y: self.year_changed.emit(int(y)))
        layout.addWidget(self.year_combo)

        # ── Grand Prix ──
        layout.addWidget(self._section_label("GRAND PRIX"))
        self.gp_list = QListWidget()
        self.gp_list.setStyleSheet(self._list_style())
        self.gp_list.setMaximumHeight(160)
        self.gp_list.itemSelectionChanged.connect(self._on_gp_selected)
        layout.addWidget(self.gp_list)

        # ── Visualisation ──
        layout.addWidget(self._section_label("VISUALISATION"))
        self.viz_combo = self._combo(list(CHART_LABELS.values()))
        self.viz_combo.currentIndexChanged.connect(self._on_viz_changed)
        layout.addWidget(self.viz_combo)

        # ── Pilotes (pour Driver Laptimes) ──
        layout.addWidget(self._section_label("PILOTES (Driver Styling)"))
        self.drivers_list = QListWidget()
        self.drivers_list.setStyleSheet(self._list_style())
        self.drivers_list.setMaximumHeight(130)
        layout.addWidget(self.drivers_list)

        layout.addStretch()

        # ── Bouton Générer ──
        self.gen_btn = QPushButton("▶  GÉNÉRER")
        self.gen_btn.setFont(QFont("Helvetica Neue", 9, QFont.Bold))
        self.gen_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: {T['accent']}; color: white; border: none;"
            f"  border-radius: 4px; padding: 10px; letter-spacing: 2px;"
            f"}}"
            f"QPushButton:hover {{ background: #ff1a14; }}"
            f"QPushButton:pressed {{ background: {T['accent_dim']}; }}"
            f"QPushButton:disabled {{ background: {T['border']}; color: {T['text_dim']}; }}"
        )
        self.gen_btn.clicked.connect(self.generate_requested)
        layout.addWidget(self.gen_btn)

    # ── Helpers UI ───────────────────────────────────────────────────────────

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Helvetica Neue", 7, QFont.Bold))
        lbl.setStyleSheet(f"color: {T['text_dim']}; letter-spacing: 2px; margin-top: 4px;")
        return lbl

    def _separator(self) -> QWidget:
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {T['border']};")
        return sep

    def _combo(self, items: list) -> QComboBox:
        cb = QComboBox()
        cb.addItems(items)
        cb.setFont(_FONT_LABEL)
        cb.setStyleSheet(
            f"QComboBox {{"
            f"  background: {T['bg_panel']}; color: {T['text']}; border: 1px solid {T['border']};"
            f"  border-radius: 3px; padding: 5px 8px;"
            f"}}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{"
            f"  background: {T['bg_panel']}; color: {T['text']};"
            f"  selection-background-color: {T['accent_dim']};"
            f"}}"
        )
        return cb

    def _list_style(self) -> str:
        return (
            f"QListWidget {{"
            f"  background: {T['bg_panel']}; color: {T['text']}; border: 1px solid {T['border']};"
            f"  border-radius: 3px; outline: none;"
            f"}}"
            f"QListWidget::item {{ padding: 4px 8px; }}"
            f"QListWidget::item:selected {{"
            f"  background: {T['accent_dim']}; color: white;"
            f"}}"
            f"QListWidget::item:hover {{ background: #222; }}"
        )

    # ── Mise à jour des listes ────────────────────────────────────────────────

    def update_gp_list(self, gps: list[str]) -> None:
        self.gp_list.blockSignals(True)
        self.gp_list.clear()
        for gp in gps:
            self.gp_list.addItem(gp)
        if gps:
            self.gp_list.setCurrentRow(0)
        self.gp_list.blockSignals(False)
        # Émettre manuellement après avoir rempli
        if gps:
            self.gp_changed.emit(gps[0])

    def update_drivers_list(self, drivers: list[str]) -> None:
        self.drivers_list.clear()
        for drv in drivers:
            item = QListWidgetItem(drv)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.drivers_list.addItem(item)

    def get_selected_gp(self) -> Optional[str]:
        item = self.gp_list.currentItem()
        return item.text() if item else None

    def get_selected_drivers(self) -> list[str]:
        result = []
        for i in range(self.drivers_list.count()):
            item = self.drivers_list.item(i)
            if item.checkState() == Qt.Checked:
                result.append(item.text())
        return result

    def get_chart_type(self) -> str:
        idx = self.viz_combo.currentIndex()
        return list(CHART_LABELS.keys())[idx]

    # ── Slots internes ────────────────────────────────────────────────────────

    def _on_gp_selected(self):
        gp = self.get_selected_gp()
        if gp:
            self.gp_changed.emit(gp)

    def _on_viz_changed(self):
        self.visualizer_changed.emit(self.get_chart_type())


# ── Toolbar ───────────────────────────────────────────────────────────────────

class Toolbar(QToolBar):
    export_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMovable(False)
        self.setStyleSheet(
            f"QToolBar {{"
            f"  background: {T['bg_panel']}; border-bottom: 1px solid {T['border']}; spacing: 0px;"
            f"}}"
        )

        title = QLabel("  F1 DASHBOARD")
        title.setFont(QFont("Helvetica Neue", 11, QFont.Black))
        title.setStyleSheet(f"color: {T['accent']}; letter-spacing: 3px; padding: 0 10px;")
        self.addWidget(title)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)

        self.export_btn = QPushButton("⬇  Exporter PNG")
        self.export_btn.setFont(QFont("Helvetica Neue", 8, QFont.Bold))
        self.export_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent; color: {T['text_dim']}; border: 1px solid {T['border']};"
            f"  border-radius: 3px; padding: 6px 14px; margin-right: 12px;"
            f"}}"
            f"QPushButton:hover {{ color: {T['text']}; border-color: {T['text_dim']}; }}"
        )
        self.export_btn.clicked.connect(self.export_requested)
        self.addWidget(self.export_btn)


# ── Barre de statut personnalisée ─────────────────────────────────────────────

class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet(f"background: {T['bg_panel']}; border-top: 1px solid {T['border']};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)

        self._label = QLabel("Prêt")
        self._label.setFont(_FONT_LABEL)
        self._label.setStyleSheet(f"color: {T['text_dim']};")
        layout.addWidget(self._label)

        layout.addStretch()

        self._progress = QProgressBar()
        self._progress.setFixedWidth(120)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 0)   # mode indéfini
        self._progress.setVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {T['border']}; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {T['accent']}; border-radius: 3px; }}"
        )
        layout.addWidget(self._progress)

    def set_message(self, msg: str, loading: bool = False) -> None:
        self._label.setText(msg)
        self._progress.setVisible(loading)


# ── Fenêtre principale ────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("F1 Dashboard")
        self.setMinimumSize(1200, 750)
        self.setStyleSheet(f"background: {T['bg']}; color: {T['text']};")

        self._data  = DataManager(self)
        self._pool  = QThreadPool.globalInstance()

        self._current_year: int       = 2024
        self._current_gp:   Optional[str] = None
        self._current_fig:  Optional[Figure] = None

        self._build_ui()
        self._connect_signals()

        # Chargement initial
        self._data.fetch_schedule(self._current_year)

    # ── Construction de l'UI ─────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Toolbar
        self._toolbar = Toolbar(self)
        self.addToolBar(self._toolbar)

        # Contenu central
        central = QWidget()
        central.setStyleSheet(f"background: {T['bg']};")
        h_layout = QHBoxLayout(central)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(0)

        self._sidebar = Sidebar()
        h_layout.addWidget(self._sidebar)

        self._chart_area = ChartCanvas()
        self._chart_area.setStyleSheet(f"background: {T['bg']};")
        h_layout.addWidget(self._chart_area, stretch=1)

        self.setCentralWidget(central)

        # Barre de statut
        self._status = StatusBar()
        self.setStatusBar(None)          # désactive la QStatusBar native
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(central)
        main_layout.addWidget(self._status)
        wrapper = QWidget()
        wrapper.setLayout(main_layout)
        self.setCentralWidget(wrapper)

    # ── Connexions signaux / slots ────────────────────────────────────────────

    def _connect_signals(self) -> None:
        # Sidebar → MainWindow
        self._sidebar.year_changed.connect(self._on_year_changed)
        self._sidebar.gp_changed.connect(self._on_gp_changed)
        self._sidebar.generate_requested.connect(self._on_generate)

        # DataManager → MainWindow
        self._data.schedule_ready.connect(self._on_schedule_ready)
        self._data.drivers_ready.connect(self._sidebar.update_drivers_list)
        self._data.session_ready.connect(self._on_session_ready)
        self._data.error.connect(self._on_data_error)

        # Toolbar
        self._toolbar.export_requested.connect(self._on_export)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_year_changed(self, year: int) -> None:
        self._current_year = year
        self._current_gp   = None
        self._status.set_message(f"Chargement du calendrier {year}…", loading=True)
        self._data.fetch_schedule(year)

    def _on_gp_changed(self, gp: str) -> None:
        self._current_gp = gp
        self._status.set_message(f"Chargement des pilotes — {gp}…", loading=True)
        self._data.fetch_drivers(self._current_year, gp)

    def _on_generate(self) -> None:
        if not self._current_gp:
            self._status.set_message("Sélectionnez un Grand Prix d'abord")
            return

        chart_type = self._sidebar.get_chart_type()
        gp         = self._current_gp
        year       = self._current_year

        self._status.set_message(f"Chargement session {year} {gp}…", loading=True)
        self._sidebar.gen_btn.setEnabled(False)

        # fetch_session émettra session_ready (cache ou async)
        self._pending_chart  = chart_type
        self._pending_drivers = self._sidebar.get_selected_drivers()
        self._data.fetch_session(year, gp)

    def _on_schedule_ready(self, gps) -> None:
        self._sidebar.update_gp_list(gps)
        self._status.set_message(f"{len(gps)} Grand Prix chargés", loading=False)

    def _on_session_ready(self, session) -> None:
        """Session chargée → on lance la génération du graphique."""
        self._status.set_message("Génération du graphique…", loading=True)
        chart_type = getattr(self, "_pending_chart", "laptimes")
        drivers    = getattr(self, "_pending_drivers", [])

        worker = _ChartWorker(chart_type, session, drivers)
        worker.signals.done.connect(self._on_chart_ready)
        worker.signals.error.connect(self._on_chart_error)
        self._pool.start(worker)

    def _on_chart_ready(self, fig: Figure) -> None:
        self._current_fig = fig
        self._chart_area.set_figure(fig)
        self._status.set_message("Graphique généré", loading=False)
        self._sidebar.gen_btn.setEnabled(True)

    def _on_chart_error(self, msg: str) -> None:
        log.error("Chart error: %s", msg)
        self._status.set_message(f"Erreur : {msg}", loading=False)
        self._sidebar.gen_btn.setEnabled(True)

    def _on_data_error(self, msg: str) -> None:
        log.error("Data error: %s", msg)
        self._status.set_message(f"Erreur données : {msg}", loading=False)
        self._sidebar.gen_btn.setEnabled(True)

    def _on_export(self) -> None:
        fig = self._chart_area.get_figure()
        if fig is None:
            QMessageBox.warning(self, "Aucun graphique", "Aucun graphique à exporter.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Exporter le graphique", "",
            "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)"
        )
        if not filepath:
            return

        try:
            ext = Path(filepath).suffix.lower()
            fmt = ext.lstrip(".") or "png"
            fig.savefig(filepath, dpi=150, format=fmt, bbox_inches="tight", facecolor="#0f0f0f")
            self._status.set_message(f"Exporté → {filepath}")
        except Exception as exc:
            log.error("Export error: %s", exc)
            QMessageBox.critical(self, "Erreur", f"Export échoué : {exc}")

    # ── Fermeture propre ──────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        # Attendre la fin des workers en cours
        self._pool.waitForDone(3000)
        event.accept()