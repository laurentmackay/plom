# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2021 Andrew Rechnitzer
# Copyright (C) 2018 Elvis Cai
# Copyright (C) 2019-2021 Colin B. Macdonald
# Copyright (C) 2020 Victoria Schuster
# Copyright (C) 2020 Vala Vakilian
# Copyright (C) 2021 Forest Kobayashi

import logging
from pathlib import Path

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QPalette,
    QCursor,
    QDropEvent,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QCheckBox,
    QLabel,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from plom.comment_utils import comments_apply_default_fields
from plom.misc_utils import next_in_longest_subsequence
from .useful_classes import ErrorMessage, SimpleMessage
from .rubric_wrangler import RubricWrangler

log = logging.getLogger("annotr")


# colours to indicate whether rubric is legal to paste or not.
# TODO: how do:  QPalette().color(QPalette.Text), QPalette().color(QPalette.Dark)
colour_legal = QBrush(QColor(0, 0, 0))
colour_illegal = QBrush(QColor(128, 128, 128, 128))
abs_suffix = " / N"
abs_suffix_length = len(abs_suffix)


def isLegalRubric(mss, kind, delta):
    """Checks the 'legality' of the current rubric - returning one of three possibile states
    0 = incompatible - the kind of rubric is not compatible with the current state
    1 = compatible but out of range - the kind of rubric is compatible with the state but applying that rubric will take the score out of range [0, maxmark] (so cannot be used)
    2 = compatible and in range - is compatible and can be used.
    Note that the rubric lists use the result to decide which rubrics will be shown (return value 2) which hidden (0 return) and greyed out (1 return)


    Args:
        mss (list): triple that encodes max-mark, state, and current-score
        kind: the kind of the rubric being checked
        delta: the delta of the rubric being checked

    Returns:
        int: 0,1,2.
    """
    maxMark = mss[0]
    state = mss[1]
    score = mss[2]

    # easy cases first
    # when state is neutral - all rubrics are fine
    # a neutral rubric is always compatible and in range
    if state == "neutral" or kind == "neutral":
        return 2
    # now, neither state nor kind are neutral

    # consequently if state is absolute, no remaining rubric is legal
    # similarly, if kind is absolute, the rubric is not legal since state is not netural
    if state == "absolute" or kind == "absolute":
        return 0

    # now state must be up or down, and kind must be delta or relative
    # delta mark = delta = must be an non-zero int.
    idelta = int(delta)
    if state == "up":
        if idelta < 0:  # not compat
            return 0
        elif idelta + score > maxMark:  # out of range
            return 1
        else:
            return 2
    else:  # state == "down"
        if idelta > 0:  # not compat
            return 0
        elif idelta + score < 0:  # out of range
            return 1
        else:
            return 2


class RubricTable(QTableWidget):
    def __init__(self, parent, shortname=None, sort=False, tabType=None):
        super().__init__()
        self.parent = parent
        self.tabType = tabType  # to help set menu
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.horizontalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(True)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        #  negative padding is probably b/c of fontsize changes
        self.setStyleSheet(
            """
            QHeaderView::section {
                background-color: palette(window);
                color: palette(dark);
                padding-left: 1px;
                padding-right: -3px;
                border: none;
            }
            QTableView {
                border: none;
            }
            QTableView::item {
                border: none;
                border-bottom: 1px solid palette(mid);
            }
        """
        )
        # CSS cannot set relative fontsize
        f = self.font()
        f.setPointSizeF(0.67 * f.pointSizeF())
        self.verticalHeader().setFont(f)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Key", "Username", "Delta", "Text", "Kind"])
        self.hideColumn(0)
        self.hideColumn(1)
        self.hideColumn(4)
        # could use a subclass
        if self.tabType == "delta":
            self.hideColumn(3)
            # self.verticalHeader().setVisible(False)
        if sort:
            self.setSortingEnabled(True)
        self.shortname = shortname
        self.pressed.connect(self.handleClick)
        # self.itemChanged.connect(self.handleClick)
        self.doubleClicked.connect(self.editRow)

    def set_name(self, newname):
        log.debug("tab %s changing name to %s", self.shortname, newname)
        self.shortname = newname
        # TODO: assumes parent is TabWidget, can we do with signals/slots?
        # More like "If anybody cares, I just changed my name!"
        self.parent.update_tab_names()

    def is_user_tab(self):
        return self.tabType is None

    def is_delta_tab(self):
        return self.tabType == "delta"

    def is_hidden_tab(self):
        # TODO: naming here is confusing
        return self.tabType == "hide"

    def is_shared_tab(self):
        return self.tabType == "show"

    def contextMenuEvent(self, event):
        if self.is_hidden_tab():
            self.hideContextMenuEvent(event)
        elif self.is_shared_tab():
            self.showContextMenuEvent(event)
        elif self.is_user_tab():
            self.defaultContextMenuEvent(event)
        elif self.is_delta_tab():
            event.ignore()
        else:
            event.ignore()

    def defaultContextMenuEvent(self, event):
        # first try to get the row from the event
        row = self.rowAt(event.pos().y())
        if row < 0:
            # no row under click but maybe one is highlighted
            row = self.getCurrentRubricRow()
        key = None if row is None else self.getKeyFromRow(row)

        # These are workaround for Issue #1441, lambdas in a loop
        def func_factory_add(t, k):
            def foo():
                t.appendByKey(k)

            return foo

        def func_factory_del(t, k):
            def foo():
                t.removeRubricByKey(k)

            return foo

        menu = QMenu(self)
        if key:
            edit = QAction("Edit rubric", self)
            edit.setEnabled(False)  # TODO hook it up
            menu.addAction(edit)
            menu.addSeparator()

            for tab in self.parent.user_tabs:
                if tab == self:
                    continue
                a = QAction(f"Move to tab {tab.shortname}", self)
                a.triggered.connect(func_factory_add(tab, key))
                a.triggered.connect(func_factory_del(self, key))
                menu.addAction(a)
            menu.addSeparator()

            remAction = QAction("Remove from this tab", self)
            remAction.triggered.connect(func_factory_del(self, key))
            menu.addAction(remAction)
            menu.addSeparator()

        renameTabAction = QAction("Rename this tab...", self)
        menu.addAction(renameTabAction)
        renameTabAction.triggered.connect(self.rename_current_tab)
        a = QAction("Add new tab", self)
        a.triggered.connect(lambda: self.parent.add_new_tab())
        menu.addAction(a)
        a = QAction("Remove this tab...", self)

        def _local_delete_thyself():
            # TODO: can we put all this in some close event?
            # TODO: I don't like that we're hardcoding the parent structure here
            msg = SimpleMessage(
                f"<p>Are you sure you want to delete the tab &ldquo;{self.shortname}&rdquo;?</p>"
                "<p>(The rubrics themselves will not be deleted).<p>"
            )
            if msg.exec_() == QMessageBox.No:
                return
            for n in range(self.parent.RTW.count()):
                tab = self.parent.RTW.widget(n)
                if tab == self:
                    self.parent.RTW.removeTab(n)
            self.clear()
            self.deleteLater()

        a.triggered.connect(_local_delete_thyself)
        menu.addAction(a)
        menu.popup(QCursor.pos())
        event.accept()

    def showContextMenuEvent(self, event):
        # first try to get the row from the event
        row = self.rowAt(event.pos().y())
        if row < 0:
            # no row under click but maybe one is highlighted
            row = self.getCurrentRubricRow()
        key = None if row is None else self.getKeyFromRow(row)

        # workaround for Issue #1441, lambdas in a loop
        def function_factory(t, k):
            def foo():
                t.appendByKey(k)

            return foo

        menu = QMenu(self)
        if key:
            edit = QAction("Edit rubric", self)
            edit.setEnabled(False)  # TODO hook it up
            menu.addAction(edit)
            menu.addSeparator()

            # TODO: walk in another order for moveable tabs?
            # [self.parent.RTW.widget(n) for n in range(1, 5)]
            for tab in self.parent.user_tabs:
                a = QAction(f"Add to tab {tab.shortname}", self)
                a.triggered.connect(function_factory(tab, key))
                menu.addAction(a)
            menu.addSeparator()

            hideAction = QAction("Hide", self)
            hideAction.triggered.connect(self.hideCurrentRubric)
            menu.addAction(hideAction)
            menu.addSeparator()
        renameTabAction = QAction("Rename this tab...", self)
        menu.addAction(renameTabAction)
        renameTabAction.triggered.connect(self.rename_current_tab)
        a = QAction("Add new tab", self)
        a.triggered.connect(lambda: self.parent.add_new_tab())
        menu.addAction(a)
        menu.popup(QCursor.pos())
        event.accept()

    def hideContextMenuEvent(self, event):
        menu = QMenu(self)
        unhideAction = QAction("Unhide rubric", self)
        unhideAction.triggered.connect(self.unhideCurrentRubric)
        menu.addAction(unhideAction)
        menu.popup(QCursor.pos())
        event.accept()

    def removeCurrentRubric(self):
        row = self.getCurrentRubricRow()
        if row is None:
            return
        self.removeRow(row)
        self.selectRubricByVisibleRow(0)
        self.handleClick()

    def removeRubricByKey(self, key):
        row = self.getRowFromKey(key)
        if row is None:
            return
        self.removeRow(row)
        self.selectRubricByVisibleRow(0)
        self.handleClick()

    def hideCurrentRubric(self):
        row = self.getCurrentRubricRow()
        if row is None:
            return
        key = self.item(row, 0).text()
        self.parent.hideRubricByKey(key)
        self.removeRow(row)
        self.selectRubricByVisibleRow(0)
        self.handleClick()

    def unhideCurrentRubric(self):
        row = self.getCurrentRubricRow()
        if row is None:
            return
        key = self.item(row, 0).text()
        self.parent.unhideRubricByKey(key)
        self.removeRow(row)
        self.selectRubricByVisibleRow(0)
        self.handleClick()

    def dropEvent(self, event):
        # fixed drop event using
        # https://stackoverflow.com/questions/26227885/drag-and-drop-rows-within-qtablewidget
        if event.source() == self:
            event.setDropAction(Qt.CopyAction)
            sourceRow = self.selectedIndexes()[0].row()
            targetRow = self.indexAt(event.pos()).row()
            if targetRow == -1:  # no row, so drop at end
                targetRow = self.rowCount()
            # insert a new row at position targetRow
            self.insertRow(targetRow)
            # but now - if sourceRow after target row, sourceRow has moved by 1.
            if targetRow < sourceRow:
                sourceRow += 1
            # move items from the sourceRow to the new targetRow
            for col in range(0, self.columnCount()):
                self.setItem(targetRow, col, self.takeItem(sourceRow, col))
            self.selectRow(targetRow)
            self.removeRow(sourceRow)
            event.accept()

    def rename_current_tab(self):
        # this is really a method for the current tab, not current row
        # TODO: perhaps this method is in the wrong place
        curtab_widget = self.parent.RTW.currentWidget()
        if not curtab_widget:
            return
        curname = curtab_widget.shortname
        s1, ok1 = QInputDialog.getText(
            self, 'Rename tab "{}"'.format(curname), "Enter new name"
        )
        if not ok1:
            return
        # TODO: hint that "wh&ot" will enable "alt-o" shortcut on most OSes
        # TODO: use a custom dialog
        # s2, ok2 = QInputDialog.getText(
        #     self, 'Rename tab "{}"'.format(curname), "Enter long name"
        # )
        log.debug('refresh tab text from "%s" to "%s"', curname, s1)
        curtab_widget.set_name(s1)

    def appendByKey(self, key):
        """Append the rubric associated with a key to the end of the list

        If its a dupe, don't add.

        args
            key (str/int?): the key associated with a rubric.

        raises
            what happens on invalid key?
        """
        # TODO: hmmm, should be dict?
        (rubric,) = [x for x in self.parent.rubrics if x["id"] == key]
        self.appendNewRubric(rubric)

    def appendNewRubric(self, rubric):
        rc = self.rowCount()
        # do sanity check for duplications
        for r in range(rc):
            if rubric["id"] == self.item(r, 0).text():
                return  # rubric already present
        # is a new rubric, so append it
        self.insertRow(rc)
        self.setItem(rc, 0, QTableWidgetItem(rubric["id"]))
        self.setItem(rc, 1, QTableWidgetItem(rubric["username"]))
        if rubric["kind"] == "absolute":
            self.setItem(rc, 2, QTableWidgetItem(rubric["delta"] + abs_suffix))
        else:
            self.setItem(rc, 2, QTableWidgetItem(rubric["delta"]))
        self.setItem(rc, 3, QTableWidgetItem(rubric["text"]))
        self.setItem(rc, 4, QTableWidgetItem(rubric["kind"]))
        # set row header
        self.setVerticalHeaderItem(rc, QTableWidgetItem("{}".format(rc + 1)))
        # set the legality
        self.colourLegalRubric(rc, self.parent.mss)
        # set a tooltip over delta that tells user the type of rubric
        self.item(rc, 2).setToolTip("{}-rubric".format(rubric["kind"]))
        # set a tooltip that contains tags and meta info when someone hovers over text
        hoverText = ""
        if rubric["tags"] != "":
            hoverText += "Tagged as {}\n".format(rubric["tags"])
        if rubric["meta"] != "":
            hoverText += "{}\n".format(rubric["meta"])
        self.item(rc, 3).setToolTip(hoverText.strip())

    def setRubricsByKeys(self, rubric_list, key_list):
        """Clear table and repopulate rubrics in the key_list"""
        # remove everything
        for r in range(self.rowCount()):
            self.removeRow(0)
        # since populating in order of key_list, build all keys from rubric_list
        rkl = [X["id"] for X in rubric_list]
        for id in key_list:
            try:  # guard against mysterious keys - should not happen unless people doing silliness
                rb = rubric_list[rkl.index(id)]
            except (ValueError, KeyError, IndexError):
                continue
            self.appendNewRubric(rb)

        self.resizeColumnsToContents()

    def setDeltaRubrics(self, rubrics):
        """Clear table and repopulate with delta-rubrics"""
        # remove everything
        for r in range(self.rowCount()):
            self.removeRow(0)
        # grab the delta-rubrics from the rubricslist
        delta_rubrics = []
        for rb in rubrics:
            # take the manager generated delta rubrics
            if rb["username"] == "manager" and rb["kind"] == "delta":
                delta_rubrics.append(rb)

        # now sort in numerical order away from 0 and add
        for rb in sorted(delta_rubrics, key=lambda r: abs(int(r["delta"]))):
            self.appendNewRubric(rb)

    def getKeyFromRow(self, row):
        return self.item(row, 0).text()

    def getKeyList(self):
        return [self.item(r, 0).text() for r in range(self.rowCount())]

    def getRowFromKey(self, key):
        for r in range(self.rowCount()):
            if int(self.item(r, 0).text()) == int(key):
                return r
        else:
            return None

    def getCurrentRubricRow(self):
        if not self.selectedIndexes():
            return None
        return self.selectedIndexes()[0].row()

    def getCurrentRubricKey(self):
        if not self.selectedIndexes():
            return None
        return self.item(self.selectedIndexes()[0].row(), 0).text()

    def reselectCurrentRubric(self):
        # If no selected row, then select row 0.
        # else select current row - triggers a signal.
        r = self.getCurrentRubricRow()
        if r is None:
            if self.rowCount() == 0:
                return
            else:
                r = 0
        self.selectRubricByVisibleRow(r)

    def selectRubricByRow(self, r):
        """Select the r'th rubric in the list

        Args:
            r (int): The row-number in the rubric-table.
            If r is None, do nothing.
        """
        if r is not None:
            self.selectRow(r)

    def selectRubricByVisibleRow(self, r):
        """Select the r'th **visible** row

        Args:
            r (int): The row-number in the rubric-table.
            If r is None, do nothing.
        """
        rc = -1  # start here, so that correctly test after-increment
        for s in range(self.rowCount()):
            if not self.isRowHidden(s):
                rc += 1
            if rc == r:
                self.selectRow(s)
                return
        return

    def selectRubricByKey(self, key):
        """Select row with given key. Return true if works, else false"""
        if key is None:
            return False
        for r in range(self.rowCount()):
            if int(self.item(r, 0).text()) == int(key):
                self.selectRow(r)
                return True
        return False

    def nextRubric(self):
        """Move selection to the next row, wrapping around if needed."""
        r = self.getCurrentRubricRow()
        if r is None:
            if self.rowCount() >= 1:
                self.selectRubricByVisibleRow(0)
                self.handleClick()  # actually force a click
            return
        rs = r  # get start row
        while True:  # move until we get back to start or hit unhidden row
            r = (r + 1) % self.rowCount()
            if r == rs or not self.isRowHidden(r):
                break
        self.selectRubricByRow(r)  # we know that row is not hidden
        self.handleClick()

    def previousRubric(self):
        """Move selection to the prevoous row, wrapping around if needed."""
        r = self.getCurrentRubricRow()
        if r is None:
            if self.rowCount() >= 1:
                self.selectRubricByRow(self.lastUnhiddenRow())
            return
        rs = r  # get start row
        while True:  # move until we get back to start or hit unhidden row
            r = (r - 1) % self.rowCount()
            if r == rs or not self.isRowHidden(r):
                break
        self.selectRubricByRow(r)
        self.handleClick()

    def handleClick(self):
        # When an item is clicked, grab the details and emit rubric signal [key, delta, text]
        r = self.getCurrentRubricRow()
        if r is None:
            r = self.firstUnhiddenRow()
            if r is None:  # there is nothing unhidden here.
                return
            self.selectRubricByRow(r)
        # recall columns are ["Key", "Username", "Delta", "Text", "Kind"])
        # absolute rubrics have trailing suffix - remove before sending signal
        delta = self.item(r, 2).text()
        if self.item(r, 4).text() == "absolute":
            delta = self.item(r, 2).text()[:-abs_suffix_length]

        self.parent.rubricSignal.emit(  # send delta, text, rubricID, kind
            [
                delta,
                self.item(r, 3).text(),
                self.item(r, 0).text(),
                self.item(r, 4).text(),
            ]
        )

    def firstUnhiddenRow(self):
        for r in range(self.rowCount()):
            if not self.isRowHidden(r):
                return r
        return None

    def lastUnhiddenRow(self):
        for r in reversed(range(self.rowCount())):
            if not self.isRowHidden(r):
                return r
        return None

    def colourLegalRubric(self, r, mss):
        # recall columns are ["Key", "Username", "Delta", "Text", "Kind"])
        legal = isLegalRubric(
            mss, kind=self.item(r, 4).text(), delta=self.item(r, 2).text()
        )
        if legal == 2:
            self.showRow(r)
            self.item(r, 2).setForeground(colour_legal)
            self.item(r, 3).setForeground(colour_legal)
        elif legal == 1:
            self.showRow(r)
            self.item(r, 2).setForeground(colour_illegal)
            self.item(r, 3).setForeground(colour_illegal)
        else:
            self.hideRow(r)

    def updateLegalityOfDeltas(self, mss):
        """Style items according to their legality based on max,state and score (mss)"""
        for r in range(self.rowCount()):
            self.colourLegalRubric(r, mss)

    def editRow(self, tableIndex):
        r = tableIndex.row()
        rubricKey = self.item(r, 0).text()
        self.parent.edit_rubric(rubricKey)

    def updateRubric(self, new_rubric, mss):
        for r in range(self.rowCount()):
            if self.item(r, 0).text() == new_rubric["id"]:
                self.item(r, 1).setText(new_rubric["username"])
                self.item(r, 2).setText(new_rubric["delta"])
                self.item(r, 3).setText(new_rubric["text"])
                self.item(r, 4).setText(new_rubric["kind"])
                # update the legality
                self.colourLegalRubric(r, mss)
                # set a tooltip that contains tags and meta info when someone hovers over text
                hoverText = ""
                if new_rubric["tags"] != "":
                    hoverText += "Tagged as {}\n".format(new_rubric["tags"])
                if new_rubric["meta"] != "":
                    hoverText += "{}\n".format(new_rubric["meta"])
                self.item(r, 3).setToolTip(hoverText.strip())


class RubricWidget(QWidget):
    # This is picked up by the annotator and tells is what is
    # the current comment and delta
    rubricSignal = pyqtSignal(list)  # pass the rubric's [key, delta, text, kind]

    def __init__(self, parent):
        # layout the widget - a table and add/delete buttons.
        super(RubricWidget, self).__init__()
        self.test_name = None
        self.question_number = None
        self.tgv = None
        self.parent = parent
        self.username = parent.username
        self.maxMark = None
        self.currentScore = None
        self.rubrics = None

        grid = QGridLayout()
        # assume our container will deal with margins
        grid.setContentsMargins(0, 0, 0, 0)
        delta_label = "\N{Plus-minus Sign}\N{Greek Small Letter Delta}"
        default_user_tabs = ["\N{Black Star}", "\N{Black Heart Suit}"]
        self.tabS = RubricTable(self, shortname="Shared", tabType="show")
        self.tabDelta = RubricTable(self, shortname=delta_label, tabType="delta")
        self.RTW = QTabWidget()
        self.RTW.setMovable(True)
        self.RTW.tabBar().setChangeCurrentOnDrag(True)
        self.RTW.addTab(self.tabS, self.tabS.shortname)
        for name in default_user_tabs:
            tab = RubricTable(self, shortname=name)
            self.RTW.addTab(tab, tab.shortname)
        self.RTW.addTab(self.tabDelta, self.tabDelta.shortname)
        self.RTW.setCurrentIndex(0)  # start on shared tab
        self.tabHide = RubricTable(self, sort=True, tabType="hide")
        self.groupHide = QTabWidget()
        self.groupHide.addTab(self.tabHide, "Hidden")
        self.showHideW = QStackedWidget()
        self.showHideW.addWidget(self.RTW)
        self.showHideW.addWidget(self.groupHide)
        grid.addWidget(self.showHideW, 1, 1, 2, 4)
        self.addB = QPushButton("Add")
        self.filtB = QPushButton("Arrange/Filter")
        self.hideB = QPushButton("Shown/Hidden")
        self.otherB = QToolButton()
        self.otherB.setText("\N{Anticlockwise Open Circle Arrow}")
        grid.addWidget(self.addB, 3, 1)
        grid.addWidget(self.filtB, 3, 2)
        grid.addWidget(self.hideB, 3, 3)
        grid.addWidget(self.otherB, 3, 4)
        grid.setSpacing(0)
        self.setLayout(grid)
        # connect the buttons to functions.
        self.addB.clicked.connect(self.add_new_rubric)
        self.filtB.clicked.connect(self.wrangleRubrics)
        self.otherB.clicked.connect(self.refreshRubrics)
        self.hideB.clicked.connect(self.toggleShowHide)

    def toggleShowHide(self):
        if self.showHideW.currentIndex() == 0:  # on main lists
            # move to hidden list
            self.showHideW.setCurrentIndex(1)
            # disable a few buttons
            self.addB.setEnabled(False)
            self.filtB.setEnabled(False)
            self.otherB.setEnabled(False)
            # reselect the current rubric
            self.tabHide.handleClick()
        else:
            # move to main list
            self.showHideW.setCurrentIndex(0)
            # enable buttons
            self.addB.setEnabled(True)
            self.filtB.setEnabled(True)
            self.otherB.setEnabled(True)
            # reselect the current rubric
            self.handleClick()

    @property
    def user_tabs(self):
        """Dynamically construct the ordered list of user-defined tabs."""
        # this is all tabs: we want only the user ones
        # return [self.RTW.widget(n) for n in range(self.RTW.count())]
        L = []
        for n in range(self.RTW.count()):
            tab = self.RTW.widget(n)
            if tab.is_user_tab():
                L.append(tab)
        return L

    def update_tab_names(self):
        """Loop over the tabs and update their displayed names"""
        for n in range(self.RTW.count()):
            self.RTW.setTabText(n, self.RTW.widget(n).shortname)
            # self.RTW.setTabToolTip(n, self.RTW.widget(n).longname)

    def add_new_tab(self, name=None):
        """Add new user-defined tab either to end or near end.

        If the delta tab is last, insert before that.  Otherwise append
        to the end of tab list.

        args:
            name (str/None): name of the new tab.  If omitted or None,
                generate one from a set of symbols with digits appended
                if necessary.
        """
        if not name:
            tab_names = [x.shortname for x in self.user_tabs]
            name = next_in_longest_subsequence(tab_names)
        if not name:
            syms = (
                "\N{Black Star}",
                "\N{Black Heart Suit}",
                "\N{Black Spade Suit}",
                "\N{Black Diamond Suit}",
                "\N{Black Club Suit}",
                "\N{Double Dagger}",
                "\N{Floral Heart}",
                "\N{Rotated Floral Heart Bullet}",
            )
            extra = ""
            counter = 0
            while not name:
                for s in syms:
                    if s + extra not in tab_names:
                        name = s + extra
                        break
                counter += 1
                extra = f"{counter}"

        tab = RubricTable(self, shortname=name)
        n = self.RTW.count()
        if n >= 1 and (
            self.RTW.widget(n - 1).is_delta_tab()
            or self.RTW.widget(n - 1).is_absolute_tab()
        ):
            self.RTW.insertTab(n - 1, tab, tab.shortname)
        else:
            self.RTW.addTab(tab, tab.shortname)

    def refreshRubrics(self):
        """Get rubrics from server and if non-trivial then repopulate"""
        new_rubrics = self.parent.getRubrics()
        if new_rubrics is not None:
            self.rubrics = new_rubrics
            self.wrangleRubrics()
        # do legality of deltas check
        self.updateLegalityOfDeltas()

    def wrangleRubrics(self):
        wr = RubricWrangler(
            self.rubrics,
            self.get_tab_rubric_lists(),
            self.username,
            annotator_size=self.parent.size(),
        )
        if wr.exec_() != QDialog.Accepted:
            return
        else:
            self.setRubricsFromState(wr.wranglerState)
            # ask annotator to save this stuff back to marker
            self.parent.saveWranglerState(wr.wranglerState)

    def setInitialRubrics(self):
        """Grab rubrics from server and set sensible initial values. Called after annotator knows its tgv etc."""

        self.rubrics = self.parent.getRubrics()
        wranglerState = {
            "user_tab_names": [],
            "shown": [],
            "hidden": [],
            "tabs": [],
        }

        for X in self.rubrics:
            # exclude HALs system-rubrics
            if X["username"] == "HAL":
                continue
            # exclude manager-delta rubrics
            if X["username"] == "manager" and X["kind"] == "delta":
                continue
            wranglerState["shown"].append(X["id"])
        # then set state from this
        self.setRubricsFromState(wranglerState)

    def setRubricsFromState(self, wranglerState):
        """Set rubric tabs (but not rubrics themselves) from saved data.

        The various rubric tabs are updated based on data passed in.
        The rubrics themselves are uneffected.

        args:
            wranglerState (dict): should be documented elsewhere and
                linked here but must contain at least `shown`, `hidden`,
                `tabs`, and `user_tab_names`.  The last two may be empty
                lists.  Subject to change without notice, your milleage
                may vary, etc.

        If there is too much data for the number of data, the extra data
        is discarded.  If there is too few data, pad with empty lists
        and/or leave the current lists as they are.

        TODO: if new Annotator, we may want to clear the tabs before
        calling this.
        """
        # zip truncates shorter list incase of length mismatch
        # for tab, name in zip(self.user_tabs, wranglerState["user_tab_names"]):
        #    tab.set_name(name)
        curtabs = self.user_tabs
        newnames = wranglerState["user_tab_names"]
        for n in range(max(len(curtabs), len(newnames))):
            if n < len(curtabs):
                if n < len(newnames):
                    curtabs[n].set_name(newnames[n])
            else:
                if n < len(newnames):
                    self.add_new_tab(newnames[n])
        del curtabs

        # compute legality for putting things in tables
        for n, tab in enumerate(self.user_tabs):
            if n >= len(wranglerState["tabs"]):
                # not enough data for number of tabs
                idlist = []
            else:
                idlist = wranglerState["tabs"][n]
            tab.setRubricsByKeys(
                self.rubrics,
                idlist,
            )
        self.tabS.setRubricsByKeys(
            self.rubrics,
            wranglerState["shown"],
        )
        self.tabDelta.setDeltaRubrics(
            self.rubrics,
        )
        self.tabHide.setRubricsByKeys(
            self.rubrics,
            wranglerState["hidden"],
        )

        # make sure something selected in each tab
        self.tabHide.selectRubricByVisibleRow(0)
        self.tabDelta.selectRubricByVisibleRow(0)
        self.tabS.selectRubricByVisibleRow(0)
        for tab in self.user_tabs:
            tab.selectRubricByVisibleRow(0)

    def getCurrentRubricKeyAndTab(self):
        """return the current rubric key and the current tab.

        returns:
            list: [a,b] where a=rubric-key=(int/none) and b=current tab index = int
        """
        return [
            self.RTW.currentWidget().getCurrentRubricKey(),
            self.RTW.currentIndex(),
        ]

    def setCurrentRubricKeyAndTab(self, key, tab):
        """set the current rubric key and the current tab

        args
            key (int/None): which rubric to highlight.  If no None, no action.
            tab (int): which tab to choose.

        returns:
            bool: True if we set a row, False if we could not find an appropriate row
                b/c for example key or tab are invalid or not found.
        """
        if key is None:
            return False
        if tab in range(0, self.RTW.count()):
            self.RTW.setCurrentIndex(tab)
        else:
            return False
        return self.RTW.currentWidget().selectRubricByKey(key)

    def setQuestionNumber(self, qn):
        """Set question number being graded.

        args:
            qn (int/None): the question number.
        """
        self.question_number = qn

    def setTestName(self, tn):
        self.test_name = tn

    def reset(self):
        """Return the widget to a no-TGV-specified state."""
        self.setQuestionNumber(None)
        self.setTestName(None)
        log.debug("TODO - what else needs doing on reset")

    def changeMark(self, currentScore, currentState, maxMark=None):
        # Update the current and max mark and so recompute which deltas are displayed
        if maxMark:
            self.maxMark = maxMark
        self.currentScore = currentScore
        self.currentState = currentState
        self.mss = [self.maxMark, self.currentState, self.currentScore]
        self.updateLegalityOfDeltas()

    def updateLegalityOfDeltas(self):
        # now redo each tab
        self.tabS.updateLegalityOfDeltas(self.mss)
        self.tabDelta.updateLegalityOfDeltas(self.mss)
        for tab in self.user_tabs:
            tab.updateLegalityOfDeltas(self.mss)

    def handleClick(self):
        self.RTW.currentWidget().handleClick()

    def reselectCurrentRubric(self):
        self.RTW.currentWidget().reselectCurrentRubric()
        self.handleClick()

    def selectRubricByRow(self, rowNumber):
        self.RTW.currentWidget().selectRubricByRow(rowNumber)
        self.handleClick()

    def selectRubricByVisibleRow(self, rowNumber):
        self.RTW.currentWidget().selectRubricByVisibleRow(rowNumber)
        self.handleClick()

    def nextRubric(self):
        # change rubrics in the correct tab
        if self.showHideW.currentIndex() == 0:
            self.RTW.currentWidget().nextRubric()
        else:
            self.tabHide.nextRubric()

    def previousRubric(self):
        # change rubrics in the correct tab
        if self.showHideW.currentIndex() == 0:
            self.RTW.currentWidget().previousRubric()
        else:
            self.tabHide.previousRubric()

    def next_tab(self):
        """Move to next tab, only if tabs are shown."""
        if self.showHideW.currentIndex() == 0:
            numtabs = self.RTW.count()
            self.RTW.setCurrentIndex((self.RTW.currentIndex() + 1) % numtabs)
            self.handleClick()

    def prev_tab(self):
        """Move to previous tab, only if tabs are shown."""
        if self.showHideW.currentIndex() == 0:
            numtabs = self.RTW.count()
            self.RTW.setCurrentIndex((self.RTW.currentIndex() - 1) % numtabs)
            self.handleClick()

    def get_nonrubric_text_from_page(self):
        """Find any text that isn't already part of a formal rubric.

        Returns:
            list: strings for each text on page that is not inside a rubric
        """
        return self.parent.get_nonrubric_text_from_page()

    def unhideRubricByKey(self, key):
        index = [x["id"] for x in self.rubrics].index(key)
        self.tabS.appendNewRubric(self.rubrics[index])

    def hideRubricByKey(self, key):
        index = [x["id"] for x in self.rubrics].index(key)
        self.tabHide.appendNewRubric(self.rubrics[index])

    def add_new_rubric(self):
        """Open a dialog to create a new comment."""
        self._new_or_edit_rubric(None)

    def edit_rubric(self, key):
        """Open a dialog to edit a rubric - from the id-key of that rubric."""
        # first grab the rubric from that key
        try:
            index = [x["id"] for x in self.rubrics].index(key)
        except ValueError:
            # no such rubric - this should not happen
            return
        com = self.rubrics[index]

        if com["username"] == self.username:
            self._new_or_edit_rubric(com, edit=True, index=index)
            return
        msg = SimpleMessage(
            "<p>You did not create this message.</p>"
            "<p>To edit it, the system will make a copy that you can edit.</p>"
            "<p>Do you want to continue?</p>"
        )
        if msg.exec_() == QMessageBox.No:
            return
        com = com.copy()  # don't muck-up the original
        com["id"] = None
        com["username"] = self.username
        self._new_or_edit_rubric(com, edit=False)

    def _new_or_edit_rubric(self, com, edit=False, index=None):
        """Open a dialog to edit a comment or make a new one.

        args:
            com (dict/None): a comment to modify or use as a template
                depending on next arg.  If set to None, which always
                means create new.
            edit (bool): are we modifying the comment?  if False, use
                `com` as a template for a new duplicated comment.
            index (int): the index of the comment inside the current rubric list
                used for updating the data in the rubric list after edit (only)

        Returns:
            None: does its work through side effects on the comment list.
        """
        if self.question_number is None:
            log.error("Not allowed to create rubric while question number undefined.")
            return
        reapable = self.get_nonrubric_text_from_page()
        arb = AddRubricBox(
            self.username,
            self.maxMark,
            reapable,
            com,
            annotator_size=self.parent.size(),
        )
        if arb.exec_() != QDialog.Accepted:
            return
        if arb.DE.checkState() == Qt.Checked:
            dlt = str(arb.SB.textFromValue(arb.SB.value()))
        else:
            dlt = "."
        txt = arb.TE.toPlainText().strip()
        if len(txt) <= 0:
            return
        tag = arb.TEtag.toPlainText().strip()
        meta = arb.TEmeta.toPlainText().strip()
        kind = arb.Lkind.text().strip()
        username = arb.Luser.text().strip()
        # only meaningful if we're modifying
        rubricID = arb.label_rubric_id.text().strip()

        new_rubric = {
            "kind": kind,
            "delta": dlt,
            "text": txt,
            "tags": tag,
            "meta": meta,
            "username": self.username,
            "question": self.question_number,
        }

        if edit:
            new_rubric["id"] = rubricID
            rv = self.parent.modifyRubric(rubricID, new_rubric)
            # update the rubric in the current internal rubric list
            # make sure that keys match.
            assert self.rubrics[index]["id"] == new_rubric["id"]
            # then replace
            self.rubrics[index] = new_rubric
            # update the rubric in all lists
            self.updateRubricInLists(new_rubric)
        else:
            rv = self.parent.createNewRubric(new_rubric)
            # check was updated/created successfully
            if not rv[0]:  # some sort of creation problem
                return
            # created ok
            rubricID = rv[1]
            new_rubric["id"] = rubricID
            # at this point we have an accepted new rubric
            # add it to the internal list of rubrics
            self.rubrics.append(new_rubric)
            # append the rubric to the shownList
            self.tabS.appendNewRubric(new_rubric)
            # also add it to the list in the current rubriclist (if different)
            if self.RTW.currentWidget() != self.tabS:
                self.RTW.currentWidget().appendNewRubric(new_rubric)
        # finally - select that rubric and simulate a click
        self.RTW.currentWidget().selectRubricByKey(rubricID)
        self.handleClick()

    def updateRubricInLists(self, new_rubric):
        self.tabS.updateRubric(new_rubric, self.mss)
        self.tabHide.updateRubric(new_rubric, self.mss)
        for tab in self.user_tabs:
            tab.updateRubric(new_rubric, self.mss)

    def get_tab_rubric_lists(self):
        """returns a dict of lists of the current rubrics"""
        return {
            "user_tab_names": [t.shortname for t in self.user_tabs],
            "shown": self.tabS.getKeyList(),
            "hidden": self.tabHide.getKeyList(),
            "tabs": [t.getKeyList() for t in self.user_tabs],
        }


class SignedSB(QSpinBox):
    # add an explicit sign to spinbox and no 0
    # range is from -(N+1),..,-1,1,...(N-1)
    def __init__(self, maxMark):
        super().__init__()
        self.setRange(-maxMark + 1, maxMark - 1)
        self.setValue(1)

    def stepBy(self, steps):
        self.setValue(self.value() + steps)
        # to skip 0.
        if self.value() == 0:
            self.setValue(self.value() + steps)

    def textFromValue(self, n):
        t = QSpinBox().textFromValue(n)
        if n > 0:
            return "+" + t
        else:
            return t


class AddRubricBox(QDialog):
    def __init__(self, username, maxMark, lst, com=None, annotator_size=None):
        """Initialize a new dialog to edit/create a comment.

        Args:
            username (str)
            maxMark (int)
            lst (list): these are used to "harvest" plain 'ol text
                annotations and morph them into comments.
            com (dict/None): if None, we're creating a new rubric.
                Otherwise, this has the current comment data.
            annotator_size (QSize/None): size of the parent annotator
        """
        super().__init__()

        if com:
            self.setWindowTitle("Modify rubric")
        else:
            self.setWindowTitle("Add new rubric")

        ## Set self to be 1/2 the size of the annotator
        if annotator_size:
            self.resize(annotator_size / 2)
        ##
        self.CB = QComboBox()
        self.TE = QTextEdit()
        self.SB = SignedSB(maxMark)
        self.DE = QCheckBox("enabled")
        self.DE.setCheckState(Qt.Checked)
        self.DE.stateChanged.connect(self.toggleSB)
        self.TEtag = QTextEdit()
        self.TEmeta = QTextEdit()
        # cannot edit these
        self.label_rubric_id = QLabel("Will be auto-assigned")
        self.Luser = QLabel()
        self.Lkind = QLabel("relative")

        sizePolicy = QSizePolicy(
            QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding
        )
        sizePolicy.setVerticalStretch(3)

        print(self.size())
        ##
        self.TE.setSizePolicy(sizePolicy)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sizePolicy.setVerticalStretch(1)
        self.TEtag.setSizePolicy(sizePolicy)
        self.TEmeta.setSizePolicy(sizePolicy)
        # TODO: make everything wider!

        flay = QFormLayout()
        flay.addRow("Enter text", self.TE)
        lay = QFormLayout()
        lay.addRow("or choose text", self.CB)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.CB.setSizePolicy(sizePolicy)
        flay.addRow("", lay)
        lay = QHBoxLayout()
        lay.addWidget(self.DE)
        lay.addItem(QSpacerItem(48, 10, QSizePolicy.Preferred, QSizePolicy.Minimum))
        lay.addWidget(self.SB)
        flay.addRow("Delta mark", lay)
        flay.addRow("Tags", self.TEtag)
        flay.addRow("Meta", self.TEmeta)

        flay.addRow("kind", self.Lkind)
        flay.addRow("Rubric ID", self.label_rubric_id)
        flay.addRow("User who created", self.Luser)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        vlay = QVBoxLayout()
        vlay.addLayout(flay)
        vlay.addWidget(buttons)
        self.setLayout(vlay)

        # set up widgets
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.CB.addItem("")
        self.CB.addItems(lst)
        # Set up TE and CB so that when CB changed, text is updated
        self.CB.currentTextChanged.connect(self.changedCB)
        # If supplied with current text/delta then set them

        if com:
            if com["text"]:
                self.TE.clear()
                self.TE.insertPlainText(com["text"])
            if com["tags"]:
                self.TEtag.clear()
                self.TEtag.insertPlainText(com["tags"])
            if com["meta"]:
                self.TEmeta.clear()
                self.TEmeta.insertPlainText(com["meta"])
            if com["delta"]:
                if com["delta"] == ".":
                    self.SB.setValue(0)
                    self.DE.setCheckState(Qt.Unchecked)
                else:
                    self.SB.setValue(int(com["delta"]))
            if com["id"]:
                self.label_rubric_id.setText(str(com["id"]))
            if com["username"]:
                self.Luser.setText(com["username"])
        else:
            self.TE.setPlaceholderText(
                'Prepend with "tex:" to use math.\n\n'
                'You can "choose text" to harvest existing text from the page.\n\n'
                'Change "delta" below to associate a point-change.'
            )
            self.TEtag.setPlaceholderText(
                "For any user tags you might want. (mostly future use)"
            )
            self.TEmeta.setPlaceholderText(
                "Notes about this rubric such as hints on when to use it.\n\n"
                "Not shown to student!"
            )
            self.Luser.setText(username)

    def changedCB(self):
        self.TE.clear()
        self.TE.insertPlainText(self.CB.currentText())

    def toggleSB(self):
        if self.DE.checkState() == Qt.Checked:
            self.SB.setEnabled(True)
            self.Lkind.setText("relative")
        else:
            self.Lkind.setText("neutral")
            self.SB.setEnabled(False)