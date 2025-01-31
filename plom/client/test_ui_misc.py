# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020, 2023 Colin B. Macdonald

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from plom.client.chooser import Chooser
from plom.client.useful_classes import BlankIDBox
from plom.client.useful_classes import BigMessageDialog


def test_BlankIDBoxDialog(qtbot):
    d = BlankIDBox(None, 16)
    d.show()
    qtbot.addWidget(d)
    qtbot.mouseClick(d.noB, Qt.MouseButton.LeftButton)
    assert d.testNumber == 16


def test_BlankIDBoxDialog2(qtbot):
    d = BlankIDBox(None, 32)
    d.show()
    qtbot.addWidget(d)
    qtbot.mouseClick(d.blankB, Qt.MouseButton.LeftButton)
    assert d.testNumber == 32


def DISABLE_test_Chooser(qtbot):
    app = QApplication([])
    window = Chooser(app)
    window.show()
    qtbot.add_widget(window)
    # TODO: only if a local server is running, otherwise pops the dialog
    qtbot.mouseClick(window.ui.getServerInfoButton, Qt.MouseButton.LeftButton)
    assert window.ui.infoLabel.text().startswith("Server address")
    # TODO: seems to pop open the (model) dialog
    # qtbot.mouseClick(window.ui.optionsButton, Qt.MouseButton.LeftButton)
    # TODO: password too short, generates log should be so testable
    qtbot.mouseClick(window.ui.markButton, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.ui.closeButton, Qt.MouseButton.LeftButton)


def DISABLE_test_Chooser_again(qtbot):
    # TODO: disabled as we cannot open another, maybe b/c this:
    # TODO: https://pytest-qt.readthedocs.io/en/3.3.0/app_exit.html
    app = QApplication([])
    window = Chooser(app)
    window.show()
    qtbot.addWidget(window)
    qtbot.mouseClick(window.ui.closeButton, Qt.MouseButton.LeftButton)


def test_BigMessageDialog_gets_big_then_small(qtbot):
    d = BigMessageDialog(None, "foo", details="<p>bar</p>", show=False)
    d.show()
    qtbot.addWidget(d)
    w = d.geometry().width()
    h = d.geometry().height()
    qtbot.mouseClick(d.toggle_button, Qt.MouseButton.LeftButton)
    w2 = d.geometry().width()
    h2 = d.geometry().height()
    # width is maintained
    assert w2 == w
    assert h2 > h
    qtbot.mouseClick(d.toggle_button, Qt.MouseButton.LeftButton)
    w3 = d.geometry().width()
    h3 = d.geometry().height()
    assert w3 == w
    assert h3 == h
    d.accept()
