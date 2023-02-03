# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022-2023 Edith Coates

from django.db import models

from Base.models import BaseTask, BaseAction
from Papers.models import Paper
from Mark.models import Annotation


class MarkingTask(BaseTask):
    """
    Represents a single question that needs to be marked.

    paper: reference to Paper, the test-paper of the question
    code: str, a unique string for indexing a marking task
    question_number: int, the question to mark
    question_version: int, the version of the question
    """

    paper = models.ForeignKey(Paper, null=False, on_delete=models.CASCADE)
    code = models.TextField(default="", unique=True)
    question_number = models.PositiveIntegerField(null=False, default=0)
    question_version = models.PositiveIntegerField(null=False, default=0)


class ClaimMarkingTask(BaseAction):
    """
    Represents a marker client claiming a marking task.
    """

    pass


class SurrenderMarkingTask(BaseAction):
    """
    Represents a marker client surrendering a marking task.
    """

    pass


class MarkAction(BaseAction):
    """
    Represents a marker client submitting an annotation and a mark.
    """

    claim_action = models.ForeignKey(ClaimMarkingTask, on_delete=models.CASCADE)
    annotation = models.OneToOneField(Annotation, null=True, on_delete=models.SET_NULL)