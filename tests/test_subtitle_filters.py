# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
from yledl import StreamFilters
from yledl.downloader import SubtitleDownloader
from yledl.extractors import Subtitle


subtitles = [
    Subtitle(url='https://example.com/subtitles/fin.srt', lang='fin'),
    Subtitle(url='https://example.com/subtitles/swe.srt', lang='swe'),
    Subtitle(url='https://example.com/subtitles/smi.srt', lang='smi')
]


def test_all():
    selected = SubtitleDownloader().select(subtitles, StreamFilters())
    assert selected == subtitles

    selected = SubtitleDownloader().select(subtitles, StreamFilters(sublang='all'))
    assert selected == subtitles


def test_filter_by_lang():
    filters_fin = StreamFilters(sublang='fin')
    selected_fin = SubtitleDownloader().select(subtitles, filters_fin)

    assert selected_fin == [sub for sub in subtitles if sub.lang == 'fin']

    filters_swe = StreamFilters(sublang='swe')
    selected_swe = SubtitleDownloader().select(subtitles, filters_swe)

    assert selected_swe == [sub for sub in subtitles if sub.lang == 'swe']


def test_do_not_download_if_hardsubs_is_set():
    filters = StreamFilters(hardsubs=True)
    selected = SubtitleDownloader().select(subtitles, filters)
    assert selected == []
