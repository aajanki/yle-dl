# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals


default_languages = ['fin', 'swe']


class TranslationChooser(object):
    def __init__(self, preferred_three_letter_codes):
        if preferred_three_letter_codes:
            preferred = [x.lower() for x in preferred_three_letter_codes]
            self.languages = preferred + \
                [x for x in default_languages if x not in preferred]
        else:
            self.languages = list(default_languages)

    def choose_long_form(self, alternatives):
        return self._choose(alternatives, self.languages)

    def choose_short_form(self, alternatives):
        return self._choose(alternatives, self.two_letter_codes(self.languages))

    def _choose(self, alternatives, language_codes):
        if alternatives is None:
            return None

        for lang in language_codes:
            text = alternatives.get(lang)
            if text is not None:
                return text

        if alternatives:
            # An arbitrary language if none of the preferred languages
            # are available
            return list(alternatives.values())[0]
        else:
            return None

    def two_letter_codes(self, long_codes):
        code_map = {'fin': 'fi', 'swe': 'sv', 'sme': 'se'}
        return [code_map.get(x, x) for x in long_codes]
