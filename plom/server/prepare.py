# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020 Andrew Rechnitzer
# Copyright (C) 2020-2022 Colin B. Macdonald
# Copyright (C) 2020 Dryden Wiebe
# Copyright (C) 2021 Morgan Arnold
# Copyright (C) 2021 Nicholas J H Lai

"""Tools to prepare a directory for a Plom Server."""

from pathlib import Path
from textwrap import fill, dedent

from plom.server import specdir, confdir
from plom.textools import texFragmentToPNG
from plom.server import pageNotSubmitted
from plom.server import (
    build_self_signed_SSL_keys,
    build_server_directories,
    create_server_config,
)
from .manageUserFiles import save_initial_user_list


class PlomServerConfigurationError(Exception):
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)


def build_not_submitted_and_do_latex_checks(basedir=Path(".")):
    basedir = Path(basedir)
    please_check = basedir / "pleaseCheck"
    please_check.mkdir(exist_ok=True)

    # check build of fragment
    ct = please_check / "check_tex.png"
    pns = basedir / specdir / "pageNotSubmitted.pdf"
    qns = basedir / specdir / "questionNotSubmitted.pdf"
    dnmns = basedir / specdir / "dnmPageNotSubmitted.pdf"
    agid = basedir / specdir / "autoGeneratedID.pdf"

    fragment = r"\( \mathbb{Z} / \mathbb{Q} \) The cat sat on the mat and verified \LaTeX\ worked okay for Plom."

    valid, value = texFragmentToPNG(fragment)
    if valid:
        with open(ct, "wb") as f:
            f.write(value)
    else:
        print("=" * 80)
        print("\nThere was an error processing the testing TeX fragment:\n")
        print(value)
        raise PlomServerConfigurationError(
            "Error latex'ing fragment.  See messages above and/or check your latex distribution."
        )

    # build template pageNotSubmitted.pdf just in case needed
    if not pageNotSubmitted.build_not_submitted_page(pns):
        raise PlomServerConfigurationError(
            "Error building 'pageNotSubmitted.pdf' template page. Please check your latex distribution."
        )
    # build template questionNotSubmitted.pdf just in case needed
    if not pageNotSubmitted.build_not_submitted_question(qns):
        raise PlomServerConfigurationError(
            "Error building 'questionNotSubmitted.pdf' template page. Please check your latex distribution."
        )
    # build template dnmPageNotSubmitted.pdf just in case needed
    if not pageNotSubmitted.build_not_submitted_dnm(dnmns):
        raise PlomServerConfigurationError(
            "Error building 'dnmPageNotSubmitted.pdf' template page. Please check your latex distribution."
        )
    # build template dnmPageNotSubmitted.pdf just in case needed
    if not pageNotSubmitted.build_autogen_id_page(agid):
        raise PlomServerConfigurationError(
            "Error building 'autoGeneratedID.pdf' template page. Please check your latex distribution."
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


def initialise_server(
    basedir, *, port=None, name=None, make_selfsigned_keys=True, manager_pw=None
):
    """Setup various files needed before a Plom server can be started.

    args:
        basedir (pathlib.Path/str/None): the directory to prepare.  If
            `None` use the current working directory.

    keyword args:
        port (int/None): the port to use, None for a default value.
        name (str/None): None for a default value.
        make_selfsigned_keys (bool): Defaults to True.
        manager_pw (str/None): the initial manager password.  Can be
            omitted; other ways to set this later.
    """
    if not basedir:
        basedir = Path(".")
    basedir = Path(basedir)
    print("Build required directories")
    build_server_directories(basedir)
    if make_selfsigned_keys:
        print("Building self-signed SSL key for server")
        try:
            build_self_signed_SSL_keys(basedir / confdir)
        except FileExistsError as err:
            print(f"Skipped SSL keygen - {err}")

    print("Copy server networking configuration template into place.")
    try:
        create_server_config(basedir / confdir, port=port, name=name)
    except FileExistsError as err:
        print(f"Skipping server config - {err}")
    else:
        if not name:
            print(
                "You may want to update '{}' with the correct name (or IP) and "
                "port of your server.".format(confdir / "serverDetails.toml")
            )

    print(
        "Do latex checks and build 'pageNotSubmitted.pdf', 'questionNotSubmitted.pdf', 'dnmPageNotSubmitt.pdf' and 'autoGeneratedID.pdf' in case needed"
    )
    build_not_submitted_and_do_latex_checks(basedir)

    if manager_pw:
        print("Saving initial manager password")
        init_user_list = basedir / confdir / "bootstrap_initial_users.json"
        if init_user_list.exists():
            print(f"WARNING - overwriting existing {init_user_list}")
        save_initial_user_list({"manager": manager_pw}, basedir=basedir)
