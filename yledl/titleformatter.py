# This file is part of yle-dl.
#
# Copyright 2010-2026 Antti Ajanki and others
#
# Yle-dl is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Yle-dl is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with yle-dl. If not, see <https://www.gnu.org/licenses/>.

import re
from datetime import datetime
from typing import List, Mapping, Union


class TitleFormatter:
    def __init__(
        self,
        template: str = '${series_separator}${title}: ${episode_separator}${timestamp}',
        placeholder: str | None = None,
    ):
        self.template = template
        self.tokens = self._parse_template(template)
        self.placeholder = placeholder

    def format(
        self,
        title: str | None,
        publish_timestamp: datetime | None = None,
        series_title: str | None = None,
        subheading: str | None = None,
        season: int | None = None,
        episode: int | None = None,
        program_id: str | None = None,
    ) -> str | None:
        if title is None:
            return None

        title = title.strip()
        series_title = series_title.strip() if series_title is not None else None
        subheading = subheading.strip() if subheading is not None else None

        main_title = self._main_title(title, subheading, series_title)
        if not main_title and series_title:
            main_title = series_title
            series_title = None
        series_title = series_title or self.placeholder

        episode_number = self._episode_number(season, episode) or self.placeholder

        values = {
            'series': series_title or '',
            'series_separator': self._concatenate_if_not_empty(series_title, ': '),
            'title': main_title or self.placeholder,
            'season': self._season(season),
            'episode': episode_number,
            'episode_separator': self._concatenate_if_not_empty(episode_number, '-'),
            'timestamp': self._timestamp_string(publish_timestamp) or self.placeholder,
            'date': self._date_string(publish_timestamp) or self.placeholder,
            'episode_or_date': (
                episode_number
                or self._date_string(publish_timestamp)
                or self.placeholder
            ),
            'program_id': program_id or self.placeholder,
        }

        return self._substitute(values)

    def is_constant_pattern(self):
        return all(t.is_constant() for t in self.tokens)

    def maybe_missing_separators(self):
        return (
            len(self.tokens) > 1
            and not any(isinstance(t, Literal) for t in self.tokens)
            and '_separator' not in self.template
        )

    def _parse_template(self, template: str) -> List[Union['Literal', 'Substitution']]:
        res: List[Union['Literal', 'Substitution']] = []

        last_pos = 0
        for m in re.finditer(r'\$(:?{[a-zA-Z_]+?}|\$)', template):
            if m.start() != last_pos:
                res.append(Literal(template[last_pos : m.start()]))

            if m.group() == '$$':
                res.append(Literal('$'))
            else:
                var_name = m.group()
                res.append(Substitution(var_name))

            last_pos = m.end()

        if last_pos != len(template):
            res.append(Literal(template[last_pos:]))

        return res

    def _substitute(self, values: Mapping[str, str | None]) -> str:
        res = []
        for token in self.tokens:
            subst = token.substitute(values)
            if subst:
                res.append(subst)

        return ''.join(res).lstrip('/')

    def _main_title(
        self, title: str, subheading: str | None, series_title: str | None
    ) -> str:
        episode_title = self._remove_genre_prefix(
            self._remove_repeated_main_title(title)
        )
        ageless_title = self._remove_age_limit(episode_title)

        if series_title and series_title == ageless_title:
            episode_title = ''
        elif series_title:
            series_prefix = f'{re.escape(series_title)}: *'
            series_prefix_match = re.match(series_prefix, ageless_title, re.IGNORECASE)
            if series_prefix_match:
                episode_title = ageless_title[series_prefix_match.end() :]

        if subheading and not episode_title:
            return subheading
        elif subheading and subheading not in episode_title:
            return f'{episode_title}: {subheading}'
        else:
            return episode_title

    def _remove_age_limit(self, title: str) -> str:
        """Strip (S) or (12) postfix from the title."""
        m = re.match(r'(.+?)\s+\(([A-Z]|[0-9]{1,2})\)$', title)
        return m.group(1) if m else title

    def _remove_repeated_main_title(self, title: str) -> str:
        if ':' in title:
            prefix, rest = title.split(':', 1)
            if prefix in rest:
                return rest.strip()

        return title

    def _remove_genre_prefix(self, title: str) -> str:
        genre_prefixes = [
            'Elokuva:',
            'Kino:',
            'Kino Klassikko:',
            'Kino Suomi:',
            'Kotikatsomo:',
            'Uusi Kino:',
            'Dok:',
            'Dokumenttiprojekti:',
            'Historia:',
        ]
        for prefix in genre_prefixes:
            if title.startswith(prefix):
                return title[len(prefix) :].strip()
        return title

    def _concatenate_if_not_empty(self, first: str | None, second: str) -> str | None:
        if first:
            return first + second
        else:
            return first

    def _season(self, season: int | None) -> str:
        if season:
            return f'Season {season:02d}'
        else:
            return ''

    def _episode_number(self, season: int | None, episode: int | None) -> str:
        if season and episode:
            return f'S{season:02d}E{episode:02d}'
        elif episode:
            return f'E{episode:02d}'
        else:
            return ''

    def _timestamp_string(self, publish_timestamp: datetime | None) -> str:
        if publish_timestamp and hasattr(publish_timestamp, 'hour'):
            return datetime.strftime(publish_timestamp, '%Y-%m-%dT%H:%M')
        elif publish_timestamp:
            return self._date_string(publish_timestamp)
        else:
            return ''

    def _date_string(self, publish_timestamp: datetime | None) -> str:
        if publish_timestamp:
            return publish_timestamp.strftime('%Y-%m-%d')
        else:
            return ''


class Substitution:
    def __init__(self, variable_name: str):
        self.variable_name = variable_name

    def is_constant(self) -> bool:
        return False

    def substitute(self, values: Mapping[str, str | None]) -> str:
        key = self.variable_name[2:-1]
        val = values.get(key, self.variable_name)
        return val.replace('/', '_') if val else ''


class Literal:
    def __init__(self, text: str):
        self.text = text

    def is_constant(self) -> bool:
        return True

    def substitute(self, _values: Mapping[str, str | None]) -> str:
        return self.text
