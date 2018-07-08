# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import pytest
from yledl import YleDlDownloader, StreamFilters, BackendFactory
from yledl.extractors import StreamFlavor, Subtitle


flavors = [
    StreamFlavor(streams=[1], bitrate=190, width=224, height=126, media_type=''),

    StreamFlavor(streams=[5], bitrate=1506, width=1280, height=720, media_type=''),
    StreamFlavor(streams=[6], bitrate=2628, width=1280, height=720, media_type=''),
    StreamFlavor(streams=[7], bitrate=4128, width=1920, height=1080, media_type=''),

    StreamFlavor(streams=[4], bitrate=964, width=640, height=360, media_type=''),
    StreamFlavor(streams=[3], bitrate=668, width=640, height=360, media_type=''),
    StreamFlavor(streams=[2], bitrate=469, width=640, height=360, media_type='')
]


hard_sub_flavors = [
    StreamFlavor(streams=['fi'], bitrate=510, width=640, height=360,
                 hard_subtitle=Subtitle(url=None, lang='fi'), media_type=''),
    StreamFlavor(streams=['sv'], bitrate=469, width=640, height=360,
                 hard_subtitle=Subtitle(url=None, lang='sv'), media_type=''),
    StreamFlavor(streams=['none'], bitrate=489, width=640, height=360,
                 media_type='')
]


def filter_flavors(flavors, max_height=None, max_bitrate=None, hard_sub=None):
    backends = [BackendFactory.ADOBEHDSPHP]
    filters = StreamFilters(maxheight=max_height,
                            maxbitrate=max_bitrate,
                            hardsubs=hard_sub)
    return YleDlDownloader(backends).select_flavor(flavors, filters)


def test_empty_input():
    assert filter_flavors([], None, None) == None
    assert filter_flavors([], 720, None) == None
    assert filter_flavors([], None, 5000) == None
    assert filter_flavors([], 720, 5000) == None


def test_no_filters():
    assert filter_flavors(flavors, None, None).streams == [7]


def test_bitrate_filter():
    assert filter_flavors(flavors, None, 10).streams == [1]
    assert filter_flavors(flavors, None, 200).streams == [1]
    assert filter_flavors(flavors, None, 963).streams == [3]
    assert filter_flavors(flavors, None, 964).streams == [4]
    assert filter_flavors(flavors, None, 1000).streams == [4]
    assert filter_flavors(flavors, None, 5000).streams == [7]


def test_resolution_filter():
    assert filter_flavors(flavors, 100, None).streams == [1]
    assert filter_flavors(flavors, 480, None).streams == [2]
    assert filter_flavors(flavors, 719, None).streams == [2]
    assert filter_flavors(flavors, 720, None).streams == [5]
    assert filter_flavors(flavors, 1080, None).streams == [7]
    assert filter_flavors(flavors, 2160, None).streams == [7]


def test_combined_filters():
    assert filter_flavors(flavors, 10, 10).streams == [1]
    assert filter_flavors(flavors, 200, 10).streams == [1]
    assert filter_flavors(flavors, 10, 200).streams == [1]
    assert filter_flavors(flavors, 360, 400).streams == [1]
    assert filter_flavors(flavors, 360, 650).streams == [2]
    assert filter_flavors(flavors, 360, 700).streams == [3]
    assert filter_flavors(flavors, 360, 5000).streams == [4]
    assert filter_flavors(flavors, 720, 200).streams == [1]
    assert filter_flavors(flavors, 2160, 1506).streams == [5]


def test_hard_subtitle_filters():
    assert filter_flavors(hard_sub_flavors).streams == ['none']
    assert filter_flavors(hard_sub_flavors, hard_sub='fin').streams == ['fi']
    assert filter_flavors(hard_sub_flavors, hard_sub='swe').streams == ['sv']


def test_hard_subtitle_filters_no_match():
    assert filter_flavors(flavors, hard_sub='fin') == None
