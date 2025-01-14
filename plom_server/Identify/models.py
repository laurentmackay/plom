# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022-2023 Edith Coates
# Copyright (C) 2023 Natalie Balashov
# Copyright (C) 2023 Andrew Rechnitzer
# Copyright (C) 2023 Colin B. Macdonald

from django.db import models
from django.contrib.auth.models import User

from Base.models import BaseTask, BaseAction
from Papers.models import Paper


class PaperIDTask(BaseTask):
    """Represents a test-paper that needs to be identified.

    paper: reference to Paper that needs to be IDed.
    latest_action: reference to `PaperIDAction`, the latest identification
        for the paper.  "Latest" need not refer to time, it can be
        moved around to different `PaperIDAction`s if you wish.
    priority: a float priority that provides the ordering for tasks
        presented for IDing, zero by default.

    These also have a ``status`` that they inherit from their parent
    ``BaseTask``.  There is *currently* some complexity about updating
    this b/c there are changes that MUST be made (but are not automatically
    made) in the Actions which are attached to this Task.
    """

    paper = models.ForeignKey(Paper, on_delete=models.CASCADE)
    latest_action = models.OneToOneField(
        "PaperIDAction", unique=True, null=True, on_delete=models.SET_NULL
    )
    iding_priority = models.FloatField(null=True, default=0.0)


class PaperIDAction(BaseAction):
    """Represents an identification of a test-paper.

    is_valid: this Action is valid or not.  There is some... complexity
        about this.  There can be multiple Actions attached to a single
        Task.  In theory only one of them (at most one of them) can be
        valid.  Currently this IS NOT ENFORCED, so callers MUST maintain
        this logic themselves.
        There are states that are possible but we don't want to get into
        them: for example (but not exhaustive), you should not have an
        ``status=OutOfDate`` with a valid IDAction attached to that Task.
    student_name:
    student_id:
    """

    is_valid = models.BooleanField(default=True)
    student_name = models.TextField(default="")
    student_id = models.TextField(default="")


class IDPrediction(models.Model):
    paper = models.ForeignKey(Paper, null=False, on_delete=models.CASCADE)
    student_id = models.CharField(null=True, max_length=255)
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    predictor = models.CharField(null=False, max_length=255)
    certainty = models.FloatField(null=False, default=0.0)
