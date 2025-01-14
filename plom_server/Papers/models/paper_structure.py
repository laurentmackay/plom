# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 Edith Coates
# Copyright (C) 2023 Andrew Rechnitzer
# Copyright (C) 2023 Colin B. Macdonald
# Copyright (C) 2023 Julian Lapenna

from django.db import models
from polymorphic.models import PolymorphicModel

from .image_bundle import Image


class Paper(models.Model):
    """Table to store papers, each corresponding to one (physical) test-paper.

    The pages of that test-paper
    are divided into pages - see the FixedPage class.
    The Paper object does not contain explicit refs to pages, but rather
    the pages will reference the paper (as is usual in a database).

    paper_number (int): The number of the given test-paper.
    """

    paper_number = models.PositiveIntegerField(null=False, unique=True)

    def __str__(self):
        """Render a row of the Paper table as a string."""
        return f"Paper (paper_number={self.paper_number})"


class MobilePage(models.Model):
    paper = models.ForeignKey(Paper, null=False, on_delete=models.CASCADE)
    image = models.ForeignKey(Image, null=True, on_delete=models.SET_NULL)
    question_number = models.PositiveIntegerField(null=False)
    version = models.PositiveIntegerField(null=False)
    # NOTE  - no ordering.


class FixedPage(PolymorphicModel):
    """Table to store information about the "fixed" pages within a given paper.

    Since every "fixed" page has a definite page-number and version-number,
    these appear here in the base class. However, only certain pages have
    question-numbers, so we use polymorphism to put that information in
    various derived classes.

    IDPage, DNMPage = for the single IDpage and (zero or more) DNMPages, currently always v=1.
    QuestionPage = has question-number and a non-trivial version

    The base class should contain all info common to these
    classes. Searching on this base class allows us to search over all
    pages, while searching on a derived class only searches over those
    page types.

    paper (ref to Paper): the test-paper to which this page image belongs
    image (ref to Image): the image (see note below)
    page_number (int): the position of this page within the test-paper
    version (int): the version of this paper/page as determined by
        the qvmap.

    Note that the image associated to a fixed page is allowed to be
    None.
        * If the image is not-none then this indicates that there is a
        scan of this fixed page in the system.
        * If the image is None then this indicates that an image
        associated with this fixed page has not been pushed.

    Notice also that this contrasts with mobile pages where a mobile
    page *must* have an associated image. This is because the fixed
    pages are used by plom to record structure of papers and so are
    fixed (independent of whether anything is scanned), while the
    mobile pages only exist when an additional page for a given paper
    is scanned and pushed.
    """

    paper = models.ForeignKey(Paper, null=False, on_delete=models.CASCADE)
    image = models.ForeignKey(Image, null=True, on_delete=models.SET_NULL)
    page_number = models.PositiveIntegerField(null=False)
    version = models.PositiveIntegerField(null=False)


class DNMPage(FixedPage):
    """Table to store information about the do-not-mark pages.

    At present all DNM pages have version 1. This may change in the
    future.
    """

    pass


class IDPage(FixedPage):
    """Table to store information about the IDPage of the paper.

    At present the ID page always has version 1. This may change in the
    future.
    """

    pass


class QuestionPage(FixedPage):
    """Table to store information about the pages in Question groups.

    question_number (int): the question that this page belongs to.
    """

    question_number = models.PositiveIntegerField(null=False)
