# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 Andrew Rechnitzer
# Copyright (C) 2023 Colin B. Macdonald

from typing import Union

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from Papers.models import (
    Paper,
    FixedPage,
    MobilePage,
    IDPage,
    DNMPage,
    QuestionPage,
    DiscardPage,
    Image,
)
from Identify.services import IdentifyTaskService
from Mark.services import MarkingTaskService


class ManageDiscardService:
    """Functions for overseeing discarding pushed images."""

    @transaction.atomic
    def _discard_dnm_page(self, user_obj: User, dnm_obj: DNMPage) -> None:
        DiscardPage.objects.create(
            image=dnm_obj.image,
            discard_reason=(
                f"User {user_obj.username} discarded DNM page: "
                f"page {dnm_obj.paper.paper_number} page {dnm_obj.page_number}"
            ),
        )
        # Set the original dnm page to have no image, but **DO NOT** delete the DNM page
        dnm_obj.image = None
        dnm_obj.save()
        # Notice that no tasks need be invalidated since this is a DNM page.

    @transaction.atomic
    def _discard_id_page(self, user_obj: User, idpage_obj: IDPage) -> None:
        DiscardPage.objects.create(
            image=idpage_obj.image,
            discard_reason=(
                f"User {user_obj.username} discarded ID page: "
                f"page {idpage_obj.paper.paper_number} page {idpage_obj.page_number}"
            ),
        )
        # Set the original id page to have no image, but **DO NOT** delete the idpage
        idpage_obj.image = None
        idpage_obj.save()

        # now set the associated id-task to out of date.
        IdentifyTaskService().set_paper_idtask_outdated(idpage_obj.paper.paper_number)
        # notice that since there is only a single ID page we cannot
        # automatically create a new id-task, we need a new page to be uploaded.

    @transaction.atomic
    def _discard_question_page(self, user_obj: User, qpage_obj: QuestionPage) -> None:
        DiscardPage.objects.create(
            image=qpage_obj.image,
            discard_reason=(
                f"User {user_obj.username} discarded paper "
                f"{qpage_obj.paper.paper_number} page {qpage_obj.page_number} "
                f"question {qpage_obj.question_number}."
            ),
        )
        # Set the original question page to have no image, but **DO NOT** delete the question page
        qpage_obj.image = None
        qpage_obj.save()

        # set the associated Markinging task to "OUT_OF_DATE"
        # this also tries to make a new task if possible
        MarkingTaskService().set_paper_marking_task_outdated(
            qpage_obj.paper.paper_number, qpage_obj.question_number
        )

    @transaction.atomic
    def _discard_mobile_page(self, user_obj: User, mpage_obj: MobilePage) -> None:
        # note that a single mobile page is attached to an image that
        # might be associated with multiple questions. Accordingly
        # when we discard this mobile-page we also discard any other
        # mobile pages associated with this image **and** also flag
        # the marking tasks associated with those mobile pages as 'out
        # of date'

        img_to_disc = mpage_obj.image
        paper_number = mpage_obj.paper.paper_number

        DiscardPage.objects.create(
            image=img_to_disc,
            discard_reason=(
                f"User {user_obj.username} discarded mobile "
                f"paper {paper_number} "
                f"question {mpage_obj.question_number}."
            ),
        )

        # find all the mobile pages associated with this image
        # set the associated marking tasks to "OUT_OF_DATE"
        qn_to_outdate = [
            mpg.question_number for mpg in img_to_disc.mobilepage_set.all()
        ]
        # and now delete each of those mobile pages
        for mpg in img_to_disc.mobilepage_set.all():
            mpg.delete()
        # outdate the associated marking tasks
        # this also makes new marking tasks if possible
        for qn in qn_to_outdate:
            MarkingTaskService().set_paper_marking_task_outdated(paper_number, qn)

    def discard_pushed_fixed_page(
        self, user_obj: User, fixedpage_pk: int, *, dry_run: bool = True
    ) -> str:
        """Discard a fixed page, such an ID page, DNM page or Question page.

        Args:
            user_obj (User): the User who is discarding
            fixedpage_pk (int): the pk of the fixed page to be discarded

        Keyword Args:
            dry_run: really do it or just pretend?

        Returns:
            A status message about what happened (or, if ``dry_run`` is True,
            what would be attempted).

        Raises:
            ValueError: no such page, no image attached to page, unexpectedly
                unknown page type, maybe other cases.
        """
        try:
            fp_obj = FixedPage.objects.get(pk=fixedpage_pk)
        except ObjectDoesNotExist as e:
            raise ValueError(
                f"A fixed page with pk {fixedpage_pk} does not exist"
            ) from e

        if fp_obj.image is None:
            raise ValueError(
                f"There is no image attached to fixed page {fixedpage_pk} "
                f"(which is paper {fp_obj.paper.paper_number} page {fp_obj.page_number})"
            )

        if isinstance(fp_obj, DNMPage):
            msg = f"DNMPage paper {fp_obj.paper.paper_number} page {fp_obj.page_number}"
            if dry_run:
                return "DRY-RUN: would drop " + msg
            self._discard_dnm_page(user_obj, fp_obj)
            return "Have dropped " + msg
        elif isinstance(fp_obj, IDPage):
            msg = f"IDPage paper {fp_obj.paper.paper_number} page {fp_obj.page_number}"
            if dry_run:
                return f"DRY-RUN: would drop {msg}"
            self._discard_id_page(user_obj, fp_obj)
            return (
                f"Have dropped {msg} and "
                "flagged the associated ID-task as 'out of date'"
            )
        elif isinstance(fp_obj, QuestionPage):
            msg = f"QuestionPage for paper {fp_obj.paper.paper_number} "
            f"page {fp_obj.page_number} question {fp_obj.question_number}"
            if dry_run:
                return f"DRY-RUN: would drop {msg}"
            self._discard_question_page(user_obj, fp_obj)
            return (
                f"Have dropped {msg} and "
                "flagged the associated marking task as 'out of date'"
            )
        else:
            raise ValueError("Cannot determine what sort of fixed-page this is")

    def discard_pushed_mobile_page(
        self, user_obj: User, mobilepage_pk: int, *, dry_run: bool = True
    ) -> str:
        """Discard a mobile page.

        Args:
            user_obj (User): the User who is discarding
            mobilepage_pk (int): the pk of the mobile page to be discarded

        Keyword Args:
            dry_run: really do it or just pretend?

        Returns:
            A status message about what happened (or, if ``dry_run`` is True,
            what would be attempted).

        Raises:
            ValueError: no such page, no image attached to page, unexpectedly
                unknown page type, maybe other cases.
        """
        try:
            mp_obj = MobilePage.objects.get(pk=mobilepage_pk)
        except ObjectDoesNotExist as e:
            raise ValueError(
                f"A mobile page with pk {mobilepage_pk} does not exist"
            ) from e

        msg = (
            f"a MobilePage for paper {mp_obj.paper.paper_number} "
            f"question {mp_obj.question_number}"
        )
        if dry_run:
            return f"DRY-RUN: would drop {msg}"
        self._discard_mobile_page(user_obj, mp_obj)
        return (
            f"Have dropped {msg} and "
            "flagged the associated marking task as 'out of date'"
        )

    def discard_pushed_image_from_pk(self, user_obj: User, image_pk: int):
        """Given pk of a pushed image, discard it."""
        try:
            image_obj = Image.objects.get(pk=image_pk)
        except ObjectDoesNotExist as e:
            raise ValueError(f"An image with pk {image_pk} does not exist.") from e
        # is either a fixed page, mobile page or discard page
        if image_obj.fixedpage_set.exists():
            self.discard_pushed_fixed_page(
                user_obj, image_obj.fixedpage_set.first().pk, dry_run=False
            )
        elif image_obj.mobilepage_set.exists():
            # notice that this will discard all mobile pages with that image.
            self.discard_pushed_mobile_page(
                user_obj, image_obj.mobilepage_set.first().pk, dry_run=False
            )
        else:
            # is already a discard page, so nothing to do.
            pass

    def discard_pushed_page_cmd(
        self,
        username: str,
        *,
        fixedpage_pk: Union[int, None] = None,
        mobilepage_pk: Union[int, None] = None,
        dry_run: bool = True,
    ) -> str:
        try:
            user_obj = User.objects.get(
                username__iexact=username, groups__name="manager"
            )
        except ObjectDoesNotExist as e:
            raise ValueError(
                f"User '{username}' does not exist or has wrong permissions."
            ) from e

        if fixedpage_pk and mobilepage_pk:
            raise ValueError("You cannot specify both fixedpage AND mobilepage")
        elif fixedpage_pk:
            return self.discard_pushed_fixed_page(
                user_obj, fixedpage_pk, dry_run=dry_run
            )
        elif mobilepage_pk:
            return self.discard_pushed_mobile_page(
                user_obj, mobilepage_pk, dry_run=dry_run
            )
        else:
            raise ValueError("Command needs a pk for a fixedpage or mobilepage")

    @transaction.atomic
    def _assign_discard_to_fixed_page(
        self, user_obj: User, discard_pk: int, paper_number: int, page_number: int
    ):
        try:
            discard_obj = DiscardPage.objects.get(pk=discard_pk)
        except ObjectDoesNotExist:
            raise ValueError(f"Cannot find a discard page with pk = {discard_pk}")

        try:
            paper_obj = Paper.objects.get(paper_number=paper_number)
        except ObjectDoesNotExist:
            raise ValueError(f"Cannot find a paper with number = {paper_number}")

        try:
            fpage_obj = FixedPage.objects.get(paper=paper_obj, page_number=page_number)
        except ObjectDoesNotExist:
            raise ValueError(
                f"Paper {paper_number} does not have a fixed page with page number {page_number}"
            )

        if fpage_obj.image:
            raise ValueError(
                f"Fixed page {page_number} of paper {paper_number} already has an image."
            )

        # assign the image to the fixed page
        fpage_obj.image = discard_obj.image
        fpage_obj.save()
        # delete the discard page
        discard_obj.delete()

        if isinstance(fpage_obj, DNMPage):
            pass
        elif isinstance(fpage_obj, IDPage):
            IdentifyTaskService().set_paper_idtask_outdated(paper_number)
        elif isinstance(fpage_obj, QuestionPage):
            MarkingTaskService().set_paper_marking_task_outdated(
                paper_number, fpage_obj.question_number
            )
        else:
            raise RuntimeError(
                f"Cannot identify the type of the fixed page with pk = {fpage_obj.pk} in paper {paper_number} page {page_number}."
            )

    @transaction.atomic
    def _assign_discard_to_mobile_page(
        self,
        user_obj: User,
        discard_pk: int,
        paper_number: int,
        question_list: list[int],
    ):
        try:
            discard_obj = DiscardPage.objects.get(pk=discard_pk)
        except ObjectDoesNotExist:
            raise ValueError(f"Cannot find a discard page with pk = {discard_pk}")

        try:
            paper_obj = Paper.objects.get(paper_number=paper_number)
        except ObjectDoesNotExist:
            raise ValueError(f"Cannot find a paper with number = {paper_number}")

        for qn in question_list:
            # get the version from an associated question-page
            version = (
                QuestionPage.objects.filter(paper=paper_obj, question_number=qn)
                .first()
                .version
            )
            MobilePage.objects.create(
                paper=paper_obj,
                question_number=qn,
                image=discard_obj.image,
                version=version,
            )

        # delete the discard page
        discard_obj.delete()
        # reset the associated marking tasks
        for qn in question_list:
            MarkingTaskService().set_paper_marking_task_outdated(paper_number, qn)

    def assign_discard_image_to_fixed_page(
        self, user_obj: User, image_pk: int, paper_number: int, page_number: int
    ):
        try:
            image_obj = Image.objects.get(pk=image_pk)
        except ObjectDoesNotExist:
            raise ValueError("Cannot find image with pk = {image_pk}")
        try:
            self._assign_discard_to_fixed_page(
                user_obj, image_obj.discardpage.pk, paper_number, page_number
            )
        except DiscardPage.DoesNotExist:
            raise ValueError(
                f"Cannot discard image with pk {image_pk}. It is not attached to a discard page."
            )

    def assign_discard_image_to_mobile_page(
        self, user_obj: User, image_pk: int, paper_number: int, question_list: list[int]
    ):
        try:
            image_obj = Image.objects.get(pk=image_pk)
        except ObjectDoesNotExist:
            raise ValueError("Cannot find image with pk = {image_pk}")
        try:
            self._assign_discard_to_mobile_page(
                user_obj, image_obj.discardpage.pk, paper_number, question_list
            )
        except DiscardPage.DoesNotExist:
            raise ValueError(
                "Cannot reassign image with pk {image_pk}. It is not attached to a discard page."
            )

    def reassign_discard_page_to_fixed_page_cmd(
        self, username: str, discard_pk: int, paper_number: int, page_number: int
    ):
        try:
            user_obj = User.objects.get(
                username__iexact=username, groups__name="manager"
            )
        except ObjectDoesNotExist as e:
            raise ValueError(
                f"User '{username}' does not exist or has wrong permissions."
            ) from e

        self._assign_discard_to_fixed_page(
            user_obj, discard_pk, paper_number, page_number
        )

    def reassign_discard_page_to_mobile_page_cmd(
        self,
        username: str,
        discard_pk: int,
        paper_number: int,
        question_list: list[int],
    ):
        try:
            user_obj = User.objects.get(
                username__iexact=username, groups__name="manager"
            )
        except ObjectDoesNotExist as e:
            raise ValueError(
                f"User '{username}' does not exist or has wrong permissions."
            ) from e

        self._assign_discard_to_mobile_page(
            user_obj, discard_pk, paper_number, question_list
        )
