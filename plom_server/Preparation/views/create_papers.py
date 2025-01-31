# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022-2023 Edith Coates
# Copyright (C) 2023 Colin B. Macdonald

from django.shortcuts import render

from Base.base_group_views import ManagerRequiredView
from Papers.services import SpecificationService, PaperInfoService

from ..services import PQVMappingService, TestPreparedSetting


class PaperCreationView(ManagerRequiredView):
    """Create test-papers in the database."""

    def build_context(self):
        paper_info = PaperInfoService()
        context = super().build_context()
        n_to_produce = PQVMappingService().get_pqv_map_length()
        context.update(
            {
                "is_populated": paper_info.is_paper_database_populated(),
                "n_papers": n_to_produce,
                "n_questions": SpecificationService.get_n_questions(),
                "n_versions": SpecificationService.get_n_versions(),
                "n_pages": SpecificationService.get_n_pages(),
                "is_test_prepared": TestPreparedSetting.is_test_prepared(),
            }
        )
        return context

    def get(self, request):
        context = self.build_context()
        return render(request, "Preparation/test_paper_manage.html", context)
