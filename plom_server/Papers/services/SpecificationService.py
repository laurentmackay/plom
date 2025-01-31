# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 Andrew Rechnitzer
# Copyright (C) 2022-2023 Edith Coates
# Copyright (C) 2022-2023 Colin B. Macdonald
# Copyright (C) 2022 Brennen Chiu

import logging
from typing import Dict
from pathlib import Path
import sys

if sys.version_info < (3, 11):
    import tomli as tomllib
else:
    import tomllib

from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction

from plom import SpecVerifier

from ..models import Specification, SpecQuestion
from ..serializers import SpecSerializer

# TODO - build similar for solution specs
# NOTE - this does not **validate** test specs, it assumes the spec is valid


log = logging.getLogger("ValidatedSpecService")


@transaction.atomic
def load_spec_from_toml(
    pathname,
    update_staging=False,
    public_code=None,
) -> Specification:
    """Load a test spec from a TOML file, and saves to the database.

    Will call the SpecSerializer on the loaded TOML string and validate.

    Args:
        pathname (pathlib.Path or string): the filename on disk.
        update_staging (bool): if true, update the staging specification (mainly for UI purposes)
        public_code (str | None): pass a manually specified public code (mainly for unit testing)

    Returns:
        Specification: saved test spec instance.
    """
    with open(Path(pathname), "rb") as toml_f:
        data = tomllib.load(toml_f)

        # TODO: we must re-format the question list-of-dicts into a dict-of-dicts in order to make SpecVerifier happy.
        data["question"] = question_list_to_dict(data["question"])
        serializer = SpecSerializer(data=data)
        serializer.is_valid()
        valid_data = serializer.validated_data

        if public_code:
            valid_data["publicCode"] = public_code

        if update_staging:
            from SpecCreator.services import StagingSpecificationService

            StagingSpecificationService().create_from_dict(serializer.validated_data)

        return serializer.create(serializer.validated_data)


@transaction.atomic
def is_there_a_spec():
    """Has a test-specification been uploaded to the database."""
    return Specification.objects.count() == 1


@transaction.atomic
def get_the_spec() -> Dict:
    """Return the test-specification from the database.

    Returns:
        The exam specification as a dictionary.

    Exceptions:
        ObjectDoesNotExist: no exam specification yet.
    """
    try:
        spec = Specification.objects.get()
        serializer = SpecSerializer(
            spec, context={"question": SpecQuestion.objects.all()}
        )
        return serializer.data
    except Specification.DoesNotExist:
        raise ObjectDoesNotExist("The database does not contain a test specification.")


@transaction.atomic
def get_the_spec_as_toml():
    """Return the test-specification from the database.

    If present, remove the private seed.  But the public code
    is included (if present).
    """
    spec = get_the_spec()
    spec.pop("privateSeed", None)
    sv = SpecVerifier(spec)
    return sv.as_toml_string()


@transaction.atomic
def get_the_spec_as_toml_with_codes():
    """Return the test-specification from the database.

    .. warning::
        Note this includes both the public code and the private
        seed.  If you are calling this, consider carefully whether
        you need the private seed.  At the time of writing, no one
        is calling this.
    """
    sv = SpecVerifier(get_the_spec())
    return sv.as_toml_string()


@transaction.atomic
def store_validated_spec(validated_spec: Dict) -> None:
    """Takes the validated test specification and stores it in the db.

    Args:
        validated_spec (dict): A dictionary containing a validated test
            specification.
    """
    serializer = SpecSerializer()
    serializer.create(validated_spec)


@transaction.atomic
def remove_spec() -> None:
    """Removes the test specification from the db, if possible.

    This can only be done if no tests have been created.

    Raises:
        ObjectDoesNotExist: no exam specification yet.
        MultipleObjectsReturned: cannot remove spec because
            there are already papers.
    """
    if not is_there_a_spec():
        raise ObjectDoesNotExist("The database does not contain a test specification.")

    from .paper_info import PaperInfoService

    if PaperInfoService().is_paper_database_populated():
        raise MultipleObjectsReturned("Database is already populated with test-papers.")

    Specification.objects.filter().delete()


@transaction.atomic
def get_longname() -> str:
    """Get the long name of the exam.

    Exceptions:
        ObjectDoesNotExist: no exam specification yet.
    """
    spec = Specification.objects.get()
    return spec.longName


@transaction.atomic
def get_shortname() -> str:
    """Get the short name of the exam.

    Exceptions:
        ObjectDoesNotExist: no exam specification yet.
    """
    spec = Specification.objects.get()
    return spec.name


@transaction.atomic
def get_n_questions() -> int:
    """Get the number of questions in the test.

    Exceptions:
        ObjectDoesNotExist: no exam specification yet.
    """
    spec = Specification.objects.get()
    return spec.numberOfQuestions


@transaction.atomic
def get_n_versions() -> int:
    """Get the number of test versions.

    Exceptions:
        ObjectDoesNotExist: no exam specification yet.
    """
    spec = Specification.objects.get()
    return spec.numberOfVersions


@transaction.atomic
def get_n_pages() -> int:
    """Get the number of pages in the test.

    Exceptions:
        ObjectDoesNotExist: no exam specification yet.
    """
    spec = Specification.objects.get()
    return spec.numberOfPages


@transaction.atomic
def get_question_mark(question_one_index) -> int:
    """Get the max mark of a given question.

    Args:
        question_one_index (str/int): question number, indexed from 1.

    Returns:
        The maximum mark.

    Raises:
        ObjectDoesNotExist: no question exists with the given index.
    """
    question = SpecQuestion.objects.get(question_number=question_one_index)
    return question.mark


@transaction.atomic
def n_pages_for_question(question_one_index) -> int:
    question = SpecQuestion.objects.get(question_number=question_one_index)
    return len(question.pages)


@transaction.atomic
def get_question_label(question_one_index) -> str:
    """Get the question label from its one-index.

    Args:
        question_one_index (str | int): question number indexed from 1.

    Returns:
        The question label.

    Raises:
        ObjectDoesNotExist: no question exists with the given index.
    """
    question = SpecQuestion.objects.get(question_number=question_one_index)
    return question.label


@transaction.atomic
def question_list_to_dict(questions: list[Dict]) -> Dict[str, Dict]:
    """Convert a list of question dictionaries to a nested dict with question numbers as keys."""
    return {str(i + 1): q for i, q in enumerate(questions)}
