# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr
from .backends import Backends


def normalize_language_code(lang, subtype):
    if lang == 'all' or lang == 'none':
        return lang
    elif subtype == 'hearingimpaired':
        return lang + 'h'
    else:
        language_map = {'fi': 'fin', 'sv': 'swe'}
        return language_map.get(lang, lang)


@attr.s
class StreamFilters(object):
    """Parameters for deciding which of potentially multiple available stream
    versions to download.
    """
    latest_only = attr.ib(default=False)
    audiolang = attr.ib(default='')
    sublang = attr.ib(default='all')
    hardsubs = attr.ib(default=False)
    maxbitrate = attr.ib(default=None)
    maxheight = attr.ib(default=None)
    enabled_backends = attr.ib(default=attr.Factory(
        lambda: list(Backends.default_order)
    ))

    def sublang_matches(self, langcode, subtype):
        return self._lang_matches(self.sublang, langcode, subtype)

    def audiolang_matches(self, langcode):
        return self.audiolang != '' and \
            self._lang_matches(self.audiolang, langcode, '')

    def _lang_matches(self, langA, langB, subtype):
        return normalize_language_code(langA, '') == \
          normalize_language_code(langB, subtype)
