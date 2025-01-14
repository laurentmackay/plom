# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 Andrew Rechnitzer
from django.shortcuts import render
from django.http import FileResponse, HttpResponse

from Base.base_group_views import ManagerRequiredView
from Mark.services import MarkingStatsService, MarkingTaskService, PageDataService
from Papers.services import SpecificationService


class ProgressTaskAnnotationFilterView(ManagerRequiredView):
    def get(self, request):
        mss = MarkingStatsService()

        question = request.GET.get("question", "*")
        version = request.GET.get("version", "*")
        username = request.GET.get("username", "*")

        question_list = [
            str(q + 1) for q in range(SpecificationService.get_n_questions())
        ]
        version_list = [
            str(v + 1) for v in range(SpecificationService.get_n_versions())
        ]

        def optional_arg(val):
            if val == "*":
                return None
            else:
                return val

        task_info = mss.filter_marking_task_annotation_info(
            question=optional_arg(question),
            version=optional_arg(version),
            username=optional_arg(username),
        )

        context = super().build_context()
        context.update(
            {
                "question": question,
                "version": version,
                "username": username,
                "question_list": question_list,
                "version_list": version_list,
                "username_list": mss.get_list_of_users_who_marked_anything(),
                "task_info": task_info,
            }
        )

        return render(request, "Progress/Mark/task_annotations_filter.html", context)


class ProgressTaskAnnotationView(ManagerRequiredView):
    def get(self, request, question, version):
        context = super().build_context()
        context.update(
            {
                "question": question,
                "version": version,
                "task_info": MarkingStatsService().get_marking_task_annotation_info(
                    question, version
                ),
            }
        )

        return render(request, "Progress/Mark/task_annotations.html", context)


class AnnotationImageWrapView(ManagerRequiredView):
    def get(self, request, paper, question):
        annot = MarkingTaskService().get_latest_annotation(paper, question)
        context = {"paper": paper, "question": question, "annotation_pk": annot.pk}
        return render(
            request, "Progress/Mark/annotation_image_wrap_fragment.html", context
        )


class AnnotationImageView(ManagerRequiredView):
    def get(self, request, paper, question):
        annot = MarkingTaskService().get_latest_annotation(paper, question)
        return FileResponse(annot.image.image)


class OriginalImageWrapView(ManagerRequiredView):
    def get(self, request, paper, question):
        img_list = PageDataService().get_question_pages_list(paper, question)
        # update this to include an angle which is (-1)*orientation - for css transforms
        for X in img_list:
            X.update({"angle": -X["orientation"]})

        context = {"paper": paper, "question": question, "img_list": img_list}
        return render(
            request, "Progress/Mark/original_image_wrap_fragment.html", context
        )
