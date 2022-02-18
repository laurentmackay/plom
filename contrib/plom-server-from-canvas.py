#!/usr/bin/env python3

# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020-2021 Forest Kobayashi
# Copyright (C) 2021-2022 Colin B. Macdonald

"""Build and populate a Plom server from a Canvas Assignment.

The goal is automate using Plom as an alternative to Canvas's
SpeedGrader.

This is very much *pre-alpha*: not ready for production use, use at
your own risk, no warranty, etc, etc.

1. Create `api_secrets.py` containing
   ```
   my_key = "11224~AABBCCDDEEFF..."
   ```
2. Run `python plom-server-from-canvas.py`
3. Follow prompts.
4. Go the directory you created and run `plom-server launch`.

Notes:
  * If number of pages precisely matches number of questions then
    we do a 1-1 mapping onto questions.  Otherwise we push each
    page to all questions.  This could be made more configurable.

TODO:
  * needs to log instead of just discarding so much output
  * support an existing configured server in basedir: or fork
"""

import argparse
import csv
import os
from pathlib import Path
import random
import string
import subprocess
from textwrap import dedent
import time

import fitz
import PIL.Image
import requests
from tqdm import tqdm

from plom import __version__
from plom.misc_utils import working_directory
from plom.server import PlomServer
from plom.canvas import __DEFAULT_CANVAS_API_URL__
from plom.canvas import (
    canvas_login,
    download_classlist,
    get_assignment_by_id_number,
    get_conversion_table,
    get_course_by_id_number,
    get_section_by_id_number,
    interactively_get_assignment,
    interactively_get_course,
    interactively_get_section,
)
import plom.scan


def get_short_name(long_name):
    """"""
    short_name = ""
    push_letter = True
    while len(long_name):
        char, long_name = long_name[0], long_name[1:]
        if char in string.digits:
            push_letter = True
            short_name += char
        elif push_letter and char in string.ascii_letters:
            push_letter = False
            short_name += char.lower()
        elif char == " ":
            push_letter = True
        else:
            continue

    return short_name


def make_toml(assignment, marks, *, server_dir="."):
    """
    (assignment): a canvasapi assignment object
    """
    server_dir = Path(server_dir)
    longName = assignment.name

    name = get_short_name(longName)

    numberOfVersions = 1
    numberOfQuestions = len(marks)
    numberOfPages = len(marks) + 1

    numberToProduce = -1
    numberToName = -1
    # note potentially useful
    # assignment.needs_grading_count, assignment.get_gradeable_students()

    toml = dedent(
        f"""
        # autogenerated by a script to pull from Canvas to Plom
        name = "{name}"
        longName = "{longName}"
        numberOfVersions = {numberOfVersions}
        numberOfPages = {numberOfPages}
        numberToProduce = {numberToProduce}
        numberToName = {numberToName}
        numberOfQuestions = {numberOfQuestions}
        idPage = 1
        """
    ).lstrip()
    for i, mark in enumerate(marks):
        toml += dedent(
            f"""
            [question.{i + 1}]
            pages = [{i + 2}]
            mark = {mark}
            select = "fix"
            """
        ).lstrip()
    with open(server_dir / "canvasSpec.toml", "w") as f:
        f.write(toml)


def initialize(course, section, assignment, marks, *, server_dir="."):
    """
    Set up the test directory, get the classlist from canvas, make the
    .toml, etc
    """
    server_dir = Path(server_dir)
    server_dir.mkdir(exist_ok=True)

    print("\nGetting enrollment data from canvas and building `classlist.csv`...")
    download_classlist(course, section=section, server_dir=server_dir)

    print("Generating `canvasSpec.toml`...")
    make_toml(assignment, marks, server_dir=server_dir)

    with working_directory(server_dir):
        print("\nSwitched into test server directory.\n")
        print("Parsing `canvasSpec.toml`...")
        # TODO: we should replace all these with functions not cmdline?
        # TODO: capture and log all this output with capture_output=True?
        subprocess.check_call(["plom-create", "parse", "canvasSpec.toml"])
        print("Running `plom-server init`...")
        subprocess.check_call(["plom-server", "init"])
        print("Autogenerating users...")
        subprocess.check_call(["plom-server", "users", "--auto", "12", "--numbered"])
        print("Processing userlist...")
        subprocess.check_call(["plom-server", "users", "userListRaw.csv"])

    print("Temporarily exporting manager password...")
    pwds = {}
    with open(server_dir / "userListRaw.csv", "r") as csvfile:
        for row in csv.reader(csvfile):
            pwds[row[0]] = row[1]
    os.environ["PLOM_MANAGER_PASSWORD"] = pwds["manager"]
    del pwds

    print("Launching plom server.")
    plom_server = PlomServer(basedir=server_dir)
    # TODO: consider suppressing output https://gitlab.com/plom/plom/-/issues/1586
    # Forest had popen(... ,stdout=subprocess.DEVNULL)
    print("Server *should* be running now")

    # TODO: these had capture_output=True but this hides errors
    print("Building classlist...")
    build_class = subprocess.check_call(
        ["plom-create", "class", server_dir / "classlist.csv"]
    )
    print("Building the database...")
    with working_directory(server_dir):
        build_class = subprocess.check_call(["plom-create", "make", "--no-pdf"])

    return plom_server


def get_submissions(
    assignment, server_dir=".", name_by_info=True, dry_run=False, replace_existing=False
):
    """
    get the submission pdfs out of Canvas

    (name_by_info): Whether to make the filenames of the form ID_Last_First.pdf

    """
    server_dir = Path(server_dir)

    if name_by_info:
        print("Fetching conversion table...")
        conversion = get_conversion_table(server_dir=server_dir)

    tmp_downloads = server_dir / "upload" / "tmp_downloads"
    for_plom = server_dir / "upload" / "submittedHWByQ"

    tmp_downloads.mkdir(exist_ok=True, parents=True)
    for_plom.mkdir(exist_ok=True, parents=True)

    print("Fetching & preprocessing submissions...")
    subs = assignment.get_submissions()

    unsubmitted = []
    timeouts = []
    errors = []
    for sub in tqdm(subs):
        # Try to avoid overheating the canvas api (this is soooooo dumb lol)
        time.sleep(random.uniform(0.5, 1.0))
        if name_by_info:
            canvas_id = sub.user_id
            stud_name, stud_sis_id = conversion[str(canvas_id)]
            last_name, first_name = [name.strip() for name in stud_name.split(",")]
            sub_name = f"{last_name}_{first_name}.{stud_sis_id}._".replace(" ", "_")
        else:
            sub_name = f"{sub.user_id}"

        if (not replace_existing) and (for_plom / f"{sub_name}.pdf").exists():
            print(f"Skipping submission {sub_name} --- exists already")
            continue

        attachments = getattr(sub, "attachments", [])
        if not attachments:
            unsubmitted.append(sub)

        # Loop over all the attachments, save to disc, do some stitching
        # TODO: useful later to keep the student's original filename somewhere?
        attachment_filenames = []
        for i, obj in enumerate(attachments):
            assert type(obj) == dict, "Perhaps attachments are not always dicts?"
            assert "content-type" in obj.keys()
            assert "url" in obj.keys()
            assert obj["upload_status"] == "success"  # TODO, or just "continue"
            if obj["content-type"] == "null":
                # TODO: in what cases does this occur?
                continue
            elif obj["content-type"] == "application/pdf":
                suffix = "pdf"
            elif obj["content-type"] == "image/png":
                suffix = ".png"
            elif obj["content-type"] == "image/jpg":
                suffix = ".jpg"
            elif obj["content-type"] == "image/jpeg":
                suffix = ".jpeg"
            else:
                print(
                    f"unexpected content-type {obj['content-type']}: for now, appending to error list"
                )
                errors.append(sub)
            filename = tmp_downloads / f"{i:02}-{sub_name}.{suffix}"

            if dry_run:
                print(f"dry-run, but would download {filename.name}")
                filename.touch()
                continue

            time.sleep(random.uniform(0.5, 1.5))
            # TODO: try catch to a timeout/failed list?
            r = requests.get(obj["url"])
            with open(filename, "wb") as f:
                f.write(r.content)

            if suffix != "pdf":
                # TODO: fitz can do this too
                img = PIL.Image.open(filename)
                img = img.convert("RGB")
                filename = filename.with_suffix(".pdf")
                img.save(filename)

            attachment_filenames.append(filename)

        final_name = for_plom / f"{sub_name}.pdf"
        if len(attachment_filenames) == 0:
            # TODO: what is this case, can it happen?
            pass
        elif len(attachment_filenames) == 1:
            attachment_filenames[0].rename(final_name)
        else:
            # TODO: stitching not ideal: prefer bundles from original files
            doc = fitz.Document()
            for f in attachment_filenames:
                try:
                    doc.insert_pdf(fitz.open(f))
                except RuntimeError:
                    print(f"We had problems with {sub} because of error on {f}")
                    errors.append(sub)
            # TODO: this could easily fail if we failed to the insertions above
            # TODO: anyway, like I said above, stitching not ideal
            doc.save(final_name)
            # Clean up temporary files (TODO: for now we leave them)
            # for x in attachment_filenames:
            #    x.unlink()

    for sub in unsubmitted:
        print(f"No submission from user_id {sub.user_id}")
    for sub in errors:
        print(f"Error processing from user_id {sub.user_id}")


def scan_submissions(num_questions, *, server_dir="."):
    """
    Apply `plom-scan` to all the pdfs we've just pulled from canvas
    """
    server_dir = Path(server_dir)

    pwds = {}
    with open(server_dir / "userListRaw.csv", "r") as csvfile:
        for row in csv.reader(csvfile):
            pwds[row[0]] = row[1]
    scan_pwd = pwds["scanner"]
    del pwds

    upload_dir = server_dir / "upload"

    print("Applying `plom-hwscan` to pdfs...")
    for pdf in tqdm((upload_dir / "submittedHWByQ").glob("*.pdf")):
        # get 12345678 from blah_blah.blah_blah.12345678._.
        sid = pdf.stem.split(".")[-2]
        assert len(sid) == 8
        if len(fitz.open(pdf)) == num_questions:
            # If number of pages precisely matches number of questions then
            # do a 1-1 mapping...
            q = [[x] for x in range(1, num_questions + 1)]
        else:
            # ... otherwise push each page to all questionsa.
            q = [x for x in range(1, num_questions + 1)]
        # TODO: capture output and put it all in a log file?  (capture_output=True?)
        plom.scan.processHWScans(
            pdf, sid, q, basedir=upload_dir, msgr=("localhost", scan_pwd)
        )

    # Clean up any missing submissions
    plom.scan.processMissing(msgr=("localhost", scan_pwd), yes_flag=True)


parser = argparse.ArgumentParser(
    description=__doc__.split("\n")[0],
    epilog="\n".join(__doc__.split("\n")[1:]),
    formatter_class=argparse.RawDescriptionHelpFormatter,
)
parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
parser.add_argument(
    "--api_url",
    type=str,
    default=__DEFAULT_CANVAS_API_URL__,
    action="store",
    help=f'URL for talking to Canvas, defaults to "{__DEFAULT_CANVAS_API_URL__}".',
)
parser.add_argument(
    "--api_key",
    type=str,
    action="store",
    help="""
        The API Key for talking to Canvas.
        You can store this in a local file "api_secrets.py" as
        a string in a variable named "my_key".
        TODO: If blank, prompt for it?
    """,
)
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Perform a dry-run, for example, don't download papers",
)
parser.add_argument(
    "--dir",
    type=str,
    action="store",
    help="The local directory for the Plom Server files (prompts if omitted).",
)
parser.add_argument(
    "--course",
    type=int,
    metavar="N",
    action="store",
    help="""
        Specify a Canvas Course ID (an integer N).
        Interactively prompt from a list if omitted.
    """,
)
parser.add_argument(
    "--section",
    type=int,
    metavar="N",
    action="store",
    help="""
        Specify a Canvas Section ID (an integer N).
        Interactively prompt from a list if omitted.
    """,
)
parser.add_argument(
    "--no-section",
    action="store_false",
    help="""
        Overwrites the --section flag to not use sections.
    """,
)
parser.add_argument(
    "--assignment",
    type=int,
    metavar="M",
    action="store",
    help="""
        Specify a Canvas Assignment ID (an integer M).
        Interactively prompt from a list if omitted.
    """,
)
parser.add_argument(
    "--marks",
    type=str,
    metavar="LIST",
    action="store",
    help="""
        A comma-separated list of integers specifying the marks for
        each question.  This also specifies the number of questions.
        For example "5,10,4" means we have three questions worth 5,
        10 and 4 respectively.  If you use spaces after the commas,
        you'll need quotes around the list, as in `--marks "5, 10, 4"`.
    """,
)

if __name__ == "__main__":
    args = parser.parse_args()
    user = canvas_login(args.api_url, args.api_key)

    if args.course is None:
        course = interactively_get_course(user)
        print(f'Note: you can use "--course {course.id}" to reselect.\n')
    else:
        course = get_course_by_id_number(args.course, user)
    print(f"Ok using course: {course}")

    section = None
    if not args.no_section:
        if args.section is None:
            section = get_section_by_id_number(course, args.section)
        else:
            section = interactively_get_section(course)
            if section is None:
                print('Note: you can use "--no-section" to omit selecting section.\n')
            else:
                print(f'Note: you can use "--section {section.id}" to reselect.\n')
        print(f"Ok using section: {section}")

    if args.assignment:
        assignment = get_assignment_by_id_number(course, args.assignment)
    else:
        assignment = interactively_get_assignment(course)
        print(f'Note: you can use "--assignment {assignment.id}" to reselect.\n')
    print(f"Ok downloading from Assignment: {assignment}")

    o_dir = os.getcwd()

    if args.dir is None:
        basedir = input("Name of dir to use for this assignment: ")
    else:
        basedir = args.dir
    basedir = Path(basedir)

    if basedir.is_dir():
        print(f'Using existing dir "{basedir}"')
        # TODO: ensure empty or warn if somethings exist?
    else:
        print(f'Creating dir "{basedir}"')
        basedir.mkdir(exist_ok=True)

    pp = assignment.points_possible
    print(f'\n"{assignment}" has "{pp}" points possible')
    if pp == 0 or int(pp) != pp:
        raise ValueError(
            "Points possible must be non-zero int: Plom supports only integer marking"
        )
    if args.marks is None:
        print(f"Do you want to split this total of {pp} over multiple questions?")
        args.marks = input('Enter a list for the marks per question, e.g., "5,10,3": ')
    args.marks = [int(x) for x in args.marks.split(",")]
    symsum = " + ".join(str(x) for x in args.marks)
    if sum(args.marks) != pp:
        raise ValueError(f"Total marks do not match Canvas: {symsum} =/= {pp}")
    print(f"Ok, using {len(args.marks)} questions with breakdown {symsum} = {pp}")
    del pp

    plom_server = initialize(
        course, section, assignment, args.marks, server_dir=basedir
    )

    print("\n\ngetting submissions from canvas...")
    get_submissions(assignment, dry_run=args.dry_run, server_dir=basedir)

    print("scanning submissions...")
    scan_submissions(len(args.marks), server_dir=basedir)

    input("Press enter when you want to stop the server...")
    plom_server.stop()
    print("Server stopped, goodbye!")
