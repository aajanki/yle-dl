# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import re

def title(raw_title, publish_timestamp, subheading=None, season=None,
          episode=None):
    title = raw_title
    if title is None:
        return None

    if ':' in title:
        prefix, rest = title.split(':', 1)
        if prefix in rest:
            title = rest.strip()

    if season and episode:
        title += ': S%02dE%02d' % (season, episode)
    elif episode:
        title += ': E%02d' % (episode)

    if subheading and subheading not in title:
        title += ': ' + subheading

    title = remove_genre_prefix(title)

    if publish_timestamp:
        short = re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', publish_timestamp or '')
        title_ts = short.group(0) if short else publish_timestamp
        title += '-' + title_ts.replace('/', '-').replace(' ', '-')

    return title

def remove_genre_prefix(title):
    genre_prefixes = ['Elokuva:', 'Kino:', 'Kino Klassikko:',
                      'Kino Suomi:', 'Kotikatsomo:', 'Uusi Kino:', 'Dok:',
                      'Dokumenttiprojekti:', 'Historia:']
    for prefix in genre_prefixes:
        if title.startswith(prefix):
            return title[len(prefix):].strip()
    return title
