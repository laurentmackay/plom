#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "Andrew Rechnitzer"
__copyright__ = "Copyright (C) 2020 Andrew Rechnitzer and Colin Macdonald"
__credits__ = ["Andrew Rechnitzer", "Colin Macdonald"]
__license__ = "AGPL-3.0-or-later"
# SPDX-License-Identifier: AGPL-3.0-or-later

import argparse
import csv
import getpass

from plom.messenger import FinishMessenger
from plom.plom_exceptions import *

numberOfTests = 0
numberOfQuestions = 0
CSVFilename = "testMarks.csv"

# ----------------------


def writeSpreadsheet(spreadSheetDict):
    print(">>> Warning <<<")
    print(
        "This script currently outputs all scanned papers whether or not they have been marked completely."
    )

    head = ["StudentID", "StudentName", "TestNumber"]
    for q in range(1, numberOfQuestions + 1):
        head.append("Question {} Mark".format(q))
    head.append("Total")
    for q in range(1, numberOfQuestions + 1):
        head.append("Question {} Version".format(q))
    # add a warning column
    head.append("Warnings")

    with open(CSVFilename, "w") as csvfile:
        testWriter = csv.DictWriter(
            csvfile,
            fieldnames=head,
            delimiter="\t",
            quotechar='"',
            quoting=csv.QUOTE_NONNUMERIC,
        )
        testWriter.writeheader()
        for t in spreadSheetDict:
            thisTest = spreadSheetDict[t]
            if thisTest["marked"] is False:
                pass  # for testing only
                # continue
            row = {}
            row["StudentID"] = thisTest["sid"]
            row["StudentName"] = thisTest["sname"]
            row["TestNumber"] = int(t)
            tot = 0
            for q in range(1, numberOfQuestions + 1):
                if thisTest["marked"]:
                    tot += int(thisTest["q{}m".format(q)])
                row["Question {} Mark".format(q)] = thisTest["q{}m".format(q)]
                row["Question {} Version".format(q)] = thisTest["q{}v".format(q)]
            if thisTest["marked"]:
                row["Total"] = tot
            else:
                row["Total"] = ""

            warnString = ""
            if "Blank" in thisTest["sname"]:
                warnString += "[Blank ID]"
            if "No ID" in thisTest["sname"]:
                warnString += "[No ID]"
            if not thisTest["marked"]:
                warnString += "[Unmarked]"
            row["Warnings"] = warnString

            testWriter.writerow(row)


if __name__ == "__main__":
    # get commandline args if needed
    parser = argparse.ArgumentParser(
        description='Create a spreadsheet of grades named "{}".'.format(CSVFilename),
        epilog="If grading is not yet complete, the spreadsheet contains "
        "partial info and any warnings so far.",
    )
    parser.add_argument("-w", "--password", type=str)
    parser.add_argument(
        "-s",
        "--server",
        metavar="SERVER[:PORT]",
        action="store",
        help="Which server to contact.",
    )
    args = parser.parse_args()
    if args.server and ":" in args.server:
        s, p = args.server.split(":")
        msgr = FinishMessenger(s, port=p)
    else:
        msgr = FinishMessenger(args.server)
    msgr.start()

    # get the password if not specified
    if args.password is None:
        try:
            pwd = getpass.getpass("Please enter the 'manager' password:")
        except Exception as error:
            print("ERROR", error)
    else:
        pwd = args.password

    # get started
    try:
        msgr.requestAndSaveToken("manager", pwd)
    except PlomExistingLoginException:
        print(
            "You appear to be already logged in!\n\n"
            "  * Perhaps a previous session crashed?\n"
            "  * Do you have another finishing-script or manager-client running,\n"
            "    e.g., on another computer?\n\n"
            "In order to force-logout the existing authorisation run the 029_clearManagerLogin.py script."
        )
        exit(0)

    spec = msgr.getInfoGeneral()
    numberOfTests = spec["numberOfTests"]
    numberOfQuestions = spec["numberOfQuestions"]
    spreadSheetDict = msgr.RgetSpreadsheet()

    msgr.closeUser()
    msgr.stop()

    writeSpreadsheet(spreadSheetDict)