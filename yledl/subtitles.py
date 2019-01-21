# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr


@attr.s
class EmbeddedSubtitle(object):
    language = attr.ib()
