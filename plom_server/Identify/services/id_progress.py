# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 Brennen Chiu
# Copyright (C) 2023 Julian Lapenna
# Copyright (C) 2023 Natalie Balashov
# Copyright (C) 2023 Andrew Rechnitzer

from typing import Dict, Union

from django.db import transaction

from Identify.models import PaperIDTask
from Identify.services import IdentifyTaskService
from Papers.models import IDPage, Image


class IDProgressService:
    """Functions for Identify Progress HTML page."""

    @transaction.atomic
    def get_id_image_object(self, image_pk: int) -> Union[Image, None]:
        """Get the ID page image based on the image's pk value.

        Args:
            image_pk: The primary key of an image.

        Returns:
            The Image object if it exists,
            or None if the Image does not exist.

        Note:
            If the Image does not exist, the function will return None
            instead of raising the ObjectDoesNotExist exception.
        """
        try:
            return Image.objects.get(pk=image_pk)
        except Image.DoesNotExist:
            return None

    @transaction.atomic
    def get_all_id_task_info(self) -> Dict:
        id_info = {}
        # first get all the task info, then get the id page image pk if they exist
        for task in (
            PaperIDTask.objects.exclude(status=PaperIDTask.OUT_OF_DATE)
            .prefetch_related("latest_action", "paper")
            .order_by("paper__paper_number")
        ):
            dat = {"status": task.get_status_display(), "idpageimage_pk": None}

            if task.status == PaperIDTask.COMPLETE:
                dat.update(
                    {
                        "student_id": task.latest_action.student_id,
                        "student_name": task.latest_action.student_name,
                    }
                )
            id_info[task.paper.paper_number] = dat
        # now the id pages
        for idp_obj in IDPage.objects.all().prefetch_related("paper"):
            if idp_obj.image and idp_obj.paper.paper_number in id_info:
                id_info[idp_obj.paper.paper_number]["idpageimage_pk"] = idp_obj.image.pk

        return id_info

    @transaction.atomic
    def get_all_id_task_count(self) -> int:
        return PaperIDTask.objects.exclude(status=PaperIDTask.OUT_OF_DATE).count()

    @transaction.atomic
    def get_completed_id_task_count(self) -> int:
        return PaperIDTask.objects.filter(status=PaperIDTask.COMPLETE).count()

    @transaction.atomic
    def clear_id_from_paper(self, paper_number: int):
        # only clear the id from a paper that has actually been ID'd
        try:
            pidt = PaperIDTask.objects.filter(
                status=PaperIDTask.COMPLETE, paper__paper_number=paper_number
            ).get()
        except PaperIDTask.DoesNotExist:
            raise ValueError(f"Paper {paper_number} does not have a completed id-task")
        # reset the task associated with that paper.
        IdentifyTaskService().create_task(pidt.paper)

    @transaction.atomic
    def clear_id_from_all_identified_papers(self):
        # only clear the id from papers that have actually been id'd
        for task in PaperIDTask.objects.filter(
            status=PaperIDTask.COMPLETE
        ).prefetch_related("paper"):
            IdentifyTaskService().create_task(task.paper)
