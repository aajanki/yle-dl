# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import re


class TitleFormatter(object):
    def format(self, title, publish_timestamp=None, series_title=None,
               subheading=None, season=None, episode=None):
        if title is None:
            return None

        title = self._remove_repeated_main_title(title)
        title = self._prepend_series_title(series_title, title)
        title += self._episode_postfix(season, episode)
        title += self._subheading_postfix(title, subheading)
        title = self._remove_genre_prefix(title)
        title += self._timestamp_postfix(publish_timestamp)
        return title

    def _prepend_series_title(self, series_title, episode_title):
        if series_title:
            if episode_title.startswith(series_title):
                return episode_title
            else:
                return series_title + ': ' + episode_title
        else:
            return episode_title

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

    def _episode_postfix(self, season, episode):
        if season and episode:
            return ': S%02dE%02d' % (season, episode)
        elif episode:
            return ': E%02d' % (episode)
        else:
            return ''

    def _subheading_postfix(self, title, subheading):
        if subheading and subheading not in title:
            return ': ' + subheading
        else:
            return ''

    def _timestamp_postfix(self, publish_timestamp):
        if publish_timestamp:
            short = re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', publish_timestamp or '')
            title_ts = short.group(0) if short else publish_timestamp
            return '-' + title_ts.replace('/', '-').replace(' ', '-')
        else:
            return ''
