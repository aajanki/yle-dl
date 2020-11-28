# -*- coding: utf-8 -*-

from yledl import YleDlDownloader, StreamFilters
from yledl.backends import Backends, FailingBackend
from yledl.streamflavor import StreamFlavor, FailedFlavor


class MockBackend(object):
    def __init__(self, name, data=None):
        self.name = name
        self.data = data

    def is_valid(self):
        return True


class MockGeoLocation(object):
    def located_in_finland(self, referrer):
        return True


flavors = [
    StreamFlavor(streams=[MockBackend('ffmpeg', 1)],
                 bitrate=190, width=224, height=126, media_type=''),

    StreamFlavor(streams=[MockBackend('ffmpeg', 5)],
                 bitrate=1506, width=1280, height=720, media_type=''),
    StreamFlavor(streams=[MockBackend('ffmpeg', 6)],
                 bitrate=2628, width=1280, height=720, media_type=''),
    StreamFlavor(streams=[MockBackend('ffmpeg', 7)],
                 bitrate=4128, width=1920, height=1080, media_type=''),

    StreamFlavor(streams=[MockBackend('ffmpeg', 4)],
                 bitrate=964, width=640, height=360, media_type=''),
    StreamFlavor(streams=[MockBackend('ffmpeg', 3)],
                 bitrate=668, width=640, height=360, media_type=''),
    StreamFlavor(streams=[MockBackend('ffmpeg', 2)],
                 bitrate=469, width=640, height=360, media_type='')
]


def yle_dl_downloader():
    return YleDlDownloader(MockGeoLocation())


def video_flavor(streams):
    return StreamFlavor(media_type='video', streams=streams)


def filter_flavors(flavors, max_height=None, max_bitrate=None,
                   enabled_backends=None):
    if enabled_backends is None:
        enabled_backends = list(Backends.default_order)

    filters = StreamFilters(maxheight=max_height,
                            maxbitrate=max_bitrate,
                            enabled_backends=enabled_backends)
    return yle_dl_downloader().select_flavor(flavors, filters)


def backend_data(flavor):
    return [s.data for s in flavor.streams]


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
    assert backend_data(filter_flavors(flavors)) == [7]


def test_bitrate_filter():
    assert backend_data(filter_flavors(flavors, None, 10)) == [1]
    assert backend_data(filter_flavors(flavors, None, 200)) == [1]
    assert backend_data(filter_flavors(flavors, None, 963)) == [3]
    assert backend_data(filter_flavors(flavors, None, 964)) == [4]
    assert backend_data(filter_flavors(flavors, None, 1000)) == [4]
    assert backend_data(filter_flavors(flavors, None, 5000)) == [7]


def test_resolution_filter():
    assert backend_data(filter_flavors(flavors, 100, None)) == [1]
    assert backend_data(filter_flavors(flavors, 480, None)) == [2]
    assert backend_data(filter_flavors(flavors, 719, None)) == [2]
    assert backend_data(filter_flavors(flavors, 720, None)) == [5]
    assert backend_data(filter_flavors(flavors, 1080, None)) == [7]
    assert backend_data(filter_flavors(flavors, 2160, None)) == [7]


def test_combined_filters():
    assert backend_data(filter_flavors(flavors, 10, 10)) == [1]
    assert backend_data(filter_flavors(flavors, 200, 10)) == [1]
    assert backend_data(filter_flavors(flavors, 10, 200)) == [1]
    assert backend_data(filter_flavors(flavors, 360, 400)) == [1]
    assert backend_data(filter_flavors(flavors, 360, 650)) == [2]
    assert backend_data(filter_flavors(flavors, 360, 700)) == [3]
    assert backend_data(filter_flavors(flavors, 360, 5000)) == [4]
    assert backend_data(filter_flavors(flavors, 720, 200)) == [1]
    assert backend_data(filter_flavors(flavors, 2160, 1506)) == [5]


def test_combined_filter_with_some_failed_flavors():
    test_flavors = [
        FailedFlavor('Failure'),
        StreamFlavor(streams=[MockBackend('ffmpeg', 2)], bitrate=190,
                     width=224, height=126, media_type=''),
        StreamFlavor(streams=[MockBackend('ffmpeg', 3)], bitrate=469,
                     width=640, height=360, media_type=''),
        FailedFlavor('Second failure'),
        StreamFlavor(streams=[MockBackend('ffmpeg', 5)], bitrate=1506,
                     width=1280, height=720, media_type='')
    ]

    assert backend_data(filter_flavors(test_flavors)) == [5]
    assert backend_data(filter_flavors(test_flavors, max_height=720,
                                       max_bitrate=200)) == [2]
    assert backend_data(filter_flavors(test_flavors, max_height=400,
                                       max_bitrate=2000)) == [3]


def test_combined_filter_bitrate_only_and_some_failures():
    test_flavors = [
        FailedFlavor('Failure'),
        StreamFlavor(streams=[MockBackend('ffmpeg', 1)], bitrate=517,
                     media_type='video'),
        FailedFlavor('Second failure')
    ]

    assert backend_data(filter_flavors(test_flavors)) == [1]
    assert backend_data(filter_flavors(test_flavors, max_height=720)) == [1]
    assert backend_data(filter_flavors(test_flavors, max_bitrate=200)) == [1]
    assert backend_data(filter_flavors(
        test_flavors, max_height=720, max_bitrate=200)) == [1]


def test_backend_filter_first_preferred():
    test_flavors = [video_flavor([
        MockBackend('ffmpeg'),
        MockBackend('wget'),
        MockBackend('youtubedl')
    ])]
    enabled = ['wget', 'ffmpeg', 'youtubedl', 'rtmpdump']
    flavor = filter_flavors(test_flavors, enabled_backends=enabled)

    assert flavor.streams[0].name == enabled[0]


def test_backend_filter_first_preferred_2():
    test_flavors = [video_flavor([MockBackend('rtmpdump')])]
    enabled = ['wget', 'ffmpeg', 'youtubedl', 'rtmpdump']
    flavor = filter_flavors(test_flavors, enabled_backends=enabled)

    assert flavor.streams[0].name == enabled[3]


def test_backend_filter_no_match():
    test_flavors = [video_flavor([
        MockBackend('ffmpeg'),
        MockBackend('wget'),
        MockBackend('youtubedl')
    ])]
    enabled = ['rtmpdump']
    flavor = filter_flavors(test_flavors, enabled_backends=enabled)

    assert len(flavor.streams) == 1
    assert not flavor.streams[0].is_valid()
    assert 'Required backend not enabled' in flavor.streams[0].error_message


def test_backend_filter_no_streams():
    flavor = filter_flavors([], enabled_backends=['ffmpeg'])

    assert flavor is None


def test_backend_filter_failed_stream():
    test_flavors = [video_flavor([
        MockBackend('ffmpeg'),
        FailingBackend('wget stream failed'),
        MockBackend('youtubedl')
    ])]
    enabled = ['wget']
    flavor = filter_flavors(test_flavors, enabled_backends=enabled)

    assert len(flavor.streams) == 1
    assert not flavor.streams[0].is_valid()


def test_backend_filter_failed_fallback():
    test_flavors = [video_flavor([
        MockBackend('ffmpeg'),
        FailingBackend('wget stream failed'),
        MockBackend('youtubedl')
    ])]
    enabled = ['wget', 'youtubedl', 'ffmpeg']
    flavor = filter_flavors(test_flavors, enabled_backends=enabled)

    assert len(flavor.streams) == 2
    assert flavor.streams[0].is_valid()
    assert flavor.streams[0].name == enabled[1]
    assert flavor.streams[1].is_valid()
    assert flavor.streams[1].name == enabled[2]
