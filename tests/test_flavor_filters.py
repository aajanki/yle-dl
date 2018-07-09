# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import pytest
from yledl import YleDlDownloader, StreamFilters
from yledl.extractors import StreamFlavor, Subtitle
from yledl.streams import AreenaStreamBase, InvalidStream


class MockBackend(object):
    def __init__(self, name):
        self.name = name


class MockStream(AreenaStreamBase):
    def __init__(self, backend):
        AreenaStreamBase.__init__(self)
        self.backend = MockBackend(backend)

    def create_downloader(self):
        return self.backend


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
    filters = StreamFilters(maxheight=max_height,
                            maxbitrate=max_bitrate,
                            hardsubs=hard_sub)
    return YleDlDownloader().select_flavor(flavors, filters)


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


def test_backend_filter_first_preferred():
    streams = [
        MockStream('ffmpeg'),
        MockStream('wget'),
        MockStream('youtubedl')
    ]
    enabled = ['wget', 'ffmpeg', 'youtubedl', 'rtmpdump']
    filtered = YleDlDownloader().filter_by_backend(streams, enabled)

    assert filtered[0].create_downloader().name == enabled[0]


def test_backend_filter_first_preferred_2():
    streams = [MockStream('rtmpdump')]
    enabled = ['wget', 'ffmpeg', 'youtubedl', 'rtmpdump']
    filtered = YleDlDownloader().filter_by_backend(streams, enabled)

    assert filtered[0].create_downloader().name == enabled[3]


def test_backend_filter_no_match():
    streams = [
        MockStream('ffmpeg'),
        MockStream('wget'),
        MockStream('youtubedl')
    ]
    enabled = ['rtmpdump']
    filtered = YleDlDownloader().filter_by_backend(streams, enabled)

    assert len(filtered) == 1
    assert not filtered[0].is_valid()
    assert 'Required backend not enabled' in filtered[0].get_error_message()


def test_backend_filter_no_streams():
    enabled = ['ffmpeg']
    filtered = YleDlDownloader().filter_by_backend([], enabled)

    assert len(filtered) == 0


def test_backend_filter_failed_stream():
    streams = [
        MockStream('ffmpeg'),
        InvalidStream('wget stream failed'),
        MockStream('youtubedl')
    ]
    enabled = ['wget']
    filtered = YleDlDownloader().filter_by_backend(streams, enabled)

    assert len(filtered) == 1
    assert not filtered[0].is_valid()
    assert filtered[0].get_error_message() == 'wget stream failed'


def test_backend_filter_failed_fallback():
    streams = [
        MockStream('ffmpeg'),
        InvalidStream('wget stream failed'),
        MockStream('youtubedl')
    ]
    enabled = ['wget', 'youtubedl', 'ffmpeg']
    filtered = YleDlDownloader().filter_by_backend(streams, enabled)

    assert len(filtered) == 2
    assert filtered[0].is_valid()
    assert filtered[0].create_downloader().name == enabled[1]
    assert filtered[1].is_valid()
    assert filtered[1].create_downloader().name == enabled[2]
