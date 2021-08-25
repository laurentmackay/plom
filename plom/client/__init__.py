# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2020 Andrew Rechnitzer
# Copyright (C) 2020-2021 Colin B. Macdonald

"""Plom client and supporting functions."""

__copyright__ = "Copyright (C) 2018-2021 Andrew Rechnitzer, Colin B. Macdonald, et al"
__credits__ = "The Plom Project Developers"
__license__ = "AGPL-3.0-or-later"


from plom import __version__
from .marker import MarkerClient
from .identifier import IDClient
from .chooser import Chooser

# TODO: randoMarker and randoIDer

# what you get from "from plom.client import *"
__all__ = ["MarkerClient", "IDClient", "Chooser"]
