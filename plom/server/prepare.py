# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020 Andrew Rechnitzer
# Copyright (C) 2020-2021 Colin B. Macdonald
# Copyright (C) 2020 Dryden Wiebe
# Copyright (C) 2021 Morgan Arnold
# Copyright (C) 2021 Nicholas J H Lai

"""Tools to prepare a directory for a Plom Server."""

from pathlib import Path
from textwrap import fill, dedent

from plom.server import specdir as specdirname
from plom.server import confdir
from plom.textools import texFragmentToPNG
from plom.server import pageNotSubmitted
from plom.server import (
    build_self_signed_SSL_keys,
    build_server_directories,
    check_server_directories,
    check_server_fully_configured,
    create_server_config,
    create_blank_predictions,
    parse_user_list,
)


class PlomServerConfigurationError(Exception):
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)


def build_not_submitted_and_do_latex_checks(basedir=Path(".")):
    basedir = Path(basedir)
    please_check = basedir / "pleaseCheck"
    please_check.mkdir(exist_ok=True)

    # check build of fragment
    ct = please_check / "check_tex.png"
    pns = basedir / specdirname / "pageNotSubmitted.pdf"
    qns = basedir / specdirname / "questionNotSubmitted.pdf"

    fragment = r"\( \mathbb{Z} / \mathbb{Q} \) The cat sat on the mat and verified \LaTeX\ worked okay for plom."

    if not texFragmentToPNG(fragment, ct):
        raise PlomServerConfigurationError(
            "Error latex'ing fragment. Please check your latex distribution."
        )

    # build template pageNotSubmitted.pdf just in case needed
    if not pageNotSubmitted.build_not_submitted_page(pns):
        raise PlomServerConfigurationError(
            "Error building 'pageNotSubmitted.pdf' template page. Please check your latex distribution."
        )
    # build template pageNotSubmitted.pdf just in case needed
    if not pageNotSubmitted.build_not_submitted_question(qns):
        raise PlomServerConfigurationError(
            "Error building 'questionNotSubmitted.pdf' template page. Please check your latex distribution."
        )

    # Try building a replacement for missing page.
    if not pageNotSubmitted.build_test_page_substitute(
        0, 0, 0, template=pns, out_dir=please_check
    ):
        raise PlomServerConfigurationError(
            "Error building replacement for missing test page."
        )
    # Try building a replacement for missing page.
    if not pageNotSubmitted.build_homework_question_substitute(
        0, 0, template=qns, out_dir=please_check
    ):
        raise PlomServerConfigurationError(
            "Error building replacement for missing homework question."
        )

    print(
        fill(
            dedent(
                """
                Simple latex checks done.  If you feel the need, then please
                examine the png files in directory 'pleaseCheck'.
                One should be a short latex'd fragment with some mathematics
                and text, while the others should be mostly blank pages with
                'not submitted' stamped across them.  It is safe delete
                these files and the directory.
                """
            )
        )
    )


def initialise_server(port):
    """TODO: add basedir and docstring"""
    print("Build required directories")
    build_server_directories()
    print("Building self-signed SSL key for server")
    try:
        build_self_signed_SSL_keys()
    except FileExistsError as err:
        print(f"Skipped SSL keygen - {err}")

    print("Copy server networking configuration template into place.")
    try:
        create_server_config(port=port)
    except FileExistsError as err:
        print(f"Skipping server config - {err}")
    else:
        print(
            "You may want to update '{}' with the correct name (or IP) and "
            "port of your server.".format(confdir / "serverDetails.toml")
        )

    print("Build blank predictionlist for identifying.")
    try:
        create_blank_predictions()
    except FileExistsError as err:
        print(f"Skipping prediction list - {err}")

    print(
        "Do latex checks and build 'pageNotSubmitted.pdf', 'questionNotSubmitted.pdf' in case needed"
    )
    build_not_submitted_and_do_latex_checks()
