# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 Divy Patel

import numpy as np
from PIL import Image
from pathlib import Path
from sklearn.cluster import KMeans

from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from Identify.services import IDReaderService
from Identify.management.commands.plom_id import Command as PlomIDCommand
from Tags.services import TagService
from Mark.services import MarkingTaskService


class Command(BaseCommand):
    """Command tool for clustering and tagging questions.

    Currently only does clustering on student id digits and tags the first question.

    python3 manage.py cluster_and_tag
    """

    help = """Add a tag to a specific paper."""

    def get_digits_and_cluster(self, digit_index) -> list[list[int]]:
        """Get all the digits from the database and cluster them.

        Returns:
            list: List of all the clusters, each of which is a list of paper_nums
        """
        images = []
        labels = []

        idservice = IDReaderService()
        plom_id_command = PlomIDCommand()
        student_number_length = 8
        id_box_files = idservice.get_id_box_cmd((0.1, 0.9, 0.0, 1.0))

        for paper_num, id_box_file in id_box_files.items():
            id_page_file = Path(id_box_file)
            ID_box = plom_id_command.extract_and_resize_ID_box(id_page_file)
            if ID_box is None:
                self.stdout.write("Trouble finding the ID box")
                continue
            digit_images = plom_id_command.get_digit_images(
                ID_box, student_number_length
            )
            if len(digit_images) == 0:
                self.stdout.write("Trouble finding digits inside the ID box")
                continue
            for digit_image in digit_images:
                image = np.array(digit_image)
                image = image.flatten()
                if image.shape[0] == 784:
                    images.append(image)
                    labels.append(paper_num)

        kmeans = KMeans(n_clusters=10, random_state=0)
        images_np = np.array(images)
        kmeans.fit(images_np)

        clustered_papers = []
        for label in range(10):
            curr_papers = []
            for i in range(len(images)):
                if kmeans.labels_[i] == label:
                    # Get the paper number from the filename
                    paper_num = labels[i]
                    curr_papers.append(paper_num)
            clustered_papers.append(curr_papers)

        return clustered_papers

    def tag_question(self, clusters) -> None:
        """Tag the first question."""
        ms = MarkingTaskService()
        if not User.objects.filter(username="id_digit_tagging_temp_user").exists():
            user = User(username="id_digit_tagging_temp_user", password="")
            user.save()
        else:
            user = User.objects.get(username="id_digit_tagging_temp_user")
        for i in range(len(clusters)):
            if len(clusters[i]) > 0:
                for paper_num in clusters[i]:
                    code = f"q{paper_num}g1"
                    text = f"cluster_{i}"
                    try:
                        ms.add_tag_text_from_task_code(text, code, user)
                    except RuntimeError:
                        print(f"{code} does not exist")

    def add_arguments(self, parser):
        parser.add_argument(
            "digit_index", type=int, help="Digit index to cluster on, range: [0-7]"
        )

    def handle(self, *args, **options):
        paper_clusters = self.get_digits_and_cluster(options["digit_index"])
        self.tag_question(paper_clusters)
