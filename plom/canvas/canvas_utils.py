# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020-2021 Forest Kobayashi
# Copyright (C) 2021-2023 Colin B. Macdonald
# Copyright (C) 2023 Laurent MacKay
"""Misc utils for interacting with Canvas."""

import csv
from pathlib import Path
import random
import string
import time
from warnings import warn
from collections.abc import Iterable


from canvasapi import Canvas
from canvasapi.exceptions import CanvasException
import pandas

from plom.canvas import __DEFAULT_CANVAS_API_URL__


def get_student_list(course_or_section):
    """Get the list of students in a Course or a Section.

    Args:
        course (canvasapi.course.Course/canvasapi.section.Section):

    Returns:
        list: of `canvasapi.student.Student`.
    """
    students = []
    for enrollee in course_or_section.get_enrollments():
        # TODO: See if we also need to check for active enrollment
        if enrollee.role == "StudentEnrollment":
            students += [enrollee]
    return students


def download_classlist(course, *, section=None, server_dir="."):
    """Download .csv of the classlist and various conversion tables.

    Args:
        course (canvasapi.course.Course): we will query for enrollment.

    Keyword Args:
        server_dir (str/pathlib.Path): where to save the file.  Defaults
            to current working directory.
        section (None/canvasapi.section.Section): Which section should
            we take enrollment from?  If None (default), take all
            students directly from `course`.  Note at least in some cases
            omitting `section` can lead to duplicate students.

    Returns:
        None: But saves files into ``server_dir``.

    TODO: spreadsheet with entries of the form (student ID, student name)
    TODO: so is it the plom classlist or something else?

    TODO: this code is filled with comments/TODOs about collisions...

    Missing information doesn't reaaaaaaaaally matter to us so we'll
    just fill it in as needed.  That is a questionable statement; this
    function needs a serious review.
    """
    server_dir = Path(server_dir)
    if section:
        enrollments_raw = section.get_enrollments()
    else:
        enrollments_raw = course.get_enrollments()
    students = [_ for _ in enrollments_raw if _.role == "StudentEnrollment"]

    # FIXME: This should probably contain checks to make sure we get
    # no collisions.
    default_id = 0  # ? not sure how many digits this can be. I've seen 5-7
    default_sis_id = 0  # 8-digit number
    default_sis_login_id = 0  # 12-char jumble of letters and digits

    classlist = [
        ("Student", "ID", "SIS User ID", "SIS Login ID", "Section", "Student Number")
    ]

    conversion = [("Internal Canvas ID", "Student", "SIS User ID")]

    secnames = {}

    for stud in students:
        stud_name, stud_id, stud_sis_id, stud_sis_login_id = (
            stud.user["sortable_name"],
            stud.id,
            stud.sis_user_id,
            stud.user["integration_id"],
        )

        internal_canvas_id = stud.user_id

        # In order to make defaults work, we have to construct the
        # list here in pieces, which is really inelegant and gross.

        # Can't do this with a for loop, sadly, because pass by
        # reference makes it hard to modify the default values.
        #
        # I say "can't" when really I mean "didn't"

        # FIXME: Treat collisions

        if (
            not stud_id
            or stud_id is None
            or (isinstance(stud_id, str) and stud_id in string.whitespace)
        ):
            stud_id = str(default_id)
            # 5-7 characters is what I've seen, so let's just go with 7
            stud_id = (7 - len(stud_id)) * "0" + stud_id
            default_id += 1

        if (
            not stud_sis_id
            or stud_sis_id is None
            or (isinstance(stud_sis_id, str) and stud_sis_id in string.whitespace)
        ):
            stud_sis_id = str(default_sis_id)
            # 8 characters is necessary for UBC ID
            stud_sis_id = (8 - len(stud_sis_id)) * "0" + stud_sis_id
            default_sis_id += 1

        if (
            not stud_sis_login_id
            or stud_sis_login_id is None
            or (
                isinstance(stud_sis_login_id, str)
                and stud_sis_login_id in string.whitespace
            )
        ):
            stud_sis_login_id = str(default_sis_login_id)
            stud_sis_login_id = (12 - len(stud_sis_login_id)) * "0" + stud_sis_login_id
            default_sis_login_id += 1

        # TODO: presumably this is just `section` when that is non-None?
        section_id = stud.course_section_id
        if not secnames.get(section_id):
            # caching section names
            sec = course.get_section(section_id)
            secnames[section_id] = sec.name

        # Add this information to the table we'll write out to the CSV
        classlist += [
            (
                stud_name,
                stud_id,
                stud_sis_id,
                stud_sis_login_id,
                secnames[section_id],
                stud_sis_id,
            )
        ]

        conversion += [(internal_canvas_id, stud_name, stud_sis_id)]

    with open(server_dir / "classlist.csv", "w", newline="\n") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(classlist)

    with open(server_dir / "conversion.csv", "w", newline="\n") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(conversion)


def get_conversion_table(server_dir="."):
    """A mapping Canvas ID to Name and SIS ID."""
    server_dir = Path(server_dir)
    conversion = {}
    with open(server_dir / "conversion.csv", "r") as csvfile:
        reader = csv.reader(csvfile, delimiter=",", quotechar='"')
        for i, row in enumerate(reader):
            if i == 0:
                continue
            else:
                conversion[row[0]] = row[1:]
    return conversion


def get_sis_id_to_canvas_id_table(server_dir="."):
    server_dir = Path(server_dir)
    sis_id_to_canvas = {}
    with open(server_dir / "classlist.csv", "r") as csvfile:
        reader = csv.reader(csvfile, delimiter=",", quotechar='"')
        for i, row in enumerate(reader):
            if i == 0:
                continue
            else:
                sis_id_to_canvas[row[-1]] = row[1]
    return sis_id_to_canvas


def get_courses_teaching(user):
    """Get a list of the courses a particular user is teaching.

    args:
        user (canvasapi.current_user.CurrentUser)

    return:
        list: List of `canvasapi.course.Course` objects.
    """
    courses_teaching = []
    for course in user.get_courses():
        try:
            for enrollee in course.enrollments:
                if enrollee["user_id"] == user.id:
                    if enrollee["type"] in ["teacher", "ta"]:
                        courses_teaching += [course]
                    else:
                        continue

        except AttributeError:
            # OK for some reason a requester object is being included
            # as a course??????
            #
            # TODO: INvestigate further?
            # print(f"WARNING: At least one course is missing some expected attributes")
            pass

    return courses_teaching


def interactively_get_course(user):
    courses_teaching = get_courses_teaching(user)
    print("\nAvailable courses:")
    print("  --------------------------------------------------------------------")
    for i, course in enumerate(courses_teaching):
        print(f"    {i}: {course.name}")

    course_chosen = False
    while not course_chosen:
        choice = input("\n  Choice [0-n]: ")
        if not (set(choice) <= set(string.digits)):
            print("Please respond with a nonnegative integer.")
        elif int(choice) >= len(courses_teaching):
            print("Choice too large.")
        else:
            choice = int(choice)
            print(
                "  --------------------------------------------------------------------"
            )
            selection = courses_teaching[choice]
            print(f"  You selected {choice}: {selection.name}")
            confirmation = input("  Confirm choice? [y/n] ")
            if confirmation in ["", "\n", "y", "Y"]:
                course_chosen = True
                course = selection
                break
    print("\n")
    return course


def interactively_get_section(course, can_choose_none=True):
    """Choose a section (or not choice) from a menu.

    Returns:
        None/canvasapi.section.Section: None or a section object.
    """
    print(f"\nSelect a Section from {course}.\n")
    print("  Available Sections:")
    print("  --------------------------------------------------------------------")

    if not can_choose_none:
        raise NotImplementedError("Sorry, not implemented yet")

    sections = list(course.get_sections())
    i = 0
    if can_choose_none:
        print(
            f"    {i}: Do not choose a section (None) (Probably the right choice; read the help)"
        )
        i += 1
    for section in sections:
        print(f"    {i}: {section.name} ({section.id})")
        i += 1

    while True:
        choice = input("\n  Choice [0-n]: ")
        if not (set(choice) <= set(string.digits)):
            print("Please respond with a nonnegative integer.")
        elif int(choice) >= len(sections) + 1:
            print("Choice too large.")
        else:
            choice = int(choice)
            print(
                "  --------------------------------------------------------------------"
            )
            if choice == 0:
                section = None
                print(f"  You selected {choice}: None")
            else:
                section = sections[choice - 1]
                print(f"  You selected {choice}: {section.name} ({section.id})")
            confirmation = input("  Confirm choice? [y/n] ")
            if confirmation in ["", "\n", "y", "Y"]:
                print("\n")
                return section


def interactively_get_assignment(course, **kw):
    print(f"\nSelect an assignment for {course}.\n")
    print("  Available assignments:")
    print("  --------------------------------------------------------------------")

    assignments = list(course.get_assignments(**kw))
    for i, assignment in enumerate(assignments):
        print(f"    {i}: {assignment.name}")

    assignment_chosen = False
    while not assignment_chosen:
        choice = input("\n  Choice [0-n]: ")
        if not (set(choice) <= set(string.digits)):
            print("Please respond with a nonnegative integer.")
        elif int(choice) >= len(assignments):
            print("Choice too large.")
        else:
            choice = int(choice)
            print(
                "  --------------------------------------------------------------------"
            )
            selection = assignments[choice]
            print(f"  You selected {choice}: {selection.name}")
            confirmation = input("  Confirm choice? [y/n] ")
            if confirmation in ["", "\n", "y", "Y"]:
                assignment_chosen = True
                assignment = selection
    print("\n")
    return assignment


def get_course_by_partial_name(course_name, user):
    # TODO: currently unused I think
    # TODO: better to warn if multiple matches instead of first one?
    for course in get_courses_teaching(user):
        if course_name in course.name:
            return course
    raise ValueError("Could not find a matching course")


def get_course_by_id_number(course_number, user):
    for course in get_courses_teaching(user):
        if course_number == course.id:
            return course
    raise ValueError("Could not find a matching course")


def get_assignment_by_id_number(course, num, **kw):
    for assignment in course.get_assignments(**kw):
        if assignment.id == num:
            return assignment
    raise ValueError(f"Could not find assignment matching id={num}")


def get_section_by_id_number(course, num):
    for section in course.get_sections():
        if section.id == num:
            return section
    raise ValueError(f"Could not find section matching id={num}")


def canvas_login(api_url=None, api_key=None):
    """Login to a Canvas server using an API key.

    args:
        api_url (str/None): server to login to, uses a default
            if omitted.
        api_key (str/None): the API key.  Will load from disc if
            omitted.  TODO: Could consider prompting in future.

    return:
        canvasapi.current_user.CurrentUser
    """
    if not api_url:
        api_url = __DEFAULT_CANVAS_API_URL__
    if not api_key:
        warn(
            "Loading from `api_secrets.py` is deprecated: consider changing your script to use env vars instead",
            category=DeprecationWarning,
        )
        from api_secrets import my_key as API_KEY

        api_key = API_KEY
        del API_KEY
    canvas = Canvas(api_url, api_key)
    this_user = canvas.get_current_user()
    del canvas
    return this_user


def get_sis_id_to_sub_and_name_table(subs):
    # Why the heck is canvas so stupid about not associating student
    # IDs with student submissions
    conversion = get_conversion_table()

    sis_id_to_sub = {}
    for sub in subs:
        canvas_id = sub.user_id
        try:
            name, sis_id = conversion[str(canvas_id)]
            sis_id_to_sub[sis_id] = (sub, name)
        except KeyError:
            print(
                f"couldn't find student information associated with canvas id {canvas_id}..."
            )

    return sis_id_to_sub



def sis_id_to_student_dict(student_list):
    out_dict = {}
    for student in student_list:
        assert student.role == "StudentEnrollment"
        try:
            assert student.sis_user_id is not None
        except AssertionError:
            # print(student.user_id)
            pass
            # print(student.)
        out_dict[student.sis_user_id] = student
    return out_dict



def get_sis_id_to_marks(headers=['Total'], post_process=lambda x: x):
    """A dictionary of the Student Number ("sis id") to the marks specified by the csv headers in the List/tuple `headers` (default: ['Total']).
    Marks can be post-processed by an arbitrary function `post_process` (default: no op). """

    df = pandas.read_csv("marks.csv", dtype="object")
    d = df.set_index("StudentID")[headers].to_dict()


    if len(headers)==1:
        marks = [ post_process(m) for m in d[headers[0]].values()]
    else:
        marks = [ [post_process(m) for m in marks] for marks in zip(*[d[h].values() for h in headers])]

    ids = list(d[headers[0]].keys())

    return {id:mark for id, mark in zip(ids, marks)}


    # TODO: capacity to specify the csv file(s) - would be nice to have the ability to read from multiple files

def assignment_submitter(assignment, section=None, rubric_headers=False):

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
        assignment.edit(assignment={'use_rubric_for_grading':True})
        rubric_ids = [ item['id']  for item in assignment.rubric]
        rating_ids = [{ rating['points']:rating['id']  for rating in item['ratings'] } for item in assignment.rubric]
        rating_descs = [{ rating['points']:rating['description']  for rating in item['ratings'] } for item in assignment.rubric]
        sis_id_to_rubric_marks = get_sis_id_to_marks(headers=rubric_headers)

    def wait():
        time.sleep(random.uniform(0.25, 0.5))

    def push_to_canvas(sis_id, comments=None, submission_files=None, dry_run=False):
        ##TODO: move files after upload
        not_pushed = []

        try:
            sub, name = sis_id_to_sub_and_name[sis_id]
            new_sub=sub
            student = sis_id_to_students[sis_id]
            total_mark = sis_id_to_marks[sis_id]
            if rubric_headers:
                rubric_marks = sis_id_to_rubric_marks[sis_id]


        except KeyError:
            print(f"No student # {sis_id} in Canvas!")
            print("  Hopefully this is 1-1 w/ a prev canvas id error")
            print("  SKIPPING this submission and continuing")
            return 

        assert sub.user_id == student.user_id

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
                    except CanvasException as e:
                        print(e)
                        not_pushed.append(c.name)

                    wait()

        if submission_files:
            submission_files = submission_files if isinstance(submission_files, Iterable) else [submission_files]
            ids = []
            for f in submission_files:
                if dry_run:
                    not_pushed.append(f.name)
                else:
                    try:
                        up = assignment.upload_to_submission(f, user=sub.user_id)
                        ids.append(up[1]['id'])
                    except CanvasException as e:
                        print(e)
                        not_pushed.append(f.name)

                    wait()

            new_sub = sub.edit(submission={'submission_type':'online_upload', 'file_ids':ids})        

        
        if dry_run:
            not_pushed.append(total_mark)
            if rubric_headers:
                for i, (rating_desc, mark) in enumerate(zip(rating_descs, rubric_marks)):
                        not_pushed.append(f'rubric item {i+1}: {rating_desc[float(mark)]}')
        else:
            sub_data = {'submission':{"posted_grade": total_mark},'user':user}

            if rubric_headers:
                rubric_assessment = {rubric_id:{'rating_id': rating_id[float(mark)], 'points': mark} for rubric_id, rating_id, mark in zip(rubric_ids, rating_ids, rubric_marks)}
                sub_data['rubric_assessment'] = rubric_assessment
            try:
                new_sub = sub.edit(**sub_data)
                wait()

            except CanvasException as e:
                print(e)
                not_pushed.append(total_mark)

        sis_id_to_sub_and_name[sis_id]=(new_sub, name)
        
        return [(m, sis_id, name) for m in not_pushed]
    
    return push_to_canvas 
