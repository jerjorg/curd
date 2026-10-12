from PyQt6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QListWidget, QListWidgetItem, QListView, QAbstractItemView, QVBoxLayout, QLabel,
    QStyle, QStyledItemDelegate,
)
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics
import sys

from model import Course, CourseId, Catalog, ProgramId

# UVU web palette
INK, INK_2, INK_3 = "#292929", "#454543", "#63615E"
LINE, LINE_SOFT = "#CFCFCC", "#E2E2E0"
ACCENT, ACCENT_SOFT = "#275D38", "#E9F0EB"
CRIT, CRIT_SOFT, CRIT_LINE = "#8A2B1A", "#F9E7E3", "#DFA898"
REQUIRED, ELECTIVE = ACCENT, "#D2AC5F"

STYLE = f"""
TermsView {{ background: #F9F9F9; }}
#title {{ color: {INK}; font-size: 20px; font-weight: bold; }}
#legend {{ color: {INK_3}; }}
TermView {{ background: white; border: 1px solid {LINE}; }}
#header {{ border-bottom: 1px solid {LINE_SOFT}; }}
#term-name {{ color: {INK}; font-weight: bold; }}
#term-credits {{ color: {INK_3}; }}
QListWidget {{ border: none; background: transparent; padding: 3px; }}
"""

# Applied to a TermView whose credits exceed the term credit limit
OVER_STYLE = f"""
TermView {{ border-color: {CRIT_LINE}; border-top: 3px solid {CRIT}; }}
#header {{ background: {CRIT_SOFT}; border-bottom-color: {CRIT_LINE}; }}
#term-name, #term-credits {{ color: {CRIT}; }}
"""


class CourseView(QListWidgetItem):
    def __init__(self, course: Course, lw: QListWidget):
        super().__init__(str(course.c_id), lw)
        self.course = course.c_id
        # Dropped items are rebuilt as plain QListWidgetItems, so keep the id in the item data
        self.setData(Qt.ItemDataRole.UserRole, course.c_id)

    def __str__(self):
        return str(self.course)

    def __repr__(self):
        return f"CourseView({self})"


class CourseDelegate(QStyledItemDelegate):
    """Draws a course as a card: a required/elective stripe, the code and credits, and the title."""

    PAD, STRIPE = 7, 8

    def __init__(self, lw: TermListWidget):
        super().__init__(lw)
        self.lw = lw
        self.code_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.code_font.setBold(True)
        self.title_font = QFont(lw.font())
        self.title_font.setPointSizeF(self.title_font.pointSizeF() - 1)

    def course(self, index) -> Course | None:
        c_id = index.data(Qt.ItemDataRole.UserRole)
        return self.lw.term_view.terms_view.catalog.courses[c_id] if c_id else None

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
        return QSize(width, title.bottom() + self.PAD)

    def paint(self, painter, option, index):
        course = self.course(index)
        if course is None:
            return
        selected = option.state & QStyle.StateFlag.State_Selected
        elective = course.c_id not in self.lw.term_view.terms_view.required
        card = option.rect.adjusted(0, 0, -1, -1)
        painter.save()
        painter.setPen(QColor(ACCENT if selected else LINE))
        painter.setBrush(QColor(ACCENT_SOFT if selected else "white"))
        painter.drawRect(card)
        painter.fillRect(card.left(), card.top(), self.STRIPE, card.height() + 1, QColor(ELECTIVE if elective else REQUIRED))

        first, title = self.text_rects(card, course.title)
        painter.setFont(self.code_font)
        painter.setPen(QColor(INK_3))
        creds = f"{course.creds} cr"
        painter.drawText(first, Qt.AlignmentFlag.AlignRight, creds)
        painter.setPen(QColor(INK))
        code_width = first.width() - QFontMetrics(self.code_font).horizontalAdvance(creds + " ")
        code = QFontMetrics(self.code_font).elidedText(str(course.c_id), Qt.TextElideMode.ElideRight, code_width)
        painter.drawText(first, Qt.AlignmentFlag.AlignLeft, code)
        painter.setFont(self.title_font)
        painter.setPen(QColor(INK_2))
        painter.drawText(title, Qt.TextFlag.TextWordWrap, course.title)
        painter.restore()


class TermListWidget(QListWidget):
    def __init__(self, courses, term_view: TermView):
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

        for course in courses:
            CourseView(term_view.terms_view.catalog.courses[course], self)

    def dragEnterEvent(self, event):
        # TODO
        print(f"enter event: {event.source().selectedItems()} from {event.source()} to {self}")
        if True:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        # TODO
        print(f"move event: {event.source().selectedItems()} from {event.source()} to {self}")
        if True:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        # TODO
        print(f"drop event: {event.source().selectedItems()} from {event.source()} to {self}")
        if True:
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
    def __init__(self, courses, term_number: int, terms_view: TermsView):
        super().__init__(terms_view)
        self.term_number = term_number
        self.terms_view = terms_view
        self.setMinimumWidth(170)

        header = QFrame(objectName="header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.addWidget(QLabel(f"TERM {term_number}", objectName="term-name"))
        header_layout.addStretch()
        self.credits = QLabel(objectName="term-credits")
        self.credits.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        header_layout.addWidget(self.credits)

        self.lw = TermListWidget(courses, self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self.lw)

        self.lw.model().dataChanged.connect(self.update_label)
        self.lw.model().rowsRemoved.connect(self.update_label)
        self.update_label()

    def update_label(self):
        catalog = self.terms_view.catalog
        # Dropped rows are inserted empty and filled in afterwards, so skip unset ones
        ids = filter(None, (self.lw.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lw.count())))
        total = sum(catalog.courses[c_id].creds for c_id in ids)
        over = total > catalog.limits.term_credit_limit
        self.credits.setText(f"{total} cr")
        self.setStyleSheet(OVER_STYLE if over else "")


class TermsView(QWidget):
    def __init__(self, catalog: Catalog, pid: ProgramId):
        super().__init__()
        self.setWindowTitle(f"Graduation plan ({pid})")
        self.setStyleSheet(STYLE)
        self.resize(1480, 760)
        self.catalog = catalog

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.addWidget(QLabel(f"GRADUATION PLAN · {pid}", objectName="title"))
        terms = QHBoxLayout()
        terms.setSpacing(10)
        layout.addLayout(terms)

        scheduler = catalog.get_scheduler(pid)
        schedule = scheduler.generate_schedule()
        self.required = scheduler.required

        for index, (_, classes) in enumerate(schedule.schedule):
            term_list = TermView(classes, index + 1, self)
            terms.addWidget(term_list)

        legend = f'<span style="color:{REQUIRED}">■</span> Required &nbsp; <span style="color:{ELECTIVE}">■</span> Elective'
        layout.addWidget(QLabel(legend, objectName="legend"))
