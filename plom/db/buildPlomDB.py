# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2019-2021 Andrew Rechnitzer
# Copyright (C) 2019-2021 Colin B. Macdonald
# Copyright (C) 2020 Dryden Wiebe
# Copyright (C) 2021 Nicholas J H Lai

import logging
import random

from plom import check_version_map, make_random_version_map
# from plom.db import PlomDB


log = logging.getLogger("DB")


def buildSpecialRubrics(spec, db):
    # create no-answer-given rubrics
    for q in range(1, 1 + spec["numberOfQuestions"]):
        if not db.createNoAnswerRubric(q, spec["question"]["{}".format(q)]["mark"]):
            raise ValueError("No answer rubric for q.{} already exists".format(q))
    # create standard manager delta-rubrics - but no 0, nor +/- max-mark
    for q in range(1, 1 + spec["numberOfQuestions"]):
        mx = spec["question"]["{}".format(q)]["mark"]
        # make zero mark and full mark rubrics
        rubric = {
            "kind": "absolute",
            "delta": "0",
            "text": "no marks",
            "question": q,
        }
        if not db.McreateRubric("manager", rubric):
            raise ValueError(
                "Manager no-marks-rubric for q.{} already exists".format(q)
            )
        rubric = {
            "kind": "absolute",
            "delta": "{}".format(mx),
            "text": "full marks",
            "question": q,
        }
        if not db.McreateRubric("manager", rubric):
            raise ValueError(
                "Manager full-marks-rubric for q.{} already exists".format(q)
            )

        # now make delta-rubrics
        for m in range(1, mx + 1):
            # make positive delta
            rubric = {
                "delta": "+{}".format(m),
                "text": ".",
                "kind": "delta",
                "question": q,
            }
            if not db.McreateRubric("manager", rubric):
                raise ValueError(
                    "Manager delta-rubric +{} for q.{} already exists".format(m, q)
                )
            # make negative delta
            rubric = {
                "delta": "-{}".format(m),
                "text": ".",
                "kind": "delta",
                "question": q,
            }
            if not db.McreateRubric("manager", rubric):
                raise ValueError(
                    "Manager delta-rubric -{} for q.{} already exists".format(m, q)
                )


def buildExamDatabaseFromSpec(spec, db, version_map=None):
    """Build metadata for exams from spec and insert into the database.

    Arguments:
        spec (dict): exam specification, see :func:`plom.SpecVerifier`.
        db (database): the database to populate.
        version_map (dict/None): optional predetermined version map
            keyed by test number and question number.  If None, we will
            build our own random version mapping.  For the map format
            see :func:`plom.finish.make_random_version_map`.

    Returns:
        bool: True if succuess.
        str: a status string, one line per test, ending with an error if failure.

    Raises:
        ValueError: if database already populated.
        KeyError: invalid question selection scheme in spec.
    """
    if db.is_paper_database_populated():
        raise ValueError("Database already populated")

    # TODO: perhaps this should be called separately...
    buildSpecialRubrics(spec, db)

    if not version_map:
        # TODO: move reproducible random seed support to the make fcn?
        random.seed(spec["privateSeed"])
        version_map = make_random_version_map(spec)
    check_version_map(version_map)

    ok = True
    status = ""

    if not db.createReplacementBundle():
        ok = False
        status += "Error making bundle for replacement pages"

    for t in range(1, spec["numberToProduce"] + 1):
        log.info(
            "Creating DB entry for test {} of {}.".format(t, spec["numberToProduce"])
        )
        success, stat = db.buildSingleTestInDB(t, spec, version_map[t])
        if success is False:
            ok = False
        status += stat
    return ok, status
