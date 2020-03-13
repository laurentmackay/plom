__author__ = "Andrew Rechnitzer"
__copyright__ = "Copyright (C) 2019 Andrew Rechnitzer"
__credits__ = ["Andrew Rechnitzer", "Colin Macdonald"]
__license__ = "AGPLv3"

# TODO - directory structure!

# ----------------------

from aiohttp import web
import hashlib
import json
import os
import ssl
import subprocess
import sys
import tempfile
import uuid
import logging

# ----------------------

from .authenticate import Authority

from plom import __version__
from plom import Plom_API_Version as serverAPI
from plom import SpecParser
from plom.db.examDB import PlomDB

# ----------------------

serverInfo = {"server": "127.0.0.1", "mport": 41984}
# ----------------------
sslContext = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
sslContext.check_hostname = False
sslContext.load_cert_chain(
    "serverConfiguration/plom-selfsigned.crt", "serverConfiguration/plom.key"
)


from .plomServer.routesUserInit import UserInitHandler
from .plomServer.routesUpload import UploadHandler
from .plomServer.routesID import IDHandler
from .plomServer.routesMark import MarkHandler
from .plomServer.routesTotal import TotalHandler
from .plomServer.routesReport import ReportHandler


# 7 is wdith of "warning"
logging.basicConfig(
    format="%(asctime)s %(levelname)7s:%(name)s\t%(message)s", datefmt="%m-%d %H:%M:%S",
)
log = logging.getLogger("server")
# TODO: take from command line argument, debug to INFO
logging.getLogger().setLevel("Debug".upper())
# log.setLevel("Debug".upper())

log.info("Plom Server {} (communicates with api {})".format(__version__, serverAPI))


# ----------------------
def buildDirectories():
    """Build the directories that this script needs"""
    # the list of directories. Might need updating.
    lst = [
        "pages",
        "pages/discardedPages",
        "pages/collidingPages",
        "pages/unknownPages",
        "pages/originalPages",
        "markedQuestions",
        "markedQuestions/plomFiles",
        "markedQuestions/commentFiles",
    ]
    for dir in lst:
        try:
            os.mkdir(dir)
            log.debug("Building directory {}".format(dir))
        except FileExistsError:
            pass


# ----------------------


class Server(object):
    def __init__(self, spec, db):
        log.debug("Initialising server")
        self.testSpec = spec
        self.DB = db
        self.API = serverAPI
        self.Version = __version__
        self.tempDirectory = tempfile.TemporaryDirectory()
        # Give directory correct permissions.
        subprocess.check_call(["chmod", "o-r", self.tempDirectory.name])
        self.loadUsers()

    def loadUsers(self):
        """Load the users from json file, add them to the authority which
        handles authentication for us.
        """
        if os.path.exists("serverConfiguration/userList.json"):
            with open("serverConfiguration/userList.json") as data_file:
                # Load the users and pass them to the authority.
                self.userList = json.load(data_file)
                self.authority = Authority(self.userList)
            log.debug("Loading users")
        else:
            # Cannot find users - give error and quit out.
            log.error("Cannot find user/password file - aborting.")
            quit()

    def validate(self, user, token):
        """Check the user's token is valid"""
        # log.debug("Validating user {}.".format(user))
        return self.authority.validateToken(user, token)

    from .plomServer.serverUserInit import (
        InfoShortName,
        InfoGeneral,
        reloadUsers,
        giveUserToken,
        closeUser,
    )
    from .plomServer.serverUpload import (
        addKnownPage,
        addUnknownPage,
        addCollidingPage,
        replaceMissingPage,
        removeScannedPage,
        getUnknownPageNames,
        getDiscardNames,
        getCollidingPageNames,
        getUnknownImage,
        getCollidingImage,
        getDiscardImage,
        getPageImage,
        getQuestionImages,
        getTestImages,
        checkPage,
        removeUnknownImage,
        removeCollidingImage,
        unknownToTestPage,
        unknownToExtraPage,
        collidingToTestPage,
        discardToUnknown,
    )
    from .plomServer.serverID import (
        IDprogressCount,
        IDgetNextTask,
        IDgetDoneTasks,
        IDgetImage,
        IDgetRandomImage,
        IDclaimThisTask,
        IDdidNotFinish,
        IDreturnIDdTask,
        IDdeletePredictions,
        IDreviewID,
    )
    from .plomServer.serverMark import (
        MgetAllMax,
        MprogressCount,
        MgetQuestionMax,
        MgetDoneTasks,
        MgetNextTask,
        MlatexFragment,
        MclaimThisTask,
        MdidNotFinish,
        MrecordMark,
        MreturnMarkedTask,
        MgetImages,
        MgetOriginalImages,
        MsetTag,
        MgetWholePaper,
        MreviewQuestion,
        MrevertTask,
    )
    from .plomServer.serverTotal import (
        TgetMaxMark,
        TprogressCount,
        TgetDoneTasks,
        TgetNextTask,
        TclaimThisTask,
        TgetImage,
        TreturnTotalledTask,
        TdidNotFinish,
    )

    from .plomServer.serverReport import (
        RgetUnusedTests,
        RgetScannedTests,
        RgetIncompleteTests,
        RgetProgress,
        RgetQuestionUserProgress,
        RgetMarkHistogram,
        RgetIdentified,
        RgetCompletions,
        RgetStatus,
        RgetSpreadsheet,
        RgetCoverPageInfo,
        RgetOriginalFiles,
        RgetAnnotatedFiles,
        RgetMarkReview,
        RgetIDReview,
        RgetTotReview,
        RgetAnnotatedImage,
        RgetUserList,
        RgetUserDetails,
    )


def getServerInfo():
    """Read the server info from json."""
    global serverInfo
    if os.path.isfile("serverConfiguration/serverDetails.json"):
        with open("serverConfiguration/serverDetails.json") as data_file:
            serverInfo = json.load(data_file)
            log.info("Server details loaded: {}".format(serverInfo))
    else:
        log.warning("Cannot find server details.")


def launch():
    getServerInfo()
    examDB = PlomDB("specAndDatabase/plom.db")
    spec = SpecParser("specAndDatabase/verifiedSpec.toml").spec
    buildDirectories()
    peon = Server(spec, examDB)
    userIniter = UserInitHandler(peon)
    uploader = UploadHandler(peon)
    ider = IDHandler(peon)
    marker = MarkHandler(peon)
    totaller = TotalHandler(peon)
    reporter = ReportHandler(peon)

    try:
        # construct the web server
        app = web.Application()
        # add the routes
        log.info("Setting up routes")
        userIniter.setUpRoutes(app.router)
        uploader.setUpRoutes(app.router)
        ider.setUpRoutes(app.router)
        marker.setUpRoutes(app.router)
        totaller.setUpRoutes(app.router)
        reporter.setUpRoutes(app.router)
        # run the web server
        log.info("Start the server!")
        web.run_app(app, ssl_context=sslContext, port=serverInfo["mport"])
    except KeyboardInterrupt:
        log.info("Closing down")  # TODO: I never see this!
        pass