# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals

# Public exit codes
RD_SUCCESS = 0
RD_FAILED = 1
RD_INCOMPLETE = 2

# Internal exit codes
#
# RD_SUBPROCESS_EXECUTE_FAILED: A subprocess threw an OSError, for example,
# because the executable was not found.
RD_SUBPROCESS_EXECUTE_FAILED = 0x1000 | RD_FAILED


def to_external_rd_code(rdcode):
    """Map internal RD codes to the corresponding external ones."""
    if rdcode == RD_SUBPROCESS_EXECUTE_FAILED:
        return RD_FAILED
    else:
        return rdcode
