#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "Andrew Rechnitzer"
__copyright__ = "Copyright (C) 2018-2020 Andrew Rechnitzer"
__credits__ = ["Andrew Rechnitzer", "Colin Macdonald", "Elvis Cai", "Matt Coles"]
__license__ = "AGPL-3.0-or-later"
# SPDX-License-Identifier: AGPL-3.0-or-later


import toml
import os
import datetime
import logging

from PyQt5.QtCore import pyqtSlot, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QDialog, QStyleFactory, QMessageBox

from .uiFiles.ui_chooser import Ui_Chooser
from .useful_classes import ErrorMessage, SimpleMessage, ClientSettingsDialog
from plom.plom_exceptions import *
from . import marker
from . import identifier
from . import totaler
from plom import __version__
from plom import Plom_API_Version
from plom import Default_Port
from plom.messenger import Messenger
# TODO: for now, a global (to this module), later maybe in the QApp?
messenger = None

# set up variables to store paths for marker and id clients
global tempDirectory, directoryPath
# to store login + options for next run of client.
lastTime = {}

log = logging.getLogger("client")


def readLastTime():
    """Read the login + server options that were used on
    the last run of the client.
    """
    global lastTime
    # set some reasonable defaults.
    lastTime["user"] = ""
    lastTime["server"] = "localhost"
    lastTime["pg"] = 1
    lastTime["v"] = 1
    lastTime["fontSize"] = 10
    lastTime["upDown"] = "up"
    lastTime["mouse"] = "right"
    # If config file exists, use it to update the defaults
    if os.path.isfile("plomConfig.toml"):
        with open("plomConfig.toml") as data_file:
            lastTime.update(toml.load(data_file))


def writeLastTime():
    """Write the options to the config file."""
    log.info("Saving config file: plomConfig.toml")
    try:
        with open("plomConfig.toml", "w") as fh:
            fh.write(toml.dumps(lastTime))
    except PermissionError as e:
        ErrorMessage(
            "Cannot write config file!\n\n"
            "Try moving the Plom client to somewhere else on your"
            "system where you have write permissions.\n\n"
            "{}.".format(e)
        ).exec_()
        QApplication.exit(1)


class Chooser(QDialog):
    def __init__(self, Qapp):
        self.APIVersion = Plom_API_Version
        super(Chooser, self).__init__()
        self.parent = Qapp

        readLastTime()

        if lastTime.get("LogToFile"):
            now = datetime.datetime.now().isoformat("T", "seconds")
            logging.basicConfig(
                format="%(asctime)s %(levelname)5s:%(name)s\t%(message)s",
                datefmt="%m-%d %H:%M:%S",
                filename="plom-{}.log".format(now),
            )
        else:
            logging.basicConfig(
                format="%(asctime)s %(levelname)5s:%(name)s\t%(message)s",
                datefmt="%m-%d %H:%M:%S",
            )
        # Default to INFO log level
        logging.getLogger().setLevel(lastTime.get("LogLevel", "Info").upper())

        s = "Plom Client {} (communicates with api {})".format(
            __version__, self.APIVersion
        )
        log.info(s)
        # runit = either marker or identifier clients.
        self.runIt = None

        self.ui = Ui_Chooser()
        self.ui.setupUi(self)
        # Append version to window title
        self.setWindowTitle("{} {}".format(self.windowTitle(), __version__))
        self.setLastTime()
        # connect buttons to functions.
        self.ui.markButton.clicked.connect(self.runMarker)
        self.ui.identifyButton.clicked.connect(self.runIDer)
        self.ui.totalButton.clicked.connect(self.runTotaler)
        self.ui.closeButton.clicked.connect(self.closeWindow)
        self.ui.fontButton.clicked.connect(self.setFont)
        self.ui.optionsButton.clicked.connect(self.options)
        self.ui.getServerInfoButton.clicked.connect(self.getInfo)
        self.ui.serverLE.textEdited.connect(self.ungetInfo)
        self.ui.mportSB.valueChanged.connect(self.ungetInfo)
        self.ui.vDrop.setVisible(False)
        self.ui.pgDrop.setVisible(False)

    def setLastTime(self):
        # set login etc from last time client ran.
        self.ui.userLE.setText(lastTime["user"])
        self.setServer(lastTime["server"])
        self.ui.pgSB.setValue(int(lastTime["pg"]))
        self.ui.vSB.setValue(int(lastTime["v"]))
        self.ui.fontSB.setValue(int(lastTime["fontSize"]))
        self.setFont()

    def setServer(self, s):
        """Set the server and port UI widgets from a string.

        If port is missing, a default will be used."""
        try:
            s, p = s.split(":")
        except ValueError:
            p = Default_Port
        self.ui.serverLE.setText(s)
        self.ui.mportSB.setValue(int(p))

    def options(self):
        d = ClientSettingsDialog(lastTime)
        d.exec_()
        # TODO: do something more proper like QSettings
        stuff = d.getStuff()
        lastTime["FOREGROUND"] = stuff[0]
        lastTime["LogLevel"] = stuff[1]
        lastTime["LogToFile"] = stuff[2]
        logging.getLogger().setLevel(lastTime["LogLevel"].upper())

    def validate(self):
        # Check username is a reasonable string
        user = self.ui.userLE.text()
        if (not user.isalnum()) or (not user):
            return
        # check password at least 4 char long
        pwd = self.ui.passwordLE.text()
        if len(pwd) < 4:
            log.warning("Password too short")
            return
        server = self.ui.serverLE.text()
        if not server:
            log.warning("No server URI")
            return
        mport = self.ui.mportSB.value()
        # save those settings
        self.saveDetails()

        try:
            # TODO: re-use existing messenger?
            messenger = Messenger(server, mport)
            messenger.start()
        except PlomBenignException as e:
            ErrorMessage("Could not connect to server.\n\n" "{}".format(e)).exec_()
            return

        try:
            messenger.requestAndSaveToken(user, pwd)
        except PlomAPIException as e:
            ErrorMessage(
                "Could not authenticate due to API mismatch."
                "Your client version is {}.\n\n"
                "Error was: {}".format(__version__, e)
            ).exec_()
            return
        except PlomAuthenticationException as e:
            ErrorMessage("Could not authenticate: {}".format(e)).exec_()
            return
        except PlomExistingLoginException as e:
            if (
                SimpleMessage(
                    "You appear to be already logged in!\n\n"
                    "  * Perhaps a previous session crashed?\n"
                    "  * Do you have another client running,\n"
                    "    e.g., on another computer?\n\n"
                    "Should I force-logout the existing authorisation?"
                    " (and then you can try to log in again)\n\n"
                    "The other client will likely crash."
                ).exec_()
                == QMessageBox.Yes
            ):
                messenger.clearAuthorisation(user, pwd)
            return

        except PlomSeriousException as e:
            ErrorMessage(
                "Could not get authentication token.\n\n"
                "Unexpected error: {}".format(e)
            ).exec_()
            return

        # Now run the appropriate client sub-application
        if self.runIt == "Marker":
            # Run the marker client.
            pg = self.getpg()
            v = self.getv()
            self.setEnabled(False)
            self.hide()
            markerwin = marker.MarkerClient(self.parent)
            markerwin.my_shutdown_signal.connect(self.on_marker_window_close)
            markerwin.show()
            markerwin.getToWork(messenger, pg, v, lastTime)
            self.parent.marker = markerwin
        elif self.runIt == "IDer":
            # Run the ID client.
            self.setEnabled(False)
            self.hide()
            idwin = identifier.IDClient()
            idwin.my_shutdown_signal.connect(self.on_other_window_close)
            idwin.show()
            idwin.getToWork(messenger)
            self.parent.identifier = idwin
        else:
            # Run the Total client.
            self.setEnabled(False)
            self.hide()
            totalerwin = totaler.TotalClient()
            totalerwin.my_shutdown_signal.connect(self.on_other_window_close)
            totalerwin.show()
            totalerwin.getToWork(messenger)
            self.parent.totaler = totalerwin

    def runMarker(self):
        self.runIt = "Marker"
        self.validate()

    def runIDer(self):
        self.runIt = "IDer"
        self.validate()

    def runTotaler(self):
        self.runIt = "Totaler"
        self.validate()

    def saveDetails(self):
        lastTime["user"] = self.ui.userLE.text()
        lastTime["server"] = "{}:{}".format(
            self.ui.serverLE.text(), self.ui.mportSB.value()
        )
        lastTime["pg"] = self.getpg()
        lastTime["v"] = self.getv()
        lastTime["fontSize"] = self.ui.fontSB.value()
        writeLastTime()

    def closeWindow(self):
        self.saveDetails()
        if messenger:
            messenger.stop()
        self.close()

    def setFont(self):
        v = self.ui.fontSB.value()
        fnt = self.parent.font()
        fnt.setPointSize(v)
        self.parent.setFont(fnt)

    def getpg(self):
        """Return the integer question or None"""
        if self.ui.pgDrop.isVisible():
            pg = self.ui.pgDrop.currentText().lstrip("Q")
        else:
            pg = self.ui.pgSB.value()
        try:
            return int(pg)
        except:
            return None

    def getv(self):
        """Return the integer version or None"""
        if self.ui.vDrop.isVisible():
            v = self.ui.vDrop.currentText()
        else:
            v = self.ui.vSB.value()
        try:
            return int(v)
        except:
            return None

    def ungetInfo(self):
        self.ui.markGBox.setTitle("Marking information")
        pg = self.getpg()
        v = self.getv()
        self.ui.pgSB.setVisible(True)
        self.ui.vSB.setVisible(True)
        if pg:
            self.ui.pgSB.setValue(pg)
        if v:
            self.ui.vSB.setValue(v)
        self.ui.vDrop.clear()
        self.ui.vDrop.setVisible(False)
        self.ui.pgDrop.clear()
        self.ui.pgDrop.setVisible(False)
        self.ui.infoLabel.setText("")
        # TODO: just `del messenger`?
        global messenger
        if messenger:
            messenger.stop()
        messenger = None

    def getInfo(self):
        server = self.ui.serverLE.text()
        if not server:
            log.warning("No server URI")
            return
        mport = self.ui.mportSB.value()
        # save those settings
        # self.saveDetails()   # TODO?

        # TODO: might be nice, but needs another thread?
        # self.ui.infoLabel.setText("connecting...")
        # self.ui.infoLabel.repaint()

        try:
            messenger = Messenger(server, mport)
            r = messenger.start()
        except PlomBenignException as e:
            ErrorMessage("Could not connect to server.\n\n" "{}".format(e)).exec_()
            return
        self.ui.infoLabel.setText(r)

        info = messenger.getInfoGeneral()
        self.ui.markGBox.setTitle(
            "Marking information for “{}”".format(info["testName"])
        )
        pg = self.getpg()
        v = self.getv()
        self.ui.pgSB.setVisible(False)
        self.ui.vSB.setVisible(False)

        self.ui.vDrop.clear()
        self.ui.vDrop.addItems([str(x + 1) for x in range(0, info["numberOfVersions"])])
        if v:
            if v >= 1 and v <= info["numberOfVersions"]:
                self.ui.vDrop.setCurrentIndex(v - 1)
        self.ui.vDrop.setVisible(True)

        self.ui.pgDrop.clear()
        self.ui.pgDrop.addItems(
            ["Q{}".format(x + 1) for x in range(0, info["numberOfQuestions"])]
        )
        if pg:
            if pg >= 1 and pg <= info["numberOfQuestions"]:
                self.ui.pgDrop.setCurrentIndex(pg - 1)
        self.ui.pgDrop.setVisible(True)
        # TODO should we also let people type in?
        self.ui.pgDrop.setEditable(False)
        self.ui.vDrop.setEditable(False)
        # put focus at username or password line-edit
        if len(self.ui.userLE.text()) > 0:
            self.ui.passwordLE.setFocus(True)
        else:
            self.ui.userLE.setFocus(True)

    @pyqtSlot(int)
    def on_other_window_close(self, value):
        assert isinstance(value, int)
        self.show()
        self.setEnabled(True)

    @pyqtSlot(int, list)
    def on_marker_window_close(self, value, stuff):
        assert isinstance(value, int)
        self.show()
        self.setEnabled(True)
        if not stuff:
            return
        # update mouse-hand and up/down style for lasttime file
        markStyle, mouseHand = stuff
        global lastTime
        if markStyle == 2:
            lastTime["upDown"] = "up"
        elif markStyle == 3:
            lastTime["upDown"] = "down"
        else:
            raise RuntimeError("tertium non datur")
        if mouseHand == 0:
            lastTime["mouse"] = "right"
        elif mouseHand == 1:
            lastTime["mouse"] = "left"
        else:
            raise RuntimeError("tertium non datur")