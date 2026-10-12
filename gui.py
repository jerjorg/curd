from PyQt6.QtWidgets import QWidget, QHBoxLayout, QListWidget, QListWidgetItem, QAbstractItemView, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
import sys

from model import Course, CourseId, Catalog, ProgramId


class CourseView(QListWidgetItem):
    def __init__(self, course: Course, elective: bool, lw: QListWidget):
        super().__init__(f"{course.c_id} ({course.creds} cr)", lw)
        self.course = course.c_id
        self.setToolTip(f"{course.title} (elective)" if elective else course.title)
        if elective:
            font = self.font()
            font.setItalic(True)
            self.setFont(font)
        # Dropped items are rebuilt as plain QListWidgetItems, so keep the id in the item data
        self.setData(Qt.ItemDataRole.UserRole, course.c_id)

    def __str__(self):
        return str(self.course)

    def __repr__(self):
        return f"CourseView({self})"


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

        terms_view = term_view.terms_view
        for course in courses:
            CourseView(terms_view.catalog.courses[course], course not in terms_view.required, self)

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
        # remaining data (tooltip, course id) lands on the wrong item.
        self.setSortingEnabled(False)
        result = super().dropMimeData(index, data, action)
        self.setSortingEnabled(True)
        self.sortItems()
        return result

    def __str__(self):
        return f"Term {self.term_view.term_number}"


class TermView(QWidget):
    def __init__(self, courses, term_number: int, terms_view: TermsView):
        super().__init__(terms_view)
        self.term_number = term_number
        self.terms_view = terms_view

        self.label = QLabel()
        self.lw = TermListWidget(courses, self)
        layout = QVBoxLayout(self)

        layout.addWidget(self.label)
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
        self.label.setText(f"Term {self.term_number} ({total} credits)")
        self.label.setStyleSheet("color: red" if over else "")


class TermsView(QWidget):
    def __init__(self, catalog: Catalog, pid: ProgramId):
        super().__init__()
        self.setWindowTitle(f"Graduation plan ({pid})")
        self.catalog = catalog

        layout = QHBoxLayout(self)

        scheduler = catalog.get_scheduler(pid)
        schedule = scheduler.generate_schedule()
        self.required = scheduler.required

        for index, (_, classes) in enumerate(schedule.schedule):
            term_list = TermView(classes, index + 1, self)
            layout.addWidget(term_list)
