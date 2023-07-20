# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 Julian Lapenna

import base64
from io import BytesIO

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from Finish.services import StudentMarkService, TaMarkingService
from Mark.models import MarkingTask
from Mark.services import MarkingTaskService
from Papers.models import Specification


class GraphingDataService:
    """Service for getting data to graph."""

    def __init__(self):
        self.sms = StudentMarkService()
        self.tms = TaMarkingService()
        self.mts = MarkingTaskService()
        self.spec = Specification.load().spec_dict

        student_dict = self.sms.get_all_students_download(
            version_info=True, timing_info=True, warning_info=False
        )
        student_keys = self.sms.get_csv_header(
            self.spec, version_info=True, timing_info=True, warning_info=False
        )
        self.student_df = pd.DataFrame(student_dict, columns=student_keys)

        ta_dict = self.tms.build_csv_data()
        ta_keys = self.tms.get_csv_header()

        self.ta_df = pd.DataFrame(ta_dict, columns=ta_keys)

    def get_graph_as_base64(self, fig: matplotlib.figure.Figure) -> str:
        """ """
        png_bytes = BytesIO()
        fig.savefig(png_bytes, format="png")
        png_bytes.seek(0)
        plt.close()

        return base64.b64encode(png_bytes.read()).decode()

    def get_total_average_mark(self) -> float:
        """Return the average total mark for all students as a float."""
        return self.student_df["total_mark"].mean()

    def get_total_median_mark(self) -> float:
        """Return the median total mark for all students as a float."""
        return self.student_df["total_mark"].median()

    def get_total_stdev_mark(self) -> float:
        """Return the standard deviation of the total marks for all students as a float."""
        return self.student_df["total_mark"].std()

    def get_total_marks(self) -> list:
        """Return the total marks for all students as a list."""
        return self.student_df["total_mark"].tolist()

    def get_marks_by_question(self):
        """Get the marks for each question as a list of lists.

        Returns:
            list: A list of lists containing the marks for each question.
        """
        marks_by_question = []
        for question in self.spec["question"]:
            marks_by_question.append(
                self.student_df[f"q{str(question)}_mark"].to_list()
            )
        return marks_by_question

    def get_question_correlation_heatmap(self) -> pd.DataFrame:
        """Get the correlation heatmap for the questions.

        This returns as a dataframe so that it can keep column and row names.

        Returns:
            pd.DataFrame: A dataframe containing the correlation heatmap.
        """
        marks_corr = (
            self.student_df.filter(regex="q[0-9]*_mark")
            .corr(numeric_only=True)
            .round(2)
        )

        col_names = []
        for i, col_name in enumerate(marks_corr.columns):
            col_names.append("Q" + str(i + 1))

        marks_corr.columns = col_names
        marks_corr.index = col_names
        return marks_corr
