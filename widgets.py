"""widgets.py : composants d'interface réutilisables."""

from __future__ import annotations

from typing import Callable, Optional

import pyqtgraph as pg
from PySide6.QtCore import QMarginsF, QPointF, QRectF, QSize, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPageSize, QPainter, QPdfWriter
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QProgressBar, QPushButton,
                               QSizePolicy, QStackedLayout, QStyle, QStyledItemDelegate,
                               QVBoxLayout, QWidget)

import theme
from data import SESSION_SHORT, Driver, Event


# ── Sélecteur de session ─────────────────────────────────────────────────────

class Segmented(QWidget):
    """Boutons exclusifs en grille. Les sessions absentes du week-end sont grisées."""

    changed = Signal(str)

    def __init__(self, codes: list[str], columns: int = 4, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for i, code in enumerate(codes):
            b = QPushButton(SESSION_SHORT[code])
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=code: self.changed.emit(c))
            self._group.addButton(b)
            self._buttons[code] = b
            grid.addWidget(b, i // columns, i % columns)
        for c in range(columns):
            grid.setColumnStretch(c, 1)

    def set_available(self, codes) -> None:
        for code, b in self._buttons.items():
            b.setEnabled(code in codes)

    def set_current(self, code: str) -> None:
        if code in self._buttons:
            self._buttons[code].setChecked(True)

    def current(self) -> str:
        for code, b in self._buttons.items():
            if b.isChecked():
                return code
        return "R"


# ── Liste des Grands Prix ────────────────────────────────────────────────────

class _GpDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 34)

    def paint(self, p: QPainter, opt, index):
        ev: Event = index.data(Qt.ItemDataRole.UserRole)
        r = opt.rect
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        hover = bool(opt.state & QStyle.StateFlag.State_MouseOver) and ev.done
        p.save()
        if selected or hover:
            p.fillRect(r, QColor(theme.RAISED))
        if selected:
            p.fillRect(r.left(), r.top(), 3, r.height(), QColor(theme.RED))

        p.setFont(theme.font(10))
        p.setPen(QColor(theme.DIM))
        p.drawText(r.adjusted(14, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   f"{ev.round:02d}")

        p.setFont(theme.font(11, QFont.Weight.DemiBold if selected else QFont.Weight.Normal))
        p.setPen(QColor(theme.TEXT if ev.done else theme.DIM))
        name_rect = r.adjusted(46, 0, -56, 0)
        name = p.fontMetrics().elidedText(ev.short, Qt.TextElideMode.ElideRight, name_rect.width())
        p.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)

        p.setFont(theme.font(10))
        p.setPen(QColor(theme.MUTED if ev.done else theme.DIM))
        p.drawText(r.adjusted(0, 0, -12, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   f"{ev.date:%d/%m}")
        p.restore()


class GpList(QListWidget):
    selected = Signal(object)    # Event

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(_GpDelegate(self))
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.currentItemChanged.connect(self._on_current)

    def set_events(self, events: list[Event], select_round: Optional[int] = None) -> None:
        self.blockSignals(True)
        self.clear()
        for ev in events:
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, ev)
            if ev.done:
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            else:
                it.setFlags(Qt.ItemFlag.NoItemFlags)
                it.setToolTip("Cette course n'a pas encore eu lieu")
            self.addItem(it)
        self.blockSignals(False)
        if select_round is not None:
            self.select_round(select_round, emit=False)

    def select_round(self, rnd: int, emit: bool = True) -> None:
        for i in range(self.count()):
            ev = self.item(i).data(Qt.ItemDataRole.UserRole)
            if ev.round == rnd and ev.done:
                self.blockSignals(not emit)
                self.setCurrentRow(i)
                self.blockSignals(False)
                self.scrollToItem(self.item(i), QListWidget.ScrollHint.PositionAtCenter)
                return

    def current_event(self) -> Optional[Event]:
        it = self.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _on_current(self, cur, _prev) -> None:
        if cur is not None:
            self.selected.emit(cur.data(Qt.ItemDataRole.UserRole))


# ── Bandeau pilotes ──────────────────────────────────────────────────────────

class DriverStrip(QFrame):
    """Une colonne par écurie, un pilote par ligne : la grille reflète le plateau F1."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("strip")
        self._drivers: list[Driver] = []
        self._chips: dict[str, QPushButton] = {}
        self._quick_buttons: list[QPushButton] = []

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(14)

        left = QWidget()
        left.setFixedWidth(124)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        cap = QLabel("Pilotes")
        cap.setObjectName("caption")
        lv.addWidget(cap)
        quick = QGridLayout()
        quick.setSpacing(4)
        quick.setContentsMargins(0, 0, 0, 0)
        for i, (label, fn, tip) in enumerate([
            ("Top 5", lambda: self.select_top(5), "Sélectionner le Top 5"),
            ("Top 10", lambda: self.select_top(10), "Sélectionner le Top 10"),
            ("Tous", lambda: self.select_top(99), "Sélectionner tous les pilotes"),
            ("Aucun", lambda: self.select_top(0), "Désélectionner tous les pilotes"),
        ]):
            b = QPushButton(label)
            b.setObjectName("quick")
            b.setFixedHeight(24)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            quick.addWidget(b, i // 2, i % 2)
            self._quick_buttons.append(b)
        lv.addLayout(quick)
        root.addWidget(left)

        self._grid = QGridLayout()
        self._grid.setSpacing(4)
        self._grid.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._grid, 1)

    def set_drivers(self, drivers: list[Driver], selected: list[str]) -> None:
        for chip in self._chips.values():
            chip.deleteLater()
        self._chips.clear()
        self._drivers = drivers
        while self._grid.count():
            self._grid.takeAt(0)

        team_col: dict[str, int] = {}
        team_rows: dict[str, int] = {}
        for d in drivers:
            col = team_col.setdefault(d.team, len(team_col))
            row = team_rows.get(d.team, 0)
            team_rows[d.team] = row + 1
            chip = QPushButton(d.code)
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setChecked(d.code in selected)
            chip.setFixedHeight(28)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(f"QPushButton#chip {{ border-left: 4px solid {d.color}; }}")
            pos = f"P{d.position}" if d.position else "non classé"
            chip.setToolTip(f"{d.name}\n{d.team}\n{pos}")
            chip.toggled.connect(lambda _=False: self.changed.emit())
            self._grid.addWidget(chip, row, col)
            self._chips[d.code] = chip
        for c in range(len(team_col)):
            self._grid.setColumnStretch(c, 1)

    def selected(self) -> list[str]:
        return [d.code for d in self._drivers if self._chips[d.code].isChecked()]

    def select_top(self, n: int) -> None:
        for i, d in enumerate(self._drivers):
            self._chips[d.code].blockSignals(True)
            self._chips[d.code].setChecked(i < n)
            self._chips[d.code].blockSignals(False)
        self.changed.emit()

    def set_active(self, active: bool) -> None:
        for chip in self._chips.values():
            chip.setEnabled(active)
        for b in self._quick_buttons:
            b.setEnabled(active)


# ── Vue graphique ────────────────────────────────────────────────────────────

class ChartView(QWidget):
    """pyqtgraph + états (chargement, message) + lecture au survol + export."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plots: list[pg.PlotItem] = []
        self._vlines: list[pg.InfiniteLine] = []
        self._probe: Optional[Callable[[float], Optional[str]]] = None
        self._zoom = False

        self.glw = pg.GraphicsLayoutWidget()
        self.glw.setBackground(theme.BG)
        self.glw.setFrameShape(QFrame.Shape.NoFrame)

        self._msg = QWidget()
        mv = QVBoxLayout(self._msg)
        mv.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mv.setSpacing(10)
        self._msg_title = QLabel()
        self._msg_title.setObjectName("msgtitle")
        self._msg_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._msg_body = QLabel()
        self._msg_body.setObjectName("msgbody")
        self._msg_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._msg_body.setWordWrap(True)
        self._msg_body.setMaximumWidth(520)
        self._msg_bar = QProgressBar()
        self._msg_bar.setRange(0, 0)
        self._msg_bar.setTextVisible(False)
        self._msg_bar.setFixedWidth(180)
        mv.addWidget(self._msg_title)
        mv.addWidget(self._msg_body, 0, Qt.AlignmentFlag.AlignCenter)
        mv.addWidget(self._msg_bar, 0, Qt.AlignmentFlag.AlignCenter)

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self.glw)
        self._stack.addWidget(self._msg)

        self.readout = QLabel(self)
        self.readout.setObjectName("readout")
        self.readout.setTextFormat(Qt.TextFormat.RichText)
        self.readout.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.readout.hide()

        self.glw.scene().sigMouseMoved.connect(self._on_move)

    # États
    def show_message(self, title: str, detail: str = "", loading: bool = False) -> None:
        self._msg_title.setText(title)
        self._msg_body.setText(detail)
        self._msg_body.setVisible(bool(detail))
        self._msg_bar.setVisible(loading)
        self.readout.hide()
        self._stack.setCurrentWidget(self._msg)

    def begin(self):
        self.glw.clear()
        self._plots, self._vlines, self._probe = [], [], None
        self.readout.hide()
        ci = self.glw.ci
        ci.setContentsMargins(18, 14, 22, 14)
        ci.setSpacing(6)
        self._stack.setCurrentWidget(self.glw)
        return ci

    def add_title(self, title: str, subtitle: str) -> None:
        ci = self.glw.ci
        ci.addLabel(title, row=0, col=0, size="16pt", bold=True, color=theme.TEXT, justify="left")
        ci.addLabel(subtitle, row=1, col=0, size="11pt", color=theme.MUTED, justify="left")

    def register(self, plot: pg.PlotItem, vline: bool = False) -> None:
        self._plots.append(plot)
        plot.hideButtons()
        plot.setMenuEnabled(False)
        self._apply_mode(plot)
        if vline:
            line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(theme.DIM, width=1))
            line.hide()
            plot.addItem(line, ignoreBounds=True)
            self._vlines.append(line)

    def set_probe(self, fn: Optional[Callable[[float], Optional[str]]]) -> None:
        self._probe = fn

    # Interaction
    def _apply_mode(self, plot) -> None:
        vb = plot.getViewBox()
        vb.setMouseMode(pg.ViewBox.RectMode if self._zoom else pg.ViewBox.PanMode)

    def set_zoom_mode(self, zoom: bool) -> None:
        self._zoom = zoom
        for p in self._plots:
            self._apply_mode(p)

    def reset(self) -> None:
        for p in self._plots:
            p.enableAutoRange()
            p.getViewBox().autoRange()

    def _place_readout(self) -> None:
        self.readout.adjustSize()
        self.readout.move(self.width() - self.readout.width() - 18, 62)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.readout.isVisible():
            self._place_readout()

    def _on_move(self, pos: QPointF) -> None:
        if not self._probe:
            return
        for p in self._plots:
            vb = p.getViewBox()
            if vb.sceneBoundingRect().contains(pos):
                x = vb.mapSceneToView(pos).x()
                for line in self._vlines:
                    line.setPos(x)
                    line.show()
                html = self._probe(x)
                if html:
                    self.readout.setText(html)
                    self._place_readout()
                    self.readout.show()
                    self.readout.raise_()
                else:
                    self.readout.hide()
                return
        for line in self._vlines:
            line.hide()
        self.readout.hide()

    # Export
    def export(self, path: str) -> None:
        for line in self._vlines:
            line.hide()
        self.readout.hide()
        scene = self.glw.scene()
        src = QRectF(self.glw.viewport().rect())
        bg = QColor(theme.BG)
        suffix = path.lower().rsplit(".", 1)[-1]

        if suffix == "svg":
            gen = QSvgGenerator()
            gen.setFileName(path)
            gen.setSize(src.size().toSize())
            gen.setViewBox(src)
            p = QPainter(gen)
            p.fillRect(src, bg)
            scene.render(p, src, src)
            p.end()
        elif suffix == "pdf":
            w = QPdfWriter(path)
            w.setResolution(300)
            w.setPageSize(QPageSize(QSizeF(src.width() * 0.75, src.height() * 0.75),
                                    QPageSize.Unit.Point))
            w.setPageMargins(QMarginsF(0, 0, 0, 0))
            p = QPainter(w)
            target = QRectF(0, 0, w.width(), w.height())
            p.fillRect(target, bg)
            scene.render(p, target, src)
            p.end()
        else:
            scale = 3
            img = QImage(int(src.width() * scale), int(src.height() * scale),
                         QImage.Format.Format_ARGB32)
            img.fill(bg)
            p = QPainter(img)
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
            scene.render(p, QRectF(img.rect()), src)
            p.end()
            if not img.save(path):
                raise OSError(f"Écriture impossible : {path}")
