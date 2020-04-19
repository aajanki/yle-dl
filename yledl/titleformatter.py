# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import re
from datetime import datetime
from collections import defaultdict


class TitleFormatter(object):
    def __init__(self, template='${series}${title}${episode}${timestamp}'):
        self.tokens = self._parse_template(template)

    def format(self, title, publish_timestamp=None, series_title=None,
               subheading=None, season=None, episode=None, program_id=None):
        if title is None:
            return None

        title = title.strip()
        series_title = \
            series_title.strip() if series_title is not None else None
        subheading = subheading.strip() if subheading is not None else None

        main_title = self._main_title(title, subheading, series_title)
        if not main_title and series_title:
            main_title = series_title
            series_title = None

        values = {
            'series': series_title or '',
            'title': main_title,
            'episode': self._episode_number(season, episode),
            'timestamp': self._timestamp_string(publish_timestamp),
            'date': self._date_string(publish_timestamp),
            'program_id': program_id,
        }
        separators = defaultdict(lambda: ': ',
                                 timestamp='-',
                                 date='-',
                                 program_id='-')

        return self._substitute(self.tokens, values, separators)

    def _parse_template(self, template):
        res = []

        last_pos = 0
        for m in re.finditer(r'\$(:?{[a-zA-Z_]+?}|\$)', template):
            if m.start() != last_pos:
                res.append(Literal(template[last_pos:m.start()]))

            if m.group() == '$$':
                res.append(Literal('$'))
            else:
                var_name = m.group()
                res.append(Substitution(var_name))

            last_pos = m.end()

        if last_pos != len(template):
            res.append(Literal(template[last_pos:]))

        return res

    def _substitute(self, tokens, values, separators):
        res = []
        empty_separator = defaultdict(lambda: '')
        for token in self.tokens:
            sep = empty_separator if len(res) == 0 else separators
            subst = token.substitute(values, sep)
            if subst:
                res.append(subst)

        return ''.join(res)

    def _main_title(self, title, subheading, series_title):
        main_title = self._remove_genre_prefix(
            self._remove_repeated_main_title(title))
        ageless_title = self._remove_age_limit(main_title)

        if series_title:
            series_prefix = re.escape(series_title) + r'\b'
            if re.match(series_prefix, ageless_title, re.IGNORECASE):
                main_title = ageless_title[len(series_title):]
                main_title = main_title.lstrip(':').lstrip(' ')

        if subheading and not main_title:
            return subheading
        if subheading and subheading not in main_title:
            return main_title + ': ' + subheading
        else:
            return main_title

    def _remove_age_limit(self, title):
        """Strip (S) or (12) postfix from the title."""
        m = re.match(r'(.+?)\s+\(([A-Z]|[0-9]{1,2})\)$', title)
        return m.group(1) if m else title

    def _remove_repeated_main_title(self, title):
        if ':' in title:
            prefix, rest = title.split(':', 1)
            if prefix in rest:
                return rest.strip()

        return title

    def _remove_genre_prefix(self, title):
        genre_prefixes = ['Elokuva:', 'Kino:', 'Kino Klassikko:',
                          'Kino Suomi:', 'Kotikatsomo:', 'Uusi Kino:', 'Dok:',
                          'Dokumenttiprojekti:', 'Historia:']
        for prefix in genre_prefixes:
            if title.startswith(prefix):
                return title[len(prefix):].strip()
        return title

    def _episode_number(self, season, episode):
        if season and episode:
            return 'S%02dE%02d' % (season, episode)
        elif episode:
            return 'E%02d' % (episode)
        else:
            return ''

    def _timestamp_string(self, publish_timestamp):
        if publish_timestamp and hasattr(publish_timestamp, 'hour'):
            return datetime.strftime(publish_timestamp, '%Y-%m-%dT%H:%M')
        elif publish_timestamp:
            return self._date_string(publish_timestamp)
        else:
            return ''

    def _date_string(self, publish_timestamp):
        if publish_timestamp:
            return publish_timestamp.strftime('%Y-%m-%d')
        else:
            return ''


class Substitution(object):
    def __init__(self, variable_name):
        self.variable_name = variable_name

    def substitute(self, values, separators):
        key = self.variable_name[2:-1]
        val = values.get(key, self.variable_name)
        return separators[key] + val if val else ''


class Literal(object):
    def __init__(self, text):
        self.text = text

    def substitute(self, values, separators):
        return self.text
