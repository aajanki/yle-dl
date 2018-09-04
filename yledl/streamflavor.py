# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr
from .backends import FailingBackend

@attr.s
class StreamFlavor(object):
    media_type = attr.ib()
    height = attr.ib(default=None, converter=attr.converters.optional(int))
    width = attr.ib(default=None, converter=attr.converters.optional(int))
    bitrate = attr.ib(default=None, converter=attr.converters.optional(int))
    streams = attr.ib(factory=list)
    hard_subtitle = attr.ib(default=None)


class FailedFlavor(StreamFlavor):
    def __init__(self, error_message):
        StreamFlavor.__init__(self,
                              media_type='unknown',
                              height=None,
                              width=None,
                              bitrate=None,
                              streams=[FailingBackend(error_message)])
