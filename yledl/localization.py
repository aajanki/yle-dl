# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals


def localized_text(alternatives, language='fi'):
    if alternatives:
        return alternatives.get(language) or alternatives.get('fi')
    else:
        return None

def fi_or_sv_text(alternatives):
    return localized_text(alternatives, 'fi') or \
        localized_text(alternatives, 'sv')

def fin_or_swe_text(alternatives):
    return localized_text(alternatives, 'fin') or \
        localized_text(alternatives, 'swe')
