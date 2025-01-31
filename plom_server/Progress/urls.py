# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022-2023 Edith Coates
# Copyright (C) 2022-2023 Brennen Chiu
# Copyright (C) 2023 Andrew Rechnitzer

from django.urls import path

from Progress.views import (
    ScanOverview,
    ScanBundlesView,
    ScanCompleteView,
    ScanIncompleteView,
    ScanDiscardView,
    ScanReassignView,
    PushedImageView,
    PushedImageWrapView,
    ProgressIdentifyHome,
    ProgressMarkHome,
    ProgressMarkStatsView,
    ProgressMarkDetailsView,
    ProgressMarkVersionCompareView,
    ProgressTaskAnnotationFilterView,
    ProgressTaskAnnotationView,
    AnnotationImageWrapView,
    AnnotationImageView,
    OriginalImageWrapView,
    ProgressUserInfoHome,
    IDImageView,
    ClearID,
    IDImageWrapView,
)

urlpatterns = [
    path("scan/overview/", ScanOverview.as_view(), name="progress_scan_overview"),
    path("scan/bundles/", ScanBundlesView.as_view(), name="progress_scan_bundles"),
    path("scan/complete/", ScanCompleteView.as_view(), name="progress_scan_complete"),
    path(
        "scan/incomplete/",
        ScanIncompleteView.as_view(),
        name="progress_scan_incomplete",
    ),
    path(
        "scan/discard/",
        ScanDiscardView.as_view(),
        name="progress_scan_discard",
    ),
    path(
        "scan/reassign/<int:img_pk>",
        ScanReassignView.as_view(),
        name="progress_reassign_discard",
    ),
    path(
        "scan/pushed_img/<int:img_pk>",
        PushedImageView.as_view(),
        name="progress_pushed_img",
    ),
    path(
        "scan/pushed_img_wrap/<int:img_pk>",
        PushedImageWrapView.as_view(),
        name="progress_pushed_img_wrap",
    ),
    path(
        "mark/overview/",
        ProgressMarkHome.as_view(),
        name="progress_mark_home",
    ),
    path(
        "mark/stats/<int:question>/<int:version>",
        ProgressMarkStatsView.as_view(),
        name="progress_mark_stats",
    ),
    path(
        "mark/details/<int:question>/<int:version>",
        ProgressMarkDetailsView.as_view(),
        name="progress_mark_details",
    ),
    path(
        "mark/task_annotation/",
        ProgressTaskAnnotationFilterView.as_view(),
        name="progress_task_annotation_filter",
    ),
    path(
        "mark/task_annotation/<int:question>/<int:version>",
        ProgressTaskAnnotationView.as_view(),
        name="progress_task_annotation",
    ),
    path(
        "mark/task_annotation/annotation_img_wrap/<int:paper>/<int:question>",
        AnnotationImageWrapView.as_view(),
        name="progress_annotation_img_wrap",
    ),
    path(
        "mark/task_annotation/annotation_img/<int:paper>/<int:question>",
        AnnotationImageView.as_view(),
        name="progress_annotation_img",
    ),
    path(
        "mark/task_annotation/original_img_wrap/<int:paper>/<int:question>",
        OriginalImageWrapView.as_view(),
        name="progress_original_img_wrap",
    ),
    path(
        "mark/compare/<int:question>",
        ProgressMarkVersionCompareView.as_view(),
        name="progress_mark_version_compare",
    ),
    path(
        "identify/overview/",
        ProgressIdentifyHome.as_view(),
        name="progress_identify_home",
    ),
    path(
        "identify/overview/id_img/<int:image_pk>",
        IDImageView.as_view(),
        name="ID_img",
    ),
    path(
        "identify/overview/id_img/clear/<int:paper_number>",
        ClearID.as_view(),
        name="clear_ID",
    ),
    path(
        "identify/overview/id_img_wrap/<int:image_pk>",
        IDImageWrapView.as_view(),
        name="ID_img_wrap",
    ),
    path(
        "userinfo/overview/",
        ProgressUserInfoHome.as_view(),
        name="progress_user_info_home",
    ),
]
