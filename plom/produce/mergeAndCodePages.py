# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2019 Andrew Rechnitzer
# Copyright (C) 2019-2021 Colin B. Macdonald
# Copyright (C) 2020 Vala Vakilian
# Copyright (C) 2020 Dryden Wiebe

import shlex
import subprocess
import tempfile
from pathlib import Path

import pyqrcode
import fitz

from plom.tpv_utils import encodeTPV
from plom.produce import paperdir as _paperdir

paperdir = Path(_paperdir)


def create_QR_file_dictionary(length, test, page_versions, code, dur):
    """Creates a dictionary of the QR codes and save them.

    Arguments:
        length {int} -- Length of the document or number of pages.
        test {int} -- Test number based on the combination we have around (length ^ versions - initial pages) tests.
        page_versions {dict} -- (int:int) Dictionary representing the version of each page for this test.
        code {Str} -- 6 digit distinguished code for the document.
        dur (pathlib.Path): a directory to save the QR codes.

    Returns:
        dict -- dict(int: dict(int: Str)) a dictionary that has another embedded dictionary for each page.
                The embedded dictionary has a string for QR code paths saved for each corner.
    """

    # Command line parameters to imagemagick's mogrify
    # puts a frame around the image.
    mogParams = ' -mattecolor black -frame 1x1 -background "#FFFFFF" ' "-flatten"

    qr_file = {}

    for page_index in range(1, length + 1):
        # 4 qr codes for the corners (one will be omitted for the staple)
        qr_file[page_index] = {}

        for corner_index in range(1, 5):
            # the tpv (test page version) is a code used for creating the qr code
            tpv = encodeTPV(
                test, page_index, page_versions[page_index], corner_index, code
            )
            qr_code = pyqrcode.create(tpv, error="H")

            # save it in the associated file
            qr_file[page_index][corner_index] = (
                dur / f"page{page_index}_{corner_index}.png"
            )
            qr_code.png(qr_file[page_index][corner_index], scale=4)

            # use a terminal mogrify process to put a border around the QR code
            cmd = shlex.split(
                "mogrify {} {}".format(mogParams, qr_file[page_index][corner_index])
            )
            subprocess.run(cmd, check=True)

    return qr_file


def create_exam_and_insert_QR(
    name,
    code,
    length,
    versions,
    test,
    page_versions,
    qr_file,
    no_qr=False,
):
    """Creates the exam objects and insert the QR codes.

    Creates the exams objects from the pdfs stored at sourceVersions.
    Then adds the 3 QR codes for each page.
    (We create 4 QR codes but only add 3 of them because of the staple side, see below).

    Arguments:
        name (str): Document Name.
        code (str): 6 digits distinguishing this document from others.
        length (int): length of the document, number of pages.
        versions (int): Number of version of this document.
        test (int): the test number.
        page_versions (dict): version number for each page of this test.
        qr_file (dict): a dict of dicts.  The outer keys are integer
            page numbers.  The inner keys index the corners with ints,
            the meaning of which is hopefully documented elsewhere.  The
            inner values are strings/pathlib.Path for images of the
            QR codes for each corner.

    Keyword Arguments:
        no_qr (bool): whether to paste in QR-codes (default: False)
            Note backward logic: False means yes to QR-codes.

    Returns:
        fitz.Document -- PDF document type returned as the exam, similar to a dictionary with the ge numbers as the keys.
    """

    # A (int : fitz.fitz.Document) dictionary that has the page document/path from each source based on page version
    version_paths_for_pages = {}
    for version_index in range(1, versions + 1):
        version_paths_for_pages[version_index] = fitz.open(
            "sourceVersions/version{}.pdf".format(version_index)
        )

    # Create test pdf as "exam"
    exam = fitz.open()
    # Insert the relevant page-versions into this pdf.
    for page_index in range(1, length + 1):
        # Pymupdf starts pagecounts from 0 rather than 1. So offset things.
        exam.insert_pdf(
            version_paths_for_pages[page_versions[page_index]],
            from_page=page_index - 1,
            to_page=page_index - 1,
            start_at=-1,
        )

    # Get page width and height
    page_width = exam[0].bound().width
    page_height = exam[0].bound().height

    # create two "do not write" (DNW) rectangles accordingly with TL (top left) and TR (top right)
    rDNW_TL = fitz.Rect(15, 15, 90, 90)
    rDNW_TR = fitz.Rect(page_width - 90, 15, page_width - 15, 90)

    # 70x70 page-corner boxes for the QR codes
    # TL: Top Left, TR: Top Right, BL: Bottom Left, BR: Bottom Right
    rTL = fitz.Rect(15, 20, 85, 90)
    rTR = fitz.Rect(page_width - 85, 20, page_width - 15, 90)
    rBL = fitz.Rect(15, page_height - 90, 85, page_height - 20)
    rBR = fitz.Rect(
        page_width - 85, page_height - 90, page_width - 15, page_height - 20
    )

    for page_index in range(length):
        # Workaround Issue #1347: unnecessary for pymupdf>=1.18.7
        exam[page_index].clean_contents()
        # test/page stamp in top-centre of page
        rect = fitz.Rect(page_width // 2 - 40, 20, page_width // 2 + 40, 44)
        text = "{}.{}".format(str(test).zfill(4), str(page_index + 1).zfill(2))
        excess = exam[page_index].insert_textbox(
            rect,
            text,
            fontsize=18,
            color=[0, 0, 0],
            fontname="Helvetica",
            fontfile=None,
            align=1,
        )
        assert excess > 0, "Text didn't fit: is paper number label too long?"
        exam[page_index].draw_rect(rect, color=[0, 0, 0])

        if no_qr:
            # no more processing of this page if QR codes unwanted
            continue

        # stamp DNW near staple: even/odd pages different
        # Top Left for even pages, Top Right for odd pages
        # TODO: Perhaps this process could be improved by putting
        # into functions
        rDNW = rDNW_TL if page_index % 2 == 0 else rDNW_TR
        shape = exam[page_index].new_shape()
        shape.draw_line(rDNW.top_left, rDNW.top_right)
        if page_index % 2 == 0:
            shape.draw_line(rDNW.top_right, rDNW.bottom_left)
        else:
            shape.draw_line(rDNW.top_right, rDNW.bottom_right)
        shape.finish(width=0.5, color=[0, 0, 0], fill=[0.75, 0.75, 0.75])
        shape.commit()
        if page_index % 2 == 0:
            # offset by trial-and-error, could be improved
            rDNW = rDNW + (19, 19, 19, 19)
        else:
            rDNW = rDNW + (-19, 19, -19, 19)
        mat = fitz.Matrix(45 if page_index % 2 == 0 else -45)
        pivot = rDNW.tr / 2 + rDNW.bl / 2
        morph = (pivot, mat)
        excess = exam[page_index].insert_textbox(
            rDNW,
            name,
            fontsize=8,
            fontname="Helvetica",
            fontfile=None,
            align=1,
            morph=morph,
        )
        assert excess > 0, "Text didn't fit: shortname too long? font issue?"

        # paste in the QR-codes
        # Grab the tpv QRcodes for current page and put them on the pdf
        # Remember that we only add 3 of the 4 QR codes for each page since
        # we always have a corner section for staples and such
        qr_code = {}
        for corner_index in range(1, 5):
            # TODO: can remove str() once minimum pymupdf is 1.18.9
            qr_code[corner_index] = fitz.Pixmap(
                str(qr_file[page_index + 1][corner_index])
            )
        if page_index % 2 == 0:
            exam[page_index].insert_image(rTR, pixmap=qr_code[1], overlay=True)
            exam[page_index].insert_image(rBR, pixmap=qr_code[4], overlay=True)
            exam[page_index].insert_image(rBL, pixmap=qr_code[3], overlay=True)
        else:
            exam[page_index].insert_image(rTL, pixmap=qr_code[2], overlay=True)
            exam[page_index].insert_image(rBL, pixmap=qr_code[3], overlay=True)
            exam[page_index].insert_image(rBR, pixmap=qr_code[4], overlay=True)

    return exam


def is_possible_to_encode_as(s, x):
    """A function that checks if string s is encodable by format x.

    Arguments:
        s {Str} -- Text String given.
        x {Str} -- Encoding type.

    Returns:
        bool -- True/False
    """
    try:
        _tmp = s.encode(x)
        return True
    except UnicodeEncodeError:
        return False


def insert_extra_info(extra, exam):
    """Creates the extra info (usually student name and id) boxes and places them in the first page.

    Arguments:
        extra (dict): dictionary with student id and name.
        exam (fitz.Document): PDF document.

    Raises:
        ValueError: Raise error if the student name and number is not encodable.

    Returns:
        fitz.Document: the exam object from the input, but with the extra
            info added into the first page.
    """

    # Get page width and height
    page_width = exam[0].bound().width
    page_height = exam[0].bound().height

    student_id = extra["id"]
    student_name = extra["name"]
    # a file for the student-details
    YSHIFT = 0.4  # where on page is centre of box 0=top, 1=bottom

    # Creating the student id \n name text file
    txt = "{}\n{}".format(student_id, student_name)

    sign_here = "Please sign here"

    # Getting the dimensions of the box
    try:
        student_id_width = (
            max(
                fitz.get_text_length(student_id, fontsize=36, fontname="Helvetica"),
                fitz.get_text_length(student_name, fontsize=36, fontname="Helvetica"),
                fitz.get_text_length(sign_here, fontsize=48, fontname="Helvetica"),
            )
            * 1.1
            * 0.5
        )
    except AttributeError:
        # workaround https://github.com/pymupdf/PyMuPDF/issues/1085
        # TODO: drop this code when we dependent on PyMuPDF>=1.18.14
        student_id_width = (
            max(
                fitz.getTextlength(student_id, fontsize=36, fontname="Helvetica"),
                fitz.getTextlength(student_name, fontsize=36, fontname="Helvetica"),
                fitz.getTextlength(sign_here, fontsize=48, fontname="Helvetica"),
            )
            * 1.1
            * 0.5
        )
    student_id_height = 36 * 1.3

    # We have 2 rectangles for the student name and student id
    student_id_rect_1 = fitz.Rect(
        page_width // 2 - student_id_width,
        page_height * YSHIFT - student_id_height,
        page_width // 2 + student_id_width,
        page_height * YSHIFT + student_id_height,
    )
    student_id_rect_2 = fitz.Rect(
        student_id_rect_1.x0,
        student_id_rect_1.y1,
        student_id_rect_1.x1,
        student_id_rect_1.y1 + 48 * 1.3,
    )
    exam[0].draw_rect(student_id_rect_1, color=[0, 0, 0], fill=[1, 1, 1], width=2)
    exam[0].draw_rect(student_id_rect_2, color=[0, 0, 0], fill=[1, 1, 1], width=2)

    # TODO: This could be put into one function
    # Also VALA doesn't understand the TODO s
    if is_possible_to_encode_as(txt, "Latin-1"):
        fontname = "Helvetica"
    elif is_possible_to_encode_as(txt, "gb2312"):
        # TODO: Double-check encoding name.  Add other CJK (how does Big5
        # vs GB work?).  Check printers can handle these or do we need to
        # embed a font?  (Adobe Acrobat users need to download something)
        fontname = "china-ss"
    else:
        # TODO: or warn use Helvetica, get "?" chars
        raise ValueError("Don't know how to write name {} into PDF".format(txt))

    # We insert the student id text boxes
    excess = exam[0].insert_textbox(
        student_id_rect_1,
        txt,
        fontsize=36,
        color=[0, 0, 0],
        fontname=fontname,
        fontfile=None,
        align=1,
    )
    assert excess > 0, "Text didn't fit: student ID too long?"

    # We insert the student name text boxes
    excess = exam[0].insert_textbox(
        student_id_rect_2,
        sign_here,
        fontsize=48,
        color=[0.9, 0.9, 0.9],
        fontname="Helvetica",
        fontfile=None,
        align=1,
    )
    assert excess > 0, "Text didn't fit: student name too long?"

    return exam


def save_PDF(extra, exam, papernum):
    """Used for saving the exams in paperdir.

    Arguments:
        extra (dict/None): dictionary with student id and name.
        exam (fitz.Document): the pdf document.
        papernum (int): the paper/test number.

    """
    # save with ID-number is making named papers: issue #790
    if extra:
        save_name = paperdir / f"exam_{papernum:04}_{extra['id']}.pdf"
    else:
        save_name = paperdir / f"exam_{papernum:04}.pdf"
    # Add the deflate option to compress the embedded pngs
    # see https://pymupdf.readthedocs.io/en/latest/document/#Document.save
    # also do garbage collection to remove duplications within pdf
    # and try to clean up as much as possible.
    # `linear=True` causes https://gitlab.com/plom/plom/issues/284
    exam.save(save_name, garbage=4, deflate=True, clean=True)


def make_PDF(
    name,
    code,
    length,
    versions,
    test,
    page_versions,
    extra=None,
    no_qr=False,
):
    """A function that makes the PDFs and saves the modified exam files.

    Overall it has 4 steps for each document:
    1- Create and save Qr codes.
    2- Create and save exams with the addition of the QR codes.
    3- If extra is defined, add student id and student name.
    4- Finally save the Documents.

    Arguments:
        name {Str} -- Document Name.
        code {Str} -- 6 digit distinguished code for the document.
        length {int} -- Length of the document or number of pages.
        versions {int} -- Number of version of this Document.
        test {int} -- Test number based on the combination we have around (length ^ versions - initial pages) tests.
        page_versions {dict} -- (int:int) dictionary representing the version of each page for this test.
        no_qr {bool} -- Boolean to determine whether or not to paste in qr-codes

    Keyword Arguments:
        extra (dict/None): Dictionary with student id and name or None.

    Raises:
        ValueError: Raise error if the student name and number is not encodable
    """
    # Build all relevant pngs in a temp directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        # create QR codes and other stamps for each test/page/version
        qr_file = create_QR_file_dictionary(
            length, test, page_versions, code, Path(tmp_dir)
        )

        # We then create the exam pdf while adding the QR codes to it
        exam = create_exam_and_insert_QR(
            name,
            code,
            length,
            versions,
            test,
            page_versions,
            qr_file,
            no_qr=no_qr,
        )

        # If we are provided with the student number and student id,
        # we would preferably want to insert them into the first page
        # as a box.
        if extra:
            exam = insert_extra_info(extra, exam)

    save_PDF(extra, exam, test)


def make_fakePDF(
    name,
    code,
    length,
    versions,
    papernum,
    page_versions,
    extra=None,
):
    """Twin to the real make_pdf command - makes empty files."""
    if extra:
        save_name = paperdir / f"exam_{papernum:04}_{extra['id']}.pdf"
    else:
        save_name = paperdir / f"exam_{papernum:04}.pdf"
    save_name.touch()
