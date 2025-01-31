# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022-2023 Edith Coates
# Copyright (C) 2022 Brennen Chiu
# Copyright (C) 2023 Colin B. Macdonald


from django.db import models

from Base.models import HueyTask
from Papers.models import Paper


class ReassembleTask(HueyTask):
    paper = models.OneToOneField(Paper, null=False, on_delete=models.CASCADE)
    pdf_file = models.FileField(upload_to="reassemble/", null=True)

    def __str__(self):
        """Stringify task using its related test-paper's number."""
        return "Task Object " + str(self.paper.paper_number)
