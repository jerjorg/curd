from collections import defaultdict
from html import escape
from PyQt6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QListWidget, QListWidgetItem, QListView, QAbstractItemView, QVBoxLayout, QLabel,
    QStyle, QStyledItemDelegate, QToolTip, QMenu, QPushButton, QToolButton, QLineEdit, QCompleter, QScrollArea,
)
from PyQt6.QtCore import Qt, QRect, QSize, QTimer
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QKeySequence, QPen
import sys

from model import Course, CourseId, Catalog, ProgramId, Requirement

# UVU web palette
INK, INK_2, INK_3 = "#292929", "#454543", "#63615E"
LINE, LINE_SOFT = "#CFCFCC", "#E2E2E0"
ACCENT, ACCENT_SOFT = "#275D38", "#E9F0EB"
CRIT, CRIT_SOFT, CRIT_LINE = "#8A2B1A", "#F9E7E3", "#DFA898"
REQUIRED, ELECTIVE = ACCENT, "#D2AC5F"

STYLE = f"""
TermsView {{ background: #F9F9F9; }}
QLabel {{ color: {INK}; }}
#title {{ color: {INK}; font-size: 20px; font-weight: bold; }}
#legend {{ color: {INK_3}; }}
#scroll, #terms {{ background: transparent; border: none; }}
TermView, #details {{ background: white; border: 1px solid {LINE}; }}
#header {{ border-bottom: 1px solid {LINE_SOFT}; }}
#term-name {{ color: {INK}; font-weight: bold; }}
#term-credits {{ color: {INK_3}; }}
#close {{ border: none; background: transparent; color: {INK_3}; font-size: 15px; }}
#close:hover {{ color: {CRIT}; }}
#add {{ border: 1px dashed {LINE}; background: transparent; color: {INK}; padding: 4px; margin: 6px; }}
#add:focus {{ border-color: {ACCENT}; }}
QListWidget {{ border: none; background: transparent; padding: 3px; }}
QPushButton {{ background: white; border: 1px solid {LINE}; padding: 5px 12px; color: {INK}; }}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; background: {ACCENT_SOFT}; }}
QPushButton:disabled {{ color: {LINE}; }}
"""

# Applied to a TermView whose credits exceed the term credit limit
OVER_STYLE = f"""
TermView {{ border-color: {CRIT_LINE}; border-top: 3px solid {CRIT}; }}
#header {{ background: {CRIT_SOFT}; border-bottom-color: {CRIT_LINE}; }}
#term-name, #term-credits {{ color: {CRIT}; }}
"""

Plan = tuple[list[list[CourseId]], set[CourseId]]


def course_label(c_id: CourseId) -> str:
    """How the planner shows a course, e.g. "CS 1400" rather than "CS_1400"."""
    return f"{c_id.dept} {c_id.course_number}"


class CourseView(QListWidgetItem):
    def __init__(self, course: Course, lw: QListWidget):
        super().__init__(course_label(course.c_id), lw)
        self.course = course.c_id
        # Dropped items are rebuilt as plain QListWidgetItems, so keep the id in the item data
        self.setData(Qt.ItemDataRole.UserRole, course.c_id)

    def __str__(self):
        return str(self.course)

    def __repr__(self):
        return f"CourseView({self})"


class CourseDelegate(QStyledItemDelegate):
    """Draws a course as a card: a required/elective stripe, the code and credits, and the title.
    A course with a prerequisite problem gets a "WILL NOT WORK" band, a course marked done is
    faded and struck through, and while a course is hovered everything unrelated to it is dimmed."""

    PAD, STRIPE, BAND = 7, 8, 15

    def __init__(self, lw: TermListWidget):
        super().__init__(lw)
        self.lw = lw
        self.terms_view = lw.term_view.terms_view
        self.code_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.code_font.setBold(True)
        self.title_font = QFont(lw.font())
        self.title_font.setPointSizeF(self.title_font.pointSizeF() - 1)

    def course(self, index) -> Course | None:
        c_id = index.data(Qt.ItemDataRole.UserRole)
        return self.terms_view.catalog.courses[c_id] if c_id else None

    def text_rects(self, card: QRect, title: str) -> tuple[QRect, QRect]:
        """Split a card into its first line (code and credits) and the wrapped title below it."""
        inner = card.adjusted(self.STRIPE + self.PAD, self.PAD, -self.PAD, -self.PAD)
        first = QRect(inner.left(), inner.top(), inner.width(), QFontMetrics(self.code_font).height())
        flags = Qt.TextFlag.TextWordWrap
        title_rect = QFontMetrics(self.title_font).boundingRect(QRect(inner.left(), first.bottom() + 3, inner.width(), 1000), flags, title)
        return first, title_rect

    def sizeHint(self, option, index):
        course = self.course(index)
        if course is None:
            return super().sizeHint(option, index)
        width = self.lw.viewport().width() - 2 * self.lw.spacing()
        _, title = self.text_rects(QRect(0, 0, width, 0), course.title)
        band = self.BAND if course.c_id in self.terms_view.conflicts else 0
        return QSize(width, title.bottom() + self.PAD + band)

    def paint(self, painter, option, index):
        course = self.course(index)
        if course is None:
            return
        tv = self.terms_view
        c_id = course.c_id
        selected = option.state & QStyle.StateFlag.State_Selected
        elective = c_id not in tv.required
        bad = c_id in tv.conflicts
        done = c_id in tv.done
        card = option.rect.adjusted(0, 0, -1, -1)
        painter.save()
        if tv.lit and c_id not in tv.lit:
            painter.setOpacity(0.25)
        elif done:
            painter.setOpacity(0.5)
        if bad:
            painter.setPen(QPen(QColor(CRIT), 2))
        elif c_id in tv.lit:
            painter.setPen(QPen(QColor(ACCENT), 3 if c_id == tv.hovered else 2))
        else:
            painter.setPen(QColor(ACCENT if selected else INK_3 if c_id == tv.hovered else LINE))
        painter.setBrush(QColor(ACCENT_SOFT if selected else CRIT_SOFT if bad else "white"))
        painter.drawRect(card)
        painter.fillRect(card.left(), card.top(), self.STRIPE, card.height() + 1, QColor(ELECTIVE if elective else REQUIRED))
        if bad:
            band = QRect(card.left(), card.bottom() - self.BAND + 1, card.width() + 1, self.BAND)
            painter.fillRect(band, QColor(CRIT))
            painter.setPen(QColor("white"))
            band_font = QFont(self.title_font)
            band_font.setBold(True)
            band_font.setPointSizeF(band_font.pointSizeF() - 2)
            painter.setFont(band_font)
            painter.drawText(band, Qt.AlignmentFlag.AlignCenter, "WILL NOT WORK")

        first, title = self.text_rects(option.rect, course.title)  # the rect sizeHint measured, not the 1px-smaller border
        painter.setFont(self.code_font)
        painter.setPen(QColor(INK_3))
        creds = f"{course.creds} cr"
        painter.drawText(first, Qt.AlignmentFlag.AlignRight, creds)
        painter.setPen(QColor(INK))
        code_width = first.width() - QFontMetrics(self.code_font).horizontalAdvance(creds + " ")
        code = QFontMetrics(self.code_font).elidedText(course_label(c_id), Qt.TextElideMode.ElideRight, code_width)
        painter.drawText(first, Qt.AlignmentFlag.AlignLeft, code)
        title_font = QFont(self.title_font)
        title_font.setStrikeOut(done)
        painter.setFont(title_font)
        painter.setPen(QColor(CRIT if bad else INK_2))
        painter.drawText(title, Qt.TextFlag.TextWordWrap, course.title)
        painter.restore()

    def helpEvent(self, event, view, option, index):
        course = self.course(index)
        problems = course and self.terms_view.conflicts.get(course.c_id)
        if not problems:
            return super().helpEvent(event, view, option, index)
        QToolTip.showText(event.globalPos(), "\n".join(problems), view)
        return True


class TermListWidget(QListWidget):
    def __init__(self, term_view: TermView):
        super().__init__()
        self.term_view = term_view

        # Selection (use ExtendedSelection if you want multi-select)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        # Enable drag & drop both ways and show indicator
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSortingEnabled(True)

        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDragDropOverwriteMode(False)

        # Cards are as wide as the list, so re-measure them when it resizes
        self.setItemDelegate(CourseDelegate(self))
        self.setSpacing(3)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.setMouseTracking(True)  # hover tracing
        self.itemClicked.connect(lambda item: term_view.terms_view.show_details(item.data(Qt.ItemDataRole.UserRole)))

    def selected_ids(self) -> list[CourseId]:
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.selectedItems()]

    def mouseMoveEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        self.term_view.terms_view.hover(item.data(Qt.ItemDataRole.UserRole) if item else None)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.term_view.terms_view.hover(None)
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selectedItems():
            self.term_view.terms_view.remove_courses(self.selected_ids())
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        ids = self.selected_ids()
        if not ids:
            return
        tv = self.term_view.terms_view
        menu = QMenu(self)
        move_menu = menu.addMenu("Move to")
        for index, term in enumerate(tv.terms):
            # *_ swallows the triggered signal's `checked` argument, which would otherwise replace index
            action = move_menu.addAction(f"Term {term.term_number}", lambda *_, index=index: tv.move_courses(ids, index))
            action.setEnabled(term is not self.term_view)
        done = all(c_id in tv.done for c_id in ids)
        menu.addAction("Mark not done" if done else "Mark done", lambda *_: tv.set_done(ids, not done))
        menu.addAction("Remove", lambda *_: tv.remove_courses(ids))
        menu.exec(event.globalPos())

    def dragEnterEvent(self, event):
        # TODO
        if True:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        # TODO
        if True:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        # TODO
        if True:
            self.term_view.terms_view.remember()
            super().dropEvent(event)
        else:
            event.ignore()

    def dropMimeData(self, index, data, action):
        # A dropped item gets its text first; if that re-sorts the list, its
        # remaining data (the course id) lands on the wrong item.
        self.setSortingEnabled(False)
        result = super().dropMimeData(index, data, action)
        self.setSortingEnabled(True)
        self.sortItems()
        return result

    def __str__(self):
        return f"Term {self.term_view.term_number}"


class TermView(QFrame):
    def __init__(self, term_number: int, terms_view: TermsView):
        super().__init__(terms_view)
        self.term_number = term_number
        self.terms_view = terms_view
        self.setMinimumWidth(170)

        header = QFrame(objectName="header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 8, 6, 8)
        header_layout.addWidget(QLabel(f"TERM {term_number}", objectName="term-name"))
        header_layout.addStretch()
        self.credits = QLabel(objectName="term-credits")
        self.credits.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        header_layout.addWidget(self.credits)
        remove = QToolButton(text="×", objectName="close", toolTip="Remove this term and its courses")
        remove.clicked.connect(lambda: terms_view.remove_term(terms_view.terms.index(self)))
        header_layout.addWidget(remove)

        # Choosing a course here adds it to this term, or moves it here if it is already planned
        self.adder = QLineEdit(placeholderText="+ Add course", objectName="add")
        completer = QCompleter(list(terms_view.entries), self.adder)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.popup().setMinimumWidth(380)
        completer.activated[str].connect(self.add_course)
        self.adder.setCompleter(completer)

        self.lw = TermListWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self.lw)
        layout.addWidget(self.adder)

        self.lw.model().dataChanged.connect(self.update_label)
        self.lw.model().rowsRemoved.connect(self.update_label)
        self.update_label()

    def add_course(self, entry: str):
        self.terms_view.move_courses([self.terms_view.entries[entry]], self.terms_view.terms.index(self))
        QTimer.singleShot(0, self.adder.clear)  # the completer writes the chosen entry in after this

    def course_ids(self) -> list[CourseId]:
        # Dropped rows are inserted empty and filled in afterwards, so skip unset ones
        ids = (self.lw.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lw.count()))
        return [c_id for c_id in ids if c_id]

    def update_label(self):
        catalog = self.terms_view.catalog
        total = sum(catalog.courses[c_id].creds for c_id in self.course_ids())
        over = total > catalog.limits.term_credit_limit
        self.credits.setText(f"{total} cr")
        self.setStyleSheet(OVER_STYLE if over else "")
        self.terms_view.check_prereqs()


class TermsView(QWidget):
    def __init__(self, catalog: Catalog, pid: ProgramId):
        super().__init__()
        self.setWindowTitle(f"Graduation plan ({pid})")
        self.setStyleSheet(STYLE)
        self.resize(1480, 760)
        self.catalog = catalog
        self.terms: list[TermView] = []
        self.done: set[CourseId] = set()
        self.history: list[Plan] = []
        self.conflicts: dict[CourseId, list[str]] = {}
        self.hovered: CourseId | None = None
        self.lit: set[CourseId] = set()  # the hovered course and its planned prerequisites and unlocks
        self.details_id: CourseId | None = None

        # "CS 1400  Fundamentals of Programming" -> its id, for the add-course boxes
        self.entries = {f"{course_label(c_id)}  {course.title}": c_id for c_id, course in sorted(catalog.courses.items())}
        self.reqs_of: dict[CourseId, set[Requirement]] = defaultdict(set)
        for req, c_ids in catalog.course_requirements.items():
            for c_id in c_ids:
                self.reqs_of[c_id].add(req)
        # Every course that must come before each course, for hover tracing
        self.closure = Catalog.close_graph(catalog.build_courses_graph())
        self.closure.add_nodes_from(catalog.courses)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 12)
        top = QHBoxLayout()
        top.addWidget(QLabel(f"GRADUATION PLAN · {pid}", objectName="title"))
        top.addStretch()
        self.undo_button = QPushButton("↩ Undo", enabled=False)
        self.undo_button.setShortcut(QKeySequence(QKeySequence.StandardKey.Undo))
        self.undo_button.clicked.connect(self.undo)
        top.addWidget(self.undo_button)
        add_term = QPushButton("+ Add term")
        add_term.clicked.connect(self.add_term)
        top.addWidget(add_term)
        layout.addLayout(top)

        terms = QWidget(objectName="terms")
        self.terms_layout = QHBoxLayout(terms)
        self.terms_layout.setContentsMargins(0, 0, 0, 0)
        self.terms_layout.setSpacing(10)
        scroll = QScrollArea(widgetResizable=True, objectName="scroll")
        scroll.setWidget(terms)
        scroll.viewport().setAutoFillBackground(False)

        self.details = QFrame(objectName="details", visible=False)
        self.details.setFixedWidth(300)
        details_layout = QVBoxLayout(self.details)
        close = QToolButton(text="×", objectName="close")
        close.clicked.connect(lambda: self.show_details(None))
        details_layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        self.details_text = QLabel(wordWrap=True, alignment=Qt.AlignmentFlag.AlignTop)
        details_layout.addWidget(self.details_text, 1)

        body = QHBoxLayout()
        body.addWidget(scroll, 1)
        body.addWidget(self.details)
        layout.addLayout(body)

        scheduler = catalog.get_scheduler(pid)
        schedule = scheduler.generate_schedule()
        self.required = scheduler.required
        self.load([sorted(classes) for _, classes in schedule.schedule], set())

        legend = (f'<span style="color:{REQUIRED}">■</span> Required &nbsp; <span style="color:{ELECTIVE}">■</span> Elective'
                  " &nbsp;·&nbsp; Hover a course to trace its prerequisites, click it for details, right-click to move, mark done or remove")
        layout.addWidget(QLabel(legend, objectName="legend"))

    def plan(self) -> Plan:
        """Each term's courses, and the courses marked done."""
        return [term.course_ids() for term in self.terms], set(self.done)

    def load(self, terms: list[list[CourseId]], done: set[CourseId]):
        """Show `terms`, adding or removing term columns to match."""
        self.done = set(done)
        while len(self.terms) > len(terms):
            self.terms.pop().deleteLater()
        while len(self.terms) < len(terms):
            term = TermView(len(self.terms) + 1, self)
            self.terms.append(term)
            self.terms_layout.addWidget(term)
        for term, c_ids in zip(self.terms, terms):
            term.lw.clear()
            for c_id in c_ids:
                CourseView(self.catalog.courses[c_id], term.lw)
            term.update_label()  # clear() resets the list without the signals update_label listens to

    def remember(self):
        """Save the plan before a change so it can be undone."""
        self.history.append(self.plan())
        self.undo_button.setEnabled(True)

    def change(self, terms: list[list[CourseId]], done: set[CourseId] | None = None):
        self.remember()
        self.load(terms, self.done if done is None else done)

    def undo(self):
        current = self.plan()
        while self.history:
            plan = self.history.pop()
            if plan != current:  # skip snapshots of edits that changed nothing, like a drop in place
                self.load(*plan)
                break
        self.undo_button.setEnabled(bool(self.history))

    def remove_courses(self, c_ids: list[CourseId]):
        self.change([[c for c in term if c not in c_ids] for term in self.plan()[0]])

    def move_courses(self, c_ids: list[CourseId], index: int):
        terms = [[c for c in term if c not in c_ids] for term in self.plan()[0]]
        terms[index] += c_ids
        self.change(terms)

    def set_done(self, c_ids: list[CourseId], done: bool):
        self.change(self.plan()[0], self.done | set(c_ids) if done else self.done - set(c_ids))

    def add_term(self):
        self.change(self.plan()[0] + [[]])

    def remove_term(self, index: int):
        terms = self.plan()[0]
        del terms[index]
        self.change(terms)

    def term_of(self) -> dict[CourseId, int]:
        return {c_id: index for index, term in enumerate(self.terms) for c_id in term.course_ids()}

    def prereq_reqs(self, c_id: CourseId) -> list[Requirement]:
        """The requirements that must be met before taking `c_id`, other than ones it meets itself."""
        deps = {dep for req in self.reqs_of[c_id] for dep in self.catalog.requirement_deps.get(req, ())}
        return sorted(dep for dep in deps if c_id not in self.catalog.course_requirements.get(dep, ()))

    def check_prereqs(self):
        """Find each course whose prerequisite is missing from the plan or scheduled no earlier
        than it, and redraw the terms."""
        term_of = self.term_of()
        conflicts = {}
        for c_id, index in term_of.items():
            problems = []
            for dep in self.prereq_reqs(c_id):
                planned = sorted((term_of[o], o) for o in self.catalog.course_requirements.get(dep, ()) if o in term_of)
                if not planned:
                    problems.append(f"Nothing in the plan covers {dep.name}")
                elif planned[0][0] >= index:
                    problems.append(f"Must come after {course_label(planned[0][1])} (Term {planned[0][0] + 1})")
            if problems:
                conflicts[c_id] = list(dict.fromkeys(problems))
        if conflicts != self.conflicts:
            self.conflicts = conflicts
            for term in self.terms:
                term.lw.scheduleDelayedItemsLayout()  # cards with a band are taller
        self.refresh()

    def hover(self, c_id: CourseId | None):
        if c_id != self.hovered:
            self.hovered = c_id
            self.refresh()

    def refresh(self):
        """Recompute the hover tracing and the details panel, and repaint the terms."""
        planned = set(self.term_of())
        related = set()
        if self.hovered in planned:
            related = (set(self.closure.predecessors(self.hovered)) | set(self.closure.successors(self.hovered))) & planned
        self.lit = related | {self.hovered} if related else set()
        self.show_details(self.details_id)
        for term in self.terms:
            term.lw.viewport().update()

    def show_details(self, c_id: CourseId | None):
        """Show `c_id`'s prerequisites and unlocks in the side panel, or hide it."""
        term_of = self.term_of()
        self.details_id = c_id if c_id in term_of else None
        self.details.setVisible(self.details_id is not None)
        if self.details_id is None:
            return
        course = self.catalog.courses[c_id]

        def rows(items):
            return "<br>".join(items) or f"<span style='color:{INK_3}'>None in this plan</span>"

        prereqs = []
        for dep in self.prereq_reqs(c_id):
            planned = sorted((term_of[o], o) for o in self.catalog.course_requirements.get(dep, ()) if o in term_of)
            where = ", ".join(f"{course_label(o)} (Term {t + 1})" for t, o in planned)
            prereqs.append(f"{escape(dep.name)}: {where or f'<span style=color:{CRIT}>not in plan</span>'}")
        unlocks = [f"{course_label(o)} (Term {t + 1})" for o, t in sorted(term_of.items(), key=lambda p: p[1])
                   if self.reqs_of[c_id] & set(self.prereq_reqs(o))]
        status = ["Required" if c_id in self.required else "Elective", f"Term {term_of[c_id] + 1}", f"{course.creds} credits"]
        problems = self.conflicts.get(c_id)
        self.details_text.setText(
            f"<p style='font-size:16px'><b>{course_label(c_id)}</b></p>"
            f"<p style='font-size:15px'>{escape(course.title)}</p>"
            f"<p style='color:{INK_3}'>{' · '.join(status + (['Done'] if c_id in self.done else []))}</p>"
            + (f"<p style='color:{CRIT}'><b>WILL NOT WORK</b><br>{'<br>'.join(map(escape, problems))}</p>" if problems else "")
            + f"<p><b>PREREQUISITES</b><br>{rows(prereqs)}</p><p><b>UNLOCKS</b><br>{rows(unlocks)}</p>"
        )
