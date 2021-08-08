# -*- coding: utf-8 -*-

import re
from datetime import datetime


class TitleFormatter(object):
    def __init__(self, template='${series_separator}${title}: ${episode_separator}${timestamp}'):
        self.template = template
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
            'series_separator': self._series_separator(series_title),
            'title': main_title,
            'episode': self._episode_number(season, episode),
            'episode_separator': self._episode_number_separator(season, episode),
            'timestamp': self._timestamp_string(publish_timestamp),
            'date': self._date_string(publish_timestamp),
            'program_id': program_id,
        }

        return self._substitute(self.tokens, values)

    def is_constant_pattern(self):
        return all(t.is_constant() for t in self.tokens)

    def maybe_missing_separators(self):
        return (len(self.tokens) > 1 and
                not any(isinstance(t, Literal) for t in self.tokens) and
                not "_separator" in self.template)

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

    def _substitute(self, tokens, values):
        res = []
        for token in self.tokens:
            subst = token.substitute(values)
            if subst:
                res.append(subst)

        return ''.join(res)

    def _main_title(self, title, subheading, series_title):
        episode_title = self._remove_genre_prefix(self._remove_repeated_main_title(title))
        ageless_title = self._remove_age_limit(episode_title)

        if series_title and series_title == ageless_title:
            episode_title = ''
        elif series_title:
            series_prefix = re.escape(series_title) + r': *'
            series_prefix_match = re.match(series_prefix, ageless_title, re.IGNORECASE)
            if series_prefix_match:
                episode_title = ageless_title[series_prefix_match.end():]

        if subheading and not episode_title:
            return subheading
        elif subheading and subheading not in episode_title:
            return episode_title + ': ' + subheading
        else:
            return episode_title

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

    def _series_separator(self, series_title):
        if series_title:
            return series_title + ': '
        else:
            return ''

    def _episode_number(self, season, episode):
        if season and episode:
            return 'S%02dE%02d' % (season, episode)
        elif episode:
            return 'E%02d' % (episode)
        else:
            return ''

    def _episode_number_separator(self, season, episode):
        value = self._episode_number(season, episode)
        if value:
            return value + '-'
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

    def is_constant(self):
        return False

    def substitute(self, values):
        key = self.variable_name[2:-1]
        val = values.get(key, self.variable_name)
        return val if val else ''


class Literal(object):
    def __init__(self, text):
        self.text = text

    def is_constant(self):
        return True

    def substitute(self, values):
        return self.text
