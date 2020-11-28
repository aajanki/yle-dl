# -*- coding: utf-8 -*-

import attr


@attr.s
class Subtitle(object):
    url = attr.ib()
    lang = attr.ib()
    category = attr.ib()


@attr.s
class EmbeddedSubtitle(object):
    language = attr.ib()
    category = attr.ib()
