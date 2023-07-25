# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 Divy Patel

import os
import numpy as np
from PIL import Image
from pathlib import Path
from sklearn.cluster import KMeans

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from Tags.services import TagService


class Command(BaseCommand):
    """Command tool for clustering and tagging questions.

    Currently only does clustering on student id digits and tags the first question.

    python3 manage.py cluster_and_tag
    """

    help = """Add a tag to a specific paper."""

    def get_digits_and_cluster(self, digit_index) -> list[list[list[np.ndarray, int]]]:
        """Get all the digits from the database and cluster them.

        Returns:
            list: List of all the clusters, each of which is a list of paper_nums
        """
        images = []
        labels = []

        filepath = Path(settings.MEDIA_ROOT / "debug_id_reader")

        for filename in filepath.iterdir():
            if filename.is_file() and filename.suffix.lower() == ".png":
                # get the digit pos index from the filename
                pos_index = filename.name.find("pos")
                if pos_index != -1 and filename.name[pos_index + 3] == str(digit_index):
                    image = np.array(Image.open(filename))
                    image = image.flatten()
                    if image.shape[0] == 784:
                        images.append(image)
                        labels.append(filename)

        kmeans = KMeans(n_clusters=10, random_state=0)
        images_np = np.array(images)
        kmeans.fit(images_np)

        clustered_papers = []
        for label in range(10):
            curr_papers = []
            for i in range(len(images)):
                if kmeans.labels_[i] == label:
                    # Get the paper number from the filename
                    paper_num_pos = labels[i].name.find("box_") + 4
                    paper_num = int(labels[i].name[paper_num_pos : paper_num_pos + 4])
                    curr_papers.append(paper_num)
            clustered_papers.append(curr_papers)

        return clustered_papers

    def tag_question(self):
        """Tag the first question."""
        pass

    def add_arguments(self, parser):
        parser.add_argument(
            "digit_index", type=int, help="Digit index to cluster on, range: [0-7]"
        )

    def handle(self, *args, **options):
        paper_clusters = self.get_digits_and_cluster(options["digit_index"])
