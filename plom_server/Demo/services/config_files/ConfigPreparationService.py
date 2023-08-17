# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 Edith Coates

"""Handle creating pre-bundle server state from a config file.

Assumes that the config describes a valid server state, and that the
server will be created in order from test specification to building test-papers.
"""

import sys
import csv

if sys.version_info >= (3, 10):
    from importlib import resources
else:
    import importlib_resources as resources

from Papers.services import SpecificationService
from Preparation import useful_files_for_testing as useful_files
from Preparation.services import (
    TestSourceService,
    PrenameSettingService,
    StagingClasslistCSVService,
    StagingStudentService,
    PQVMappingService,
)

from . import PlomServerConfig, PlomConfigCreationError


def create_specification(config: PlomServerConfig):
    """Create a test specification from a config."""
    spec_path = config.test_spec
    if spec_path == "demo":
        spec_src = resources.files(useful_files) / "testing_test_spec.toml"
    try:
        SpecificationService.load_spec_from_toml(spec_src, update_staging=True)
    except Exception as e:
        raise PlomConfigCreationError(e)


def upload_test_sources(config: PlomServerConfig):
    """Upload test sources specified in a config."""
    source_paths = config.test_sources
    if source_paths == "demo":
        version1 = resources.files(useful_files) / "test_version1.pdf"
        version2 = resources.files(useful_files) / "test_version2.pdf"
        source_paths = [version1, version2]
    try:
        for i, path in enumerate(source_paths):
            TestSourceService().store_test_source(i + 1, path)
    except Exception as e:
        raise PlomConfigCreationError(e)


def set_prenaming_setting(config: PlomServerConfig):
    """Set prenaming according to a config."""
    PrenameSettingService().set_prenaming_setting(config.prenaming_enabled)


def upload_classlist(config: PlomServerConfig):
    """Upload classlist specified in a config."""
    classlist_path = config.classlist
    if classlist_path == "demo":
        classlist_path = resources.files(useful_files) / "cl_for_demo.csv"
    try:
        with open(classlist_path, "rb") as classlist_f:
            success, warnings = StagingClasslistCSVService().take_classlist_from_upload(
                classlist_f
            )
        if success:
            StagingStudentService().use_classlist_csv()
        else:
            raise PlomConfigCreationError("Unable to upload classlist.")
    except Exception as e:
        raise PlomConfigCreationError(e)


def create_qv_map(config: PlomServerConfig):
    """Create a QVmap from a config.

    Either generated from a number-to-produce value or a link to a QVmap CSV.
    """
    if config.num_to_produce:
        PQVMappingService().generate_and_set_pqvmap(config.num_to_produce)
    else:
        # TODO: extra validation steps here?
        # TODO: qvmap service should be ab
        try:
            with open(config.qvmap, newline="") as qvmap_file:
                qvmap_rows = csv.DictReader(qvmap_file)
                qvmap = {}
                for row in qvmap_rows:
                    paper_number = row.pop("p", None)
                    qvmap[paper_number] = row
            PQVMappingService().use_pqv_map(qvmap)
        except Exception as e:
            raise PlomConfigCreationError(e)


def create_test_preparation(config: PlomServerConfig, verbose: bool = False):
    """Instantiate models from the test specification to test-papers."""

    def echo(x):
        return print(x) if verbose else None

    echo("Creating specification...")
    create_specification(config)

    echo("Uploading test sources...")
    upload_test_sources(config)

    echo("Setting prenaming and uploading classlist...")
    set_prenaming_setting(config)
    upload_classlist(config)

    echo("Creating question-version map...")
    create_qv_map(config)
