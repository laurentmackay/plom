# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 Edith Coates

from django.db import models


class AnnotationImage(models.Model):
    """
    A raster representation of an annotated question.
    """

    path = models.TextField(null=False, default="")
    hash = models.TextField(null=False, default="")


class Annotation(models.Model):
    """
    Represents a marker's annotation of a particular test paper's question.
    """

    edition = models.IntegerField(null=True)
    score = models.IntegerField(null=True)
    image = models.OneToOneField(AnnotationImage, on_delete=models.CASCADE)
    annotation_data = models.JSONField(null=True)