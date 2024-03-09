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
from typing import Iterable

from canvasapi import __version__ as __canvasapi_version__

from tqdm import tqdm
import random
import string
import time

from plom import __version__ as __plom_version__
from plom.canvas import __DEFAULT_CANVAS_API_URL__
from plom.canvas import (
    canvas_login,
    get_assignment_by_id_number,
    get_course_by_id_number,
    get_section_by_id_number,
    interactively_get_assignment,
    interactively_get_course,
    interactively_get_section,
    get_sis_id_to_canvas_id_table,
    get_student_list,
    download_classlist,
    sis_id_to_student_dict,
    get_sis_id_to_marks,
    get_sis_id_to_sub_and_name_table
)

from canvasapi.exceptions import CanvasException

# bump this a bit if you change this script
__script_version__ = "0.2.4"

headers = ['LO{i+1} mark' for i in range(16)]


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


def assignment_submitter(assignment, section=None, rubric_headers=None, 
                         reassembled_dir = 'reassembled', push_subdir = 'pushed_to_canvas', 
                         move_files_after_submission=True, overwrite=False):

    user = canvas_login(assignment._requester.original_url, assignment._requester.access_token )

    course = get_course_by_id_number(assignment.course_id, user)

    if section:
        print("  Getting student list from Section...")
        student_list = get_student_list(section)
    else:
        print("  Getting student list from Course...")
        student_list = get_student_list(course)

    print("    done.")

    print("  Getting canvasapi submission objects...")
    subs = assignment.get_submissions()
    print("    done.")

    print("  Getting another classlist and various conversion tables...")
    download_classlist(course)
    print("    done.")

    # Most of these conversion tables are fully irrelevant once we
    # test this code enough to be confident we can remove the
    # assertions down below
    print("  Constructing SIS_ID to student conversion table...")
    sis_id_to_students = sis_id_to_student_dict(student_list)
    print("    done.")

    print("  Constructing SIS_ID to canvasapi submission conversion table...")
    sis_id_to_sub_and_name = get_sis_id_to_sub_and_name_table(subs)
    print("    done.")

    print("  Constructing SIS_ID to canvasapi submission conversion table...")
    # We only need this second one for double-checking everything is
    # in order
    sis_id_to_canvas = get_sis_id_to_canvas_id_table()
    print("    done.")

    print("  Finally, getting SIS_ID to marks conversion table.")
    sis_id_to_marks = get_sis_id_to_marks()
    print("    done.")


    if rubric_headers:
        assignment.edit(assignment={'use_rubric_for_grading':True, 'published':True})
        rubric_ids = [ item['id']  for item in assignment.rubric]
        rating_ids = [{ rating['points']:rating['id']  for rating in item['ratings'] } for item in assignment.rubric]
        rating_descs = [{ rating['points']:rating['description']  for rating in item['ratings'] } for item in assignment.rubric]
        sis_id_to_rubric_marks = get_sis_id_to_marks(headers=rubric_headers)

    if move_files_after_submission:
        os.makedirs(os.path.join(reassembled_dir, push_subdir), exist_ok=True)

    def wait():
        time.sleep(random.uniform(0.25, 0.5))

    def push_to_canvas(sis_id, comments=None, submission_files=None, dry_run=False):
        ##TODO: move files after upload
        not_pushed = []

        try:
            sub, name = sis_id_to_sub_and_name[sis_id]
            new_sub=sub
            if not overwrite and not sub.missing:
                return [(m, sis_id, name) for m in not_pushed]
            student = sis_id_to_students[sis_id]

        except KeyError:
            print(f"No student # {sis_id} : {name} in Canvas!")
            print("  Hopefully this is 1-1 w/ a prev canvas id error")
            print("  SKIPPING this submission and continuing")
            return 
        
        try:
            total_mark = sis_id_to_marks[sis_id]
            if rubric_headers:
                rubric_marks = sis_id_to_rubric_marks[sis_id]

        except KeyError: 
            return #no grade, no problem

        assert sub.user_id == student.user_id
        if move_files_after_submission:
            files_to_move = set()
        # TODO: should look at the return values
        # TODO: back off on canvasapi.exception.RateLimitExceeded?
        if comments:
            comments = comments if isinstance(comments, Iterable) else [comments]
            for c in comments:
                if dry_run:
                    not_pushed.append(c.name)
                else:
                    try:
                        sub.upload_comment(c)
                        if move_files_after_submission: #TODO: think about handling mulitple files properly, more important for the submission file...
                            files_to_move.add(c)
                    except CanvasException as e:
                        print(e)
                        not_pushed.append(c.name)

                    wait()

        if submission_files:
            submission_files = submission_files if isinstance(submission_files, Iterable) else [submission_files]
            # ids = []
            # for f in submission_files:
            #     if dry_run:
            #         not_pushed.append(f.name)
            #     else:
            #         try:
            #             up = assignment.upload_to_submission(f, user=sub.user_id)
            #             ids.append(up[1]['id'])
                        # if move_files_after_submission:
                        #     files_to_move |= c
            #         except CanvasException as e:
            #             print(e)
            #             not_pushed.append(f.name)

            #         wait()

            # new_sub = sub.edit(submission={'submission_type':'online_upload', 'file_ids':ids})        


        
        if dry_run:
            not_pushed.append(total_mark)
            if rubric_headers:
                for i, (rating_desc, mark) in enumerate(zip(rating_descs, rubric_marks)):
                        not_pushed.append(f'rubric item {i+1}: {rating_desc[float(mark)]}')
        else:
            sub_data = {'submission':{"posted_grade": total_mark},'user':user} #i think `user` is redundant here, there was a confounding factor during testing

            if rubric_headers:
                rubric_assessment = {rubric_id:{'rating_id': rating_id[float(mark)], 'points': mark} for rubric_id, rating_id, mark in zip(rubric_ids, rating_ids, rubric_marks)}
                sub_data['rubric_assessment'] = rubric_assessment
            try:
                new_sub = sub.edit(**sub_data)
                wait()
                
                if move_files_after_submission:
                    for f in files_to_move:
                        if f and os.path.exists(f):
                            os.rename(f, os.path.join(f.parent, push_subdir, f.name) )

            except CanvasException as e:
                print(e)
                not_pushed.append(total_mark)



        sis_id_to_sub_and_name[sis_id]=(new_sub, name)
        
        return [(m, sis_id, name) for m in not_pushed]
    
    return push_to_canvas 


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

    
    submit = assignment_submitter(assignment, rubric_headers=headers)

    timeouts = []
    upload_comment = True
    for pdf in tqdm(Path("reassembled").glob("*.pdf")):

        sis_id = pdf.stem.split("_")[1]

        assert len(sis_id) == 8
        assert set(sis_id) <= set(string.digits)

        comment = pdf if upload_comment else None
        msg = submit(sis_id, comments = comment, dry_run = args.dry_run)

        if msg:
            timeouts.extend(msg)

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
