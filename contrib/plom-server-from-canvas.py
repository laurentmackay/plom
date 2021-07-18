#!/usr/bin/env python3

# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020-2021 Forest Kobayashi
# Copyright (C) 2021 Colin B. Macdonald

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
   You will need the `aria2c` command-line downloader in addition
   to the usual Plom dependencies.
3. Follow prompts.
4. Go the directory you created and run `plom-server launch`.
"""

import csv
import string
import subprocess
import os
import random
import time

import fitz
import PIL
from tqdm import tqdm

from canvas_utils import (
    canvas_login,
    download_classlist,
    get_conversion_table,
    interactively_get_assignment,
    interactively_get_course,
)


# TODO: Invesitate using [1] here, and can any of this help [1]?
# [1] https://gitlab.com/plom/plom/-/merge_requests/662
# For making sure the server dies with the python script if we kill
# the python script.
#
# LINUX ONLY I think. See https://stackoverflow.com/a/19448096
import signal
import ctypes

libc = ctypes.CDLL("libc.so.6")


def _set_pdeathsig(sig=signal.SIGTERM):
    """
    For killing subprocess.Popen() things when python dies

    See https://stackoverflow.com/a/19448096
    """

    def callable():
        return libc.prctl(1, sig)

    return callable


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


def get_toml(assignment, server_dir="."):
    """
    (assignment): a canvasapi assignment object
    """
    longName = assignment.name

    name = get_short_name(longName)

    numberOfVersions = 1  # TODO: Make this not hardcoded
    numberOfPages = 20  # TODO: Make this not hardcoded

    numberToProduce = -1
    numberToName = -1
    # note potentially useful
    # assignment.needs_grading_count, assignment.get_gradeable_students()

    # What a beautiful wall of +='s
    toml = ""
    toml += f'name="{name}"\n'
    toml += f'longName="{longName}"\n'
    toml += f"numberOfVersions={numberOfVersions}\n"
    toml += f"numberOfPages={numberOfPages}\n"
    toml += f"numberToProduce={numberToProduce}\n"
    toml += f"numberToName={numberToName}\n"
    toml += "numberOfQuestions=1\n"
    toml += "[idPages]\npages=[1]\n"
    toml += "[doNotMark]\npages=[2]\n"
    toml += f"[question.1]\npages={list(range(3,numberOfPages+1))}\n"
    toml += (
        f"mark={int(assignment.points_possible) if assignment.points_possible else 1}\n"
    )
    if assignment.points_possible - int(assignment.points_possible) != 0:
        assert False  # OK this error needs to be handled more
        # intelligently in the future
    toml += 'select="fix"'

    with open(f"{server_dir}/canvasSpec.toml", "w") as f:
        f.write(toml)


def initialize(course, assignment, server_dir="."):
    """
    Set up the test directory, get the classlist from canvas, make the
    .toml, etc
    """
    if not os.path.exists(server_dir):
        os.mkdir(server_dir)

    o_dir = os.getcwd()  # original directory

    print("\n\nGetting enrollment data from canvas and building `classlist.csv`...")
    download_classlist(course, server_dir=server_dir)

    print("Generating `canvasSpec.toml`...")
    get_toml(assignment, server_dir=server_dir)

    os.chdir(server_dir)
    print("\nSwitched into test server directory.\n")

    print("Parsing `canvasSpec.toml`...")
    subprocess.run(["plom-build", "parse", "canvasSpec.toml"], capture_output=True)

    print("Running `plom-server init`...")
    subprocess.run(["plom-server", "init"], capture_output=True)

    print("Autogenerating users...")
    subprocess.run(["plom-server", "users", "--auto", "1"], capture_output=True)

    print("Temporarily exporting manager password...")
    user_list = []
    with open("userListRaw.csv", "r") as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            user_list += [row]

    os.environ["PLOM_MANAGER_PASSWORD"] = user_list[1][1]

    del user_list

    print("Processing userlist...")
    subprocess.run(
        ["plom-server", "users", "userListRaw.csv"],
        capture_output=True,
    )

    print("Launching plom server.")
    # plom_server = subprocess.Popen(["plom-server", "launch"], stdout=subprocess.DEVNULL)
    plom_server = subprocess.Popen(
        ["plom-server", "launch"],
        stdout=subprocess.DEVNULL,
        preexec_fn=_set_pdeathsig(signal.SIGTERM),  # Linux only?
    )

    print(
        "Server *should* be running now (although hopefully you can't because theoretically output should be suppressed). In light of this, be extra sure to explicitly kill the server (e.g., `pkill plom-server`) before trying to start a new one --- it can persist even after the original python process has been killed.\n\nTo verify if the server is running, you can try the command\n  ss -lntu\nto check if the 41984 port has a listener.\n"
    )

    subprocess.run(["sleep", "3"])

    print("Building classlist...")
    build_class = subprocess.run(
        ["plom-build", "class", "classlist.csv"], capture_output=True
    )

    print("Building the database...")
    build_class = subprocess.run(
        ["plom-build", "make", "--no-pdf"], capture_output=True
    )

    os.chdir(o_dir)

    return plom_server


def get_submissions(
    assignment, server_dir=".", name_by_info=True, dry_run=False, replace_existing=False
):
    """
    get the submission pdfs out of Canvas

    (name_by_info): Whether to make the filenames of the form ID_Last_First.pdf

    """
    o_dir = os.getcwd()

    if name_by_info:
        print("Fetching conversion table...")
        conversion = get_conversion_table(server_dir=server_dir)

    os.chdir(server_dir)

    if not os.path.exists("upload"):
        os.mkdir("upload")

    os.chdir("upload")

    if not os.path.exists("submittedHWByQ"):
        os.mkdir("submittedHWByQ")

    os.chdir("submittedHWByQ")

    print("Moved into ./upload/submittedHWByQ")

    print("Fetching & preprocessing submissions...")
    subs = list(assignment.get_submissions())

    # TODO: Parallelize requests
    unsubmitted = []
    timeouts = []
    for sub in tqdm(subs):
        # Try to avoid overheating the canvas api (this is soooooo dumb lol)
        time.sleep(random.random())
        # TODO: is `aria2c` actually faster here lol??
        # time.sleep(random.uniform(0.5, 1.5))
        if name_by_info:
            canvas_id = sub.user_id
            stud_name, stud_sis_id = conversion[str(canvas_id)]
            last_name, first_name = [name.strip() for name in stud_name.split(",")]
            sub_name = f"{last_name}_{first_name}.{stud_sis_id}._.pdf".replace(" ", "_")
        else:
            sub_name = f"{sub.user_id}.pdf"

        if (not replace_existing) and (os.path.exists(sub_name)):
            # print(f"Skipping submission {sub_name} --- exists already")
            continue

        try:
            # If the student submitted multiple times, get _all_
            # the submissions.
            version = 0
            sub_subs = []
            for obj in sub.attachments:
                # sub-submission name --- prepend with a version
                # number to make stitching them together easier
                if type(obj) == dict:
                    # TODO: Test which of these cases are actually
                    # relevant
                    suffix = None
                    if obj["content-type"] == "null":
                        continue
                    elif obj["content-type"] == "application/pdf":
                        sub_sub_name = f"{version:02}-{sub_name}"
                    elif obj["content-type"] == "image/png":
                        suffix = ".png"
                        sub_sub_name = f"{version:02}-{sub_name}"[:-4] + suffix
                    elif obj["content-type"] == "image/jpg":
                        suffix = ".jpg"
                        sub_sub_name = f"{version:02}-{sub_name}"[:-4] + suffix
                    elif obj["content-type"] == "image/jpeg":
                        suffix = ".jpeg"
                        sub_sub_name = f"{version:02}-{sub_name}"[:-4] + suffix

                    version += 1

                    sub_url = obj["url"]
                    if not dry_run:
                        time.sleep(random.uniform(2.5, 6.5))
                        subprocess.run(
                            ["aria2c", sub_url, "-o", sub_sub_name, "-t", "240"],
                            capture_output=True,
                        )
                    else:
                        subprocess.run(
                            ["touch", sub_sub_name],
                            capture_output=True,
                        )

                    # subprocess.run(
                    #     ["curl", "-L", sub_url, "--output", sub_sub_name],
                    #     capture_output=True,
                    # )

                    if suffix is not None:
                        pdfname = f"{sub_sub_name}"[: -len(suffix)] + ".pdf"
                        if not dry_run:
                            img = PIL.Image.open(sub_sub_name)
                            img = img.convert("RGB")
                            img.save(pdfname)
                            sub_sub_name = pdfname
                        else:
                            subprocess.run(["touch", pdfname])

                    sub_subs += [sub_sub_name]

            if sub_subs and not dry_run:
                # Stitch together
                doc = fitz.Document()
                for sub_sub in sub_subs:
                    try:
                        to_insert = fitz.open(sub_sub)
                        doc.insert_pdf(to_insert)
                    except RuntimeError:
                        print(f"Could not find {sub_sub}.")
                        print(f"Current directory: {os.getcwd()}")
                        print(f"Contents:", os.listdir())

                doc.save(sub_name)
                # Clean up temporary files
                for sub_sub in sub_subs:
                    subprocess.run(["rm", sub_sub])
        except AttributeError:  # Catches if student didn't submit
            unsubmitted += [sub]
            continue

    for sub in unsubmitted:
        print(f"No submission from user_id {sub.user_id}")

    os.chdir(o_dir)


def scan_submissions(server_dir="."):
    """
    Apply `plom-scan` to all the pdfs we've just pulled from canvas
    """
    o_dir = os.getcwd()
    os.chdir(server_dir)

    user_list = []
    with open("userListRaw.csv", "r") as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            user_list += [row]

    os.environ["PLOM_SCAN_PASSWORD"] = user_list[2][1]

    os.chdir("upload")

    print("Temporarily exporting scanner password...")

    # TODO: Parallelize here
    print("Applying `plom-hwscan` to pdfs...")
    pdfs = [f for f in os.listdir("submittedHWByQ") if ".pdf" == f[-4:]]
    for pdf in tqdm(pdfs):
        stud_id = pdf.split(".")[1]
        assert len(stud_id) == 8
        subprocess.run(
            ["plom-hwscan", "process", "submittedHWByQ/" + pdf, stud_id, "-q", "1"],
            capture_output=True,
        )

    # Clean up any missing submissions
    subprocess.run(
        ["plom-hwscan", "missing"],
        capture_output=True,
    )

    os.chdir(o_dir)


if __name__ == "__main__":

    o_dir = os.getcwd()

    # Hang on, why do I switch the loop variable to true instead of
    # just doing the sensible thing and breaking?
    user = canvas_login()

    # TODO: copy commandline arg stuff from push_to_canvas
    course = interactively_get_course(user)
    assignment = interactively_get_assignment(user, course)

    # TODO: Make this give an `os.listdir()`
    print("Setting up the workspace now.\n")
    print("  Current subdirectories:")
    print("  --------------------------------------------------------------------")
    excluded_dirs = ["__pycache__"]
    subdirs = [
        subdir
        for subdir in os.listdir()
        if os.path.isdir(subdir) and subdir not in excluded_dirs
    ]
    for subdir in subdirs:
        print(f"    ./{subdir}")

    classdir_selected = False
    while not classdir_selected:

        classdir_name = input(
            "\n  Name of dir to use for this class (will create if not found): "
        )

        if not classdir_name:
            print("    Please provide a non-empty name.\n")
            continue

        print(f"  You selected `{classdir_name}`")
        confirmation = input("  Confirm choice? [y/n] ")
        if confirmation in ["", "\n", "y", "Y"]:
            classdir_selected = True
            classdir = classdir_name

    print(f"\n  cding into {classdir}...")
    if os.path.exists(classdir_name):
        os.chdir(classdir)
    else:
        os.mkdir(classdir)
        os.chdir(classdir)

    print(f"  working directory is now `{os.getcwd()}`")

    print("\n\n\n")

    print("  Current subdirectories:")
    print("  --------------------------------------------------------------------")
    subdirs = [
        subdir
        for subdir in os.listdir()
        if os.path.isdir(subdir) and subdir not in excluded_dirs
    ]
    # subdirs = [_ for _ in os.listdir if os.path.isdir(_)]
    for subdir in subdirs:
        print(f"    ./{subdir}")

    # Directory for this particular assignment
    hwdir_selected = False
    while not hwdir_selected:

        hwdir_name = input(
            "\n\n\n  Name of dir to use for this assignment (will create if not found): "
        )

        print(f"  You selected `{hwdir_name}`")
        confirmation = input("  Confirm choice? [y/n] ")
        if confirmation in ["", "\n", "y", "Y"]:
            hwdir_selected = True
            hwdir = hwdir_name

    print(f"\n  cding into {hwdir}...")
    if os.path.exists(hwdir_name):
        os.chdir(hwdir)
    else:
        os.mkdir(hwdir)
        os.chdir(hwdir)

    print(f"  working directory is now `{os.getcwd()}`")

    plom_server = initialize(course, assignment)

    print("\n\ngetting submissions from canvas...")
    get_submissions(assignment, dry_run=False)

    print("scanning submissions...")
    scan_submissions()

    # Return to starting directory
    os.chdir(o_dir)