# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr
from .backends import Backends


@attr.s
class StreamFilters(object):
    """Parameters for deciding which of potentially multiple available stream
    versions to download.
    """
    latest_only = attr.ib(default=False)
    maxbitrate = attr.ib(default=None)
    maxheight = attr.ib(default=None)
    enabled_backends = attr.ib(default=attr.Factory(
        lambda: list(Backends.default_order)
    ))
