# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2019-2021 Andrew Rechnitzer
# Copyright (C) 2019-2021 Colin B. Macdonald
# Copyright (C) 2020 Dryden Wiebe

import logging
import random

from plom.db import PlomDB


log = logging.getLogger("DB")


managerRubrics = [
    {"delta": "-1", "text": "arithmetic", "meta": "standardComment"},
    {"delta": ".", "text": "be careful", "meta": "standardComment"},
    {
        "delta": "0",
        "text": r"tex: you can write \LaTeX, $e^{i\pi} + 1 = 0$",
        "meta": "LaTeX works",
    },
    {"delta": "+1", "text": "good", "meta": "give constructive feedback"},
]


def buildSpecialRubrics(spec, db):
    # create no-answer-given rubrics
    for q in range(1, 1 + spec["numberOfQuestions"]):
        if not db.createNoAnswerRubric(q, spec["question"]["{}".format(q)]["mark"]):
            raise ValueError("No answer rubric for q.{} already exists".format(q))
    # create standard manager rubrics
    for rubric in managerRubrics:
        rubric["tags"] = ""
        for q in range(1, 1 + spec["numberOfQuestions"]):
            rubric["question"] = "{}".format(q)
            if not db.McreateRubric("manager", rubric):
                raise ValueError("Manager rubric for q.{} already exists".format(q))
    # create standard manager delta-rubrics - but no 0
    for q in range(1, 1 + spec["numberOfQuestions"]):
        mx = spec["question"]["{}".format(q)]["mark"]
        for m in range(-mx, mx + 1):
            if m == 0:
                continue
            rubric = {
                # make '+' explicit for positive delta
                "delta": "{}".format(m) if m <= 0 else "+{}".format(m),
                "text": ".",
                "tags": "",
                "meta": "delta",
                "question": q,
            }
            if not db.McreateRubric("manager", rubric):
                raise ValueError(
                    "Manager delta-rubric {} for q.{} already exists".format(m, q)
                )


def buildExamDatabaseFromSpec(spec, db):
    """Build metadata for exams from spec and insert into the database.

    Arguments:
        spec (dict): exam specification, see :func:`plom.SpecVerifier`.
        db (database): the database to populate.

    Returns:
        bool: True if succuess.
        str: a status string, one line per test, ending with an error if failure.

    Raises:
        ValueError: if database already populated.
        KeyError: question selection scheme is invalid.
    """

    buildSpecialRubrics(spec, db)

    if db.areAnyPapersProduced():
        raise ValueError("Database already populated")

    random.seed(spec["privateSeed"])

    ok = True
    status = ""
    # build bundles for annotation images
    # for q in range(1, 1 + spec["numberOfQuestions"]):
    # for v in range(1, 1 + spec["numberOfVersions"]):
    # pass
    # if not db.createAnnotationBundle(q, v):
    #     ok = False
    #     status += "Error making bundle for q.v={}.{}".format(q, v)
    # build bundle for replacement pages (for page-not-submitted images)

    if not db.createReplacementBundle():
        ok = False
        status += "Error making bundle for replacement pages"

    # Note: need to produce these in a particular order for random seed to be
    # reproducibile: so this really must be a loop, not a Pool.
    for t in range(1, spec["numberToProduce"] + 1):
        log.info(
            "Creating DB entry for test {} of {}.".format(t, spec["numberToProduce"])
        )
        if db.createTest(t):
            status += "DB entry for test {:04}:".format(t)
        else:
            status += " Error creating"
            ok = False

        if db.createIDGroup(t, spec["idPages"]["pages"]):
            status += " ID"
        else:
            status += " Error creating idgroup"
            ok = False

        if db.createDNMGroup(t, spec["doNotMark"]["pages"]):
            status += " DNM"
        else:
            status += "Error creating DoNotMark-group"
            ok = False

        for g in range(spec["numberOfQuestions"]):  # runs from 0,1,2,...
            gs = str(g + 1)  # now a str and 1,2,3,...
            if spec["question"][gs]["select"] == "fix":
                # there is only one version so all are version 1
                v = 1
                vstr = "f{}".format(v)
            elif spec["question"][gs]["select"] == "shuffle":
                # version selected randomly in [1, 2, ..., #versions]
                v = random.randint(1, spec["numberOfVersions"])
                vstr = "v{}".format(v)
            else:
                raise KeyError(
                    'problem with spec: expected "fix" or "shuffle" but got "{}".'.format(
                        spec["question"][gs]["select"]
                    )
                )
            if db.createQGroup(t, int(gs), v, spec["question"][gs]["pages"]):
                status += " Q{}{}".format(gs, vstr)
            else:
                status += "Error creating Question {} ver {}".format(gs, vstr)
                ok = False
        status += "\n"

    print("ok, status = ", ok, status)
    return ok, status
