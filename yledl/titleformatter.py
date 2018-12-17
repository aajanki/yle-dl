# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import re
from datetime import datetime


class TitleFormatter(object):
    def format(self, title, publish_timestamp=None, series_title=None,
               subheading=None, season=None, episode=None):
        if title is None:
            return None

        main_title = self._main_title(title, subheading)
        return (self._series_title_prefix(series_title, main_title) +
                main_title +
                self._episode_postfix(season, episode) +
                self._timestamp_postfix(publish_timestamp))

    def _main_title(self, title, subheading):
        main_title = self._remove_genre_prefix(
            self._remove_repeated_main_title(title))

        if subheading and subheading not in main_title:
            return main_title + ': ' + subheading
        else:
            return main_title

    def _series_title_prefix(self, series_title, episode_title):
        if series_title and not episode_title.startswith(series_title):
            return series_title + ': '
        else:
            return ''

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

    def _timestamp_postfix(self, publish_timestamp):
        if publish_timestamp and hasattr(publish_timestamp, 'hour'):
            return '-' + datetime.strftime(publish_timestamp, '%Y-%m-%dT%H:%M')
        elif publish_timestamp:
            return '-' + datetime.strftime(publish_timestamp, '%Y-%m-%d')
        else:
            return ''
