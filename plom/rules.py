# -*- coding: utf-8 -*-

"""Utils concerning rules about data, like valid student numbers."""

__author__ = "Colin B. Macdonald"
__copyright__ = "Copyright (C) 2020 Colin B. Macdonald"
__license__ = "AGPL-3.0-or-later"
# SPDX-License-Identifier: AGPL-3.0-or-later


def isValidUBCStudentNumber(n):
    """Is this a valid student number for UBC?

    Input must be a string or string like or convertable by str().
    """
    try:
        sid = int(str(n))
    except:
        return False
    if sid < 0:
        return False
    if len(str(n)) != 8:
        return False
    return True


def censorStudentNumber(n):
    """Replace some parts of student number with astericks."""
    n = str(n)
    r = n[:2] + "****" + n[-2:]
    assert len(n) == len(r)
    return r


def censorStudentName(s):
    """Replace most of a student student name with astericks."""
    if len(s) <= 3:
        r = s[0] + "*" * 7
    else:
        r = s[:3] + "*" * 5
    return r


isValidStudentNumber = isValidUBCStudentNumber
