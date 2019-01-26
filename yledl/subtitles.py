# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr


@attr.s
class Subtitle(object):
    url = attr.ib()
    lang = attr.ib()


@attr.s
class EmbeddedSubtitle(object):
    language = attr.ib()
    category = attr.ib()
