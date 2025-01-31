# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 Brennen Chiu
# Copyright (C) 2023 Andrew Rechnitzer

from django.shortcuts import render
from django.http import FileResponse
from django_htmx.http import HttpResponseClientRefresh

from Base.base_group_views import ManagerRequiredView

from Identify.services import IDProgressService


class ProgressIdentifyHome(ManagerRequiredView):
    def get(self, request):
        context = super().build_context()

        ids = IDProgressService()

        n_all_id_task = ids.get_all_id_task_count()
        n_complete_task = ids.get_completed_id_task_count()
        if n_all_id_task:
            percent_complete = round(n_complete_task / n_all_id_task * 100)
        else:
            percent_complete = 0

        context.update(
            {
                "id_task_info": ids.get_all_id_task_info(),
                "all_task_count": n_all_id_task,
                "completed_task_count": n_complete_task,
                "percent_complete": percent_complete,
            }
        )

        return render(request, "Progress/Identify/identify_home.html", context)


class IDImageWrapView(ManagerRequiredView):
    def get(self, request, image_pk):
        id_img = IDProgressService().get_id_image_object(image_pk=image_pk)
        # pass -angle to template since css uses clockwise not anti-clockwise.
        context = {"image_pk": image_pk, "angle": -id_img.rotation}
        return render(request, "Progress/Identify/id_image_wrap_fragment.html", context)


class IDImageView(ManagerRequiredView):
    def get(self, request, image_pk):
        id_img = IDProgressService().get_id_image_object(image_pk=image_pk)
        return FileResponse(id_img.image_file)


class ClearID(ManagerRequiredView):
    def delete(self, request, paper_number):
        IDProgressService().clear_id_from_paper(paper_number)
        return HttpResponseClientRefresh()
