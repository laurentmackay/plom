#!/usr/bin/env -S python3 -u

# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020-2021 Forest Kobayashi
# Copyright (C) 2021-2023 Colin B. Macdonald
# Copyright (C) 2022 Nicholas J H Lai
# Copyright (C) 2023 Laurent MacKay

"""Upload reassembled Plom papers and grades to Canvas.

Overview:

  1. Finish grading
  2. Run `plom-finish csv` and `plom-finish reassemble`.
  3. Copy this script into the current directory.
  4. Run this script and follow the interactive menus:
     ```
     ./plom-push-to-canvas.py --dry-run
     ```
     It will output what would be uploaded.
  5. Note that you can provide command line arguments and/or
     set environment variables to avoid the interactive prompts:
     ```
     ./plom-push-to-canvas.py --help
     ```
  6. Run it again for real:
     ```
     ./plom-push-to-canvas.py --course xxxxxx --assignment xxxxxxx --no-section 2>&1 | tee push.log
     ```

This script traverses the files in `reassembled/` directory
and tries to upload them.  It takes the corresponding grades
from `marks.csv`.  There can be grades in `marks.csv` for which
there is no reassembled file in `reassembled/`: these are ignored.

Solutions can also be uploaded.  Again, only solutions that
correspond to an actual reassembled paper will be uploaded.

Instructors and TAs can do this but in the past it would fail for
the "TA Grader" role: https://gitlab.com/plom/plom/-/issues/2338
"""

import argparse
import os
from pathlib import Path

import string



from canvasapi import __version__ as __canvasapi_version__

from tqdm import tqdm

from plom import __version__ as __plom_version__
from plom.canvas import __DEFAULT_CANVAS_API_URL__
from plom.canvas import (
    canvas_login,
    get_assignment_by_id_number,
    assignment_submitter,
    get_course_by_id_number,
    get_section_by_id_number,
    interactively_get_assignment,
    interactively_get_course,
    interactively_get_section,
)


# bump this a bit if you change this script
__script_version__ = "0.2.3"



parser = argparse.ArgumentParser(
    description=__doc__.split("\n")[0],
    epilog="\n".join(__doc__.split("\n")[1:]),
    formatter_class=argparse.RawDescriptionHelpFormatter,
)
parser.add_argument(
    "--version",
    action="version",
    version=f"%(prog)s {__script_version__} (using Plom version {__plom_version__}, "
    f"and canvasapi package version {__canvasapi_version__})",
)
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
        You can instead set the environment variable CANVAS_API_KEY.
        If not specified by either mechanism, you will be prompted
        to enter it.
    """,
)
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Perform a dry-run without writing grades or uploading files.",
)
parser.add_argument(
    "--course",
    type=int,
    metavar="N",
    action="store",
    help="""
        Specify a Canvas course ID (an integer N).
        Interactively prompt from a list if omitted.
    """,
)
parser.add_argument(
    "--no-section",
    action="store_true",
    help="""
        Don't use section information from Canvas.
        In this case we will take the classlist directly from the
        course.
        In most cases, this is probably what you want UNLESS you have
        the same student in multiple sections (causing duplicates in
        the classlist, leading to problems).
    """,
)
parser.add_argument(
    "--section",
    type=int,
    metavar="N",
    action="store",
    help="""
        Specify a Canvas section ID (an integer N).
        If neither this nor "no-section" is specified then the script
        will interactively prompt from a list.
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
    "--solutions",
    action="store_true",
    default=True,
    help="""
        Upload individualized solutions as well as reassembled papers
        (default: on).
    """,
)
parser.add_argument(
    "--no-solutions",
    dest="solutions",
    action="store_false",
)


if __name__ == "__main__":
    args = parser.parse_args()
    if hasattr(args, "api_key"):
        args.api_key = args.api_key or os.environ.get("CANVAS_API_KEY")
        if not args.api_key:
            args.api_key = input("Please enter the API key for Canvas: ")

    user = canvas_login(args.api_url, args.api_key)

    if args.course is None:
        course = interactively_get_course(user)
        print(f'Note: you can use "--course {course.id}" to reselect.\n')
    else:
        course = get_course_by_id_number(args.course, user)
    print(f"Ok using course: {course}")

    if args.no_section:
        section = None
    elif args.section:
        section = get_section_by_id_number(course, args.section)
    else:
        section = interactively_get_section(course)
        if section is None:
            print('Note: you can use "--no-section" to omit selecting section.\n')
        else:
            print(f'Note: you can use "--section {section.id}" to reselect.\n')
    print(f"Ok using section: {section}")

    use_rubric=True

    if use_rubric:
        assignment_kw = {'include':['rubric_assessment']}
    else:
        assignment_kw = {}

    if args.assignment:
        assignment = get_assignment_by_id_number(course, args.assignment, **assignment_kw)
    else:
        assignment = interactively_get_assignment(course, **assignment_kw)
        print(f'Note: you can use "--assignment {assignment.id}" to reselect.\n')

    print(f"Ok uploading to Assignment: {assignment}")

    print("\nChecking if you have run `plom-finish`...")
    print("  --------------------------------------------------------------------")
    if not Path("marks.csv").exists():
        raise ValueError('Missing "marks.csv": run `plom-finish csv`')
    print('  Found "marks.csv" file.')
    if not Path("reassembled").exists():
        raise ValueError('Missing "reassembled/": run `plom-finish reassemble`')
    print('  Found "reassembled/" directory.')

    if args.solutions:
        soln_dir = Path("solutions")
        if not soln_dir.exists():
            raise ValueError(
                f'Missing "{soln_dir}": run `plom-finish solutions` or pass `--no-solutions` to omit'
            )
        print(f'  Found "{soln_dir}" directory.')

    print("\nFetching data from canvas now...")
    print("  --------------------------------------------------------------------")
    

    if args.dry_run:
        print("\n\nPushing grades and marked papers to Canvas [DRY-RUN]...")
    else:
        print("\n\nPushing grades and marked papers to Canvas...")
    print("  --------------------------------------------------------------------")


        
    submit = True
    if submit:
        assignment.edit(assignment={'submission_types':'online_upload'})

    
    submit = assignment_submitter(assignment, rubric_headers=['LO1 mark', 'LO2 mark'])

    timeouts = []
    for pdf in tqdm(Path("reassembled").glob("*.pdf")):
        sis_id = pdf.stem.split("_")[1]
        assert len(sis_id) == 8
        assert set(sis_id) <= set(string.digits)
        
        not_submitted = submit(sis_id, comments = pdf, dry_run = args.dry_run)

        timeouts.extend(not_submitted)

    if args.dry_run:
        print("Done with DRY-RUN.  The following data would have been uploaded:")
    else:
        print(f"Done.  There were {len(timeouts)} timeouts:")

    print("    sis_id   student name     filename/mark")
    print("    --------------------------------------------")
    for thing, sis_id, name in timeouts:
        print(f"    {sis_id} {name} \t {thing}")
    if not args.dry_run:
        print("  These should be uploaded manually, or rerun with only")
        print("  the failures placed in reassembled/")
