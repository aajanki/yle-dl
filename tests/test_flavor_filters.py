# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import pytest
from yledl import YleDlDownloader, StreamFilters
from yledl.backends import Backends
from yledl.extractors import Subtitle
from yledl.streamflavor import StreamFlavor, FailedFlavor
from yledl.streams import AreenaStreamBase, InvalidStream


class MockBackend(object):
    def __init__(self, name):
        self.name = name


class MockStream(AreenaStreamBase):
    def __init__(self, backend, name=None):
        AreenaStreamBase.__init__(self)
        self.backend = MockBackend(backend)
        self.name = name

    def create_downloader(self):
        return self.backend


flavors = [
    StreamFlavor(streams=[MockStream('ffmpeg', 1)], bitrate=190, width=224, height=126, media_type=''),

    StreamFlavor(streams=[MockStream('ffmpeg', 5)], bitrate=1506, width=1280, height=720, media_type=''),
    StreamFlavor(streams=[MockStream('ffmpeg', 6)], bitrate=2628, width=1280, height=720, media_type=''),
    StreamFlavor(streams=[MockStream('ffmpeg', 7)], bitrate=4128, width=1920, height=1080, media_type=''),

    StreamFlavor(streams=[MockStream('ffmpeg', 4)], bitrate=964, width=640, height=360, media_type=''),
    StreamFlavor(streams=[MockStream('ffmpeg', 3)], bitrate=668, width=640, height=360, media_type=''),
    StreamFlavor(streams=[MockStream('ffmpeg', 2)], bitrate=469, width=640, height=360, media_type='')
]


hard_sub_flavors = [
    StreamFlavor(streams=[MockStream('ffmpeg', 'fi')],
                 bitrate=510, width=640, height=360,
                 hard_subtitle=Subtitle(url=None, lang='fi'), media_type=''),
    StreamFlavor(streams=[MockStream('ffmpeg', 'sv')],
                 bitrate=469, width=640, height=360,
                 hard_subtitle=Subtitle(url=None, lang='sv'), media_type=''),
    StreamFlavor(streams=[MockStream('ffmpeg', 'none')],
                 bitrate=489, width=640, height=360, media_type='')
]


def video_flavor(streams):
    return StreamFlavor(media_type='video', streams=streams)


def filter_flavors(flavors, max_height=None, max_bitrate=None, hard_sub=None, enabled_backends=None):
    if enabled_backends is None:
        enabled_backends = list(Backends.default_order)

    filters = StreamFilters(maxheight=max_height,
                            maxbitrate=max_bitrate,
                            hardsubs=hard_sub,
                            enabled_backends=enabled_backends)
    return YleDlDownloader().select_flavor(flavors, filters)


def stream_names(flavor):
    return [s.name for s in flavor.streams]


def test_empty_input():
    assert filter_flavors([]) is None
    assert filter_flavors([], max_height=720) is None
    assert filter_flavors([], max_bitrate=5000) is None
    assert filter_flavors([], max_height=720, max_bitrate=5000) is None


def test_only_failed_flavors():
    failed_flavors = [
        FailedFlavor('First failure'),
        FailedFlavor('Second failure'),
        FailedFlavor('Third failure')
    ]

    assert isinstance(filter_flavors(failed_flavors), FailedFlavor)
    assert isinstance(filter_flavors(failed_flavors, max_height=720),
                      FailedFlavor)
    assert isinstance(filter_flavors(failed_flavors, max_bitrate=2000),
                      FailedFlavor)


def test_no_filters():
    assert stream_names(filter_flavors(flavors)) == [7]


def test_bitrate_filter():
    assert stream_names(filter_flavors(flavors, None, 10)) == [1]
    assert stream_names(filter_flavors(flavors, None, 200)) == [1]
    assert stream_names(filter_flavors(flavors, None, 963)) == [3]
    assert stream_names(filter_flavors(flavors, None, 964)) == [4]
    assert stream_names(filter_flavors(flavors, None, 1000)) == [4]
    assert stream_names(filter_flavors(flavors, None, 5000)) == [7]


def test_resolution_filter():
    assert stream_names(filter_flavors(flavors, 100, None)) == [1]
    assert stream_names(filter_flavors(flavors, 480, None)) == [2]
    assert stream_names(filter_flavors(flavors, 719, None)) == [2]
    assert stream_names(filter_flavors(flavors, 720, None)) == [5]
    assert stream_names(filter_flavors(flavors, 1080, None)) == [7]
    assert stream_names(filter_flavors(flavors, 2160, None)) == [7]


def test_combined_filters():
    assert stream_names(filter_flavors(flavors, 10, 10)) == [1]
    assert stream_names(filter_flavors(flavors, 200, 10)) == [1]
    assert stream_names(filter_flavors(flavors, 10, 200)) == [1]
    assert stream_names(filter_flavors(flavors, 360, 400)) == [1]
    assert stream_names(filter_flavors(flavors, 360, 650)) == [2]
    assert stream_names(filter_flavors(flavors, 360, 700)) == [3]
    assert stream_names(filter_flavors(flavors, 360, 5000)) == [4]
    assert stream_names(filter_flavors(flavors, 720, 200)) == [1]
    assert stream_names(filter_flavors(flavors, 2160, 1506)) == [5]


def test_combined_filter_with_some_failed_flavors():
    test_flavors = [
        FailedFlavor('Failure'),
        StreamFlavor(streams=[MockStream('ffmpeg', 2)], bitrate=190,
                     width=224, height=126, media_type=''),
        StreamFlavor(streams=[MockStream('ffmpeg', 3)], bitrate=469,
                     width=640, height=360, media_type=''),
        FailedFlavor('Second failure'),
        StreamFlavor(streams=[MockStream('ffmpeg', 5)], bitrate=1506,
                     width=1280, height=720, media_type='')
    ]

    assert stream_names(filter_flavors(test_flavors)) == [5]
    assert stream_names(filter_flavors(test_flavors, max_height=720,
                                       max_bitrate=200)) == [2]
    assert stream_names(filter_flavors(test_flavors, max_height=400,
                                       max_bitrate=2000)) == [3]


def test_combined_filter_bitrate_only_and_some_failures():
    test_flavors = [
        FailedFlavor('Failure'),
        StreamFlavor(streams=[MockStream('ffmpeg', 1)], bitrate=517,
                     media_type='video'),
        FailedFlavor('Second failure')
    ]

    assert stream_names(filter_flavors(test_flavors)) == [1]
    assert stream_names(filter_flavors(test_flavors, max_height=720)) == [1]
    assert stream_names(filter_flavors(test_flavors, max_bitrate=200)) == [1]
    assert stream_names(filter_flavors(
        test_flavors, max_height=720, max_bitrate=200)) == [1]


def test_hard_subtitle_filters():
    assert stream_names(filter_flavors(hard_sub_flavors)) == ['none']
    assert stream_names(filter_flavors(hard_sub_flavors, hard_sub='fin')) == ['fi']
    assert stream_names(filter_flavors(hard_sub_flavors, hard_sub='swe')) == ['sv']


def test_hard_subtitle_filters_no_match():
    assert filter_flavors(flavors, hard_sub='fin') is None


def test_backend_filter_first_preferred():
    test_flavors = [video_flavor([
        MockStream('ffmpeg'),
        MockStream('wget'),
        MockStream('youtubedl')
    ])]
    enabled = ['wget', 'ffmpeg', 'youtubedl', 'rtmpdump']
    flavor = filter_flavors(test_flavors, enabled_backends=enabled)

    assert flavor.streams[0].create_downloader().name == enabled[0]


def test_backend_filter_first_preferred_2():
    test_flavors = [video_flavor([MockStream('rtmpdump')])]
    enabled = ['wget', 'ffmpeg', 'youtubedl', 'rtmpdump']
    flavor = filter_flavors(test_flavors, enabled_backends=enabled)

    assert flavor.streams[0].create_downloader().name == enabled[3]


def test_backend_filter_no_match():
    test_flavors = [video_flavor([
        MockStream('ffmpeg'),
        MockStream('wget'),
        MockStream('youtubedl')
    ])]
    enabled = ['rtmpdump']
    flavor = filter_flavors(test_flavors, enabled_backends=enabled)

    assert len(flavor.streams) == 1
    assert not flavor.streams[0].is_valid()
    assert 'Required backend not enabled' in flavor.streams[0].get_error_message()


def test_backend_filter_no_streams():
    flavor = filter_flavors([], enabled_backends=['ffmpeg'])

    assert flavor is None


def test_backend_filter_failed_stream():
    test_flavors = [video_flavor([
        MockStream('ffmpeg'),
        InvalidStream('wget stream failed'),
        MockStream('youtubedl')
    ])]
    enabled = ['wget']
    flavor = filter_flavors(test_flavors, enabled_backends=enabled)

    assert len(flavor.streams) == 1
    assert not flavor.streams[0].is_valid()


def test_backend_filter_failed_fallback():
    test_flavors = [video_flavor([
        MockStream('ffmpeg'),
        InvalidStream('wget stream failed'),
        MockStream('youtubedl')
    ])]
    enabled = ['wget', 'youtubedl', 'ffmpeg']
    flavor = filter_flavors(test_flavors, enabled_backends=enabled)

    assert len(flavor.streams) == 2
    assert flavor.streams[0].is_valid()
    assert flavor.streams[0].create_downloader().name == enabled[1]
    assert flavor.streams[1].is_valid()
    assert flavor.streams[1].create_downloader().name == enabled[2]
