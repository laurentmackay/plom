# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 Julian Lapenna

import fitz

from plom.create.demotools import buildDemoSourceFiles
from plom.create.buildDatabaseAndPapers import check_equal_page_count


def test_equal_page_count_true(tmp_path):
    """Checks that the page counts of each source version pdf are equal.

    Arguments:
        tmpdir (dir): The directory holding the source version pdfs.
    """
    # build the source version pdfs in sourceVersions/
    buildDemoSourceFiles(tmp_path)
    assert check_equal_page_count(tmp_path / "sourceVersions")


def test_equal_page_count_false(tmp_path):
    buildDemoSourceFiles(tmp_path)
    # create a new file with a single page
    clone = fitz.open()
    clone.new_page()
    clone.save(tmp_path / "sourceVersions/version3.pdf")
    assert not check_equal_page_count(tmp_path / "sourceVersions")
