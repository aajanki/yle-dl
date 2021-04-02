# -*- coding: utf-8 -*-

import attr
import json
import pytest
from datetime import datetime
from yledl import StreamFilters, IOContext, RD_SUCCESS, RD_FAILED
from yledl.backends import BaseDownloader
from yledl.downloader import YleDlDownloader
from yledl.extractors import Clip, FailedClip, StreamFlavor
from yledl.subtitles import EmbeddedSubtitle, Subtitle
from yledl.timestamp import FixedOffset


class StateCollectingBackend(BaseDownloader):
    def __init__(self, state_dict, id, name='ffmpeg'):
        BaseDownloader.__init__(self)
        self.id = id
        self.state_dict = state_dict
        self.name = name

    def save_stream(self, clip_title, clip, io):
        self.state_dict['command'] = 'download'
        self.state_dict['stream_id'] = self.id
        self.state_dict['backend'] = self.name

        return RD_SUCCESS

    def pipe(self, io):
        self.state_dict['command'] = 'pipe'
        self.state_dict['stream_id'] = self.id
        self.state_dict['backend'] = self.name

        return RD_SUCCESS

    def stream_url(self):
        return 'https://example.com/video/{}.mp4'.format(self.id)

    def next_available_filename(self, proposed):
        return proposed

    def warn_on_unsupported_feature(self, io):
        pass


class FailingBackend(StateCollectingBackend):
    def is_valid(self):
        return False

    def save_stream(self, clip_title, clip, io):
        return RD_FAILED

    def pipe(self, io):
        return RD_FAILED


class MockGeoLocation(object):
    def located_in_finland(self, referrer):
        return True


def successful_clip(state_dict, title='Test clip: S01E01-2018-07-01T00:00'):
    return Clip(
        webpage='https://areena.yle.fi/1-1234567',
        flavors=[
            # The flavors are intentionally unsorted
            StreamFlavor(
                media_type='video',
                height=1080,
                width=1920,
                bitrate=2808,
                streams=[StateCollectingBackend(state_dict, 'high_quality')]
            ),
            StreamFlavor(
                media_type='video',
                height=360,
                width=640,
                bitrate=880,
                streams=[StateCollectingBackend(state_dict, 'low_quality')]
            ),
            StreamFlavor(
                media_type='video',
                height=480,
                width=640,
                bitrate=964,
                streams=[StateCollectingBackend(state_dict, 'low_quality_2')],
            ),
            StreamFlavor(
                media_type='video',
                height=720,
                width=1280,
                bitrate=1412,
                streams=[StateCollectingBackend(state_dict, 'medium_quality')]
            ),
            StreamFlavor(
                media_type='video',
                height=720,
                width=1280,
                bitrate=1872,
                streams=[StateCollectingBackend(state_dict, 'medium_quality_high_bitrate')]
            )
        ],
        title=title,
        duration_seconds=950,
        region='Finland',
        publish_timestamp=datetime(2018, 7, 1, tzinfo=FixedOffset(3)),
        expiration_timestamp=datetime(2019, 1, 1, tzinfo=FixedOffset(3)),
        embedded_subtitles=[
            EmbeddedSubtitle('fin', 'käännöstekstitys'),
            EmbeddedSubtitle('swe', 'käännöstekstitys')
        ]
    )


def incomplete_flavors_clip(state_dict):
    return Clip(
        webpage='https://areena.yle.fi/1-1234567',
        flavors=[
            StreamFlavor(
                media_type='video',
                streams=[StateCollectingBackend(state_dict, '1')]
            ),
            StreamFlavor(
                media_type='video',
                height=360,
                width=640,
                streams=[StateCollectingBackend(state_dict, '2')]
            ),
            StreamFlavor(
                media_type='video',
                streams=[StateCollectingBackend(state_dict, '3')]
            )
        ],
        title='Test clip: S01E01-2018-07-01T00:00',
        duration_seconds=None,
        region='Finland',
        publish_timestamp=None,
        expiration_timestamp=None
    )


def multistream_clip(state_dict, title='Test clip: S01E01-2018-07-01T00:00'):
    return Clip(
        webpage='https://areena.yle.fi/1-1234567',
        flavors=[
            StreamFlavor(
                media_type='video',
                height=360,
                width=640,
                bitrate=964,
                streams=[
                    FailingBackend(state_dict, '1', 'wget'),
                    FailingBackend(state_dict, '2', 'Invalid stream'),
                    StateCollectingBackend(state_dict, '3', 'wget'),
                    StateCollectingBackend(state_dict, '4', 'ffmpeg')
                ]
            )
        ],
        title='Test clip: S01E01-2018-07-01T00:00',
        duration_seconds=950,
        region='Finland',
        publish_timestamp=None,
        expiration_timestamp=None
    )


def failed_clip():
    return FailedClip('https://areena.yle.fi/1-1234567', 'Failed test clip')


def failed_stream_clip(state_dict):
    return Clip(
        webpage='https://areena.yle.fi/1-1234567',
        flavors=[
            StreamFlavor(
                media_type='video',
                height=360,
                width=640,
                bitrate=964,
                streams=[
                    FailingBackend(state_dict, '1', 'wget'),
                    FailingBackend(state_dict, '2', 'ffmpeg')
                ]
            )
        ],
        title='Test clip: S01E01-2018-07-01T00:00',
        duration_seconds=950,
        region='Finland',
        publish_timestamp=None,
        expiration_timestamp=None
    )


@attr.s
class DownloaderParametersFixture(object):
    io = attr.ib()
    filters = attr.ib()
    downloader = attr.ib()


@pytest.fixture
def simple():
    return DownloaderParametersFixture(
        io=IOContext(destdir='/tmp/'),
        filters=StreamFilters(),
        downloader=YleDlDownloader(MockGeoLocation()))


def test_download_success(simple):
    state = {}
    clips = [successful_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, simple.filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'high_quality'


def test_download_incomplete_metadata(simple):
    state = {}
    clips = [incomplete_flavors_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, simple.filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == '3'


def test_download_filter_resolution(simple):
    state = {}
    filters = StreamFilters(maxheight=400)
    clips = [successful_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'low_quality'


def test_download_filter_exact_resolution(simple):
    state = {}
    filters = StreamFilters(maxheight=720)
    clips = [successful_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'medium_quality'


def test_download_filter_bitrate1(simple):
    state = {}
    filters = StreamFilters(maxbitrate=1500)
    clips = [successful_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'medium_quality'


def test_download_filter_bitrate2(simple):
    state = {}
    filters = StreamFilters(maxbitrate=2000)
    clips = [successful_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'medium_quality_high_bitrate'


def test_download_multiple_filters(simple):
    state = {}
    filters = StreamFilters(maxheight=700, maxbitrate=900)
    clips = [successful_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'low_quality'


def test_pipe_success(simple):
    state = {}
    clips = [successful_clip(state)]
    res = simple.downloader.pipe(clips, simple.io, simple.filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'pipe'
    assert state['stream_id'] == 'high_quality'


def test_print_urls(simple):
    clips = [successful_clip({}), successful_clip({})]
    urls = simple.downloader.get_urls(clips, simple.filters)

    assert urls == [
        'https://example.com/video/high_quality.mp4',
        'https://example.com/video/high_quality.mp4'
    ]


def test_print_titles(simple):
    titles = ['Uutiset', 'Pasila: S01E01-2018-07-01T00:00']
    clips = [successful_clip({}, t) for t in titles]

    assert simple.downloader.get_titles(clips, simple.io) == titles


def test_print_titles_replaces_whitespace(simple):
    titles = ['   Title with\tall\vkinds\u00a0of\u2003whitespace \t \u00a0 characters']
    expected_titles = ['Title with all kinds of whitespace characters']
    clips = [successful_clip({}, t) for t in titles]

    assert simple.downloader.get_titles(clips, simple.io) == expected_titles


def test_print_metadata(simple):
    state = {}
    clips = [successful_clip(state)]
    metadata = simple.downloader.get_metadata(clips, simple.io)
    parsed_metadata = json.loads(metadata[0])

    assert len(metadata) == 1

    # Match filename fuzzily because the exact name depends on the existing
    # file names
    assert 'Test clip' in parsed_metadata[0]['filename']
    del parsed_metadata[0]['filename']
    assert parsed_metadata == [
        {
            'webpage': 'https://areena.yle.fi/1-1234567',
            'title': 'Test clip: S01E01-2018-07-01T00:00',
            'flavors': [
                {
                    'media_type': 'video',
                    'height': 360,
                    'width': 640,
                    'bitrate': 880,
                    'url': 'https://example.com/video/low_quality.mp4',
                    'backends': ['ffmpeg']
                },
                {
                    'media_type': 'video',
                    'height': 480,
                    'width': 640,
                    'bitrate': 964,
                    'url': 'https://example.com/video/low_quality_2.mp4',
                    'backends': ['ffmpeg']
                },
                {
                    'media_type': 'video',
                    'height': 720,
                    'width': 1280,
                    'bitrate': 1412,
                    'url': 'https://example.com/video/medium_quality.mp4',
                    'backends': ['ffmpeg']
                },
                {
                    'media_type': 'video',
                    'height': 720,
                    'width': 1280,
                    'bitrate': 1872,
                    'url': 'https://example.com/video/medium_quality_high_bitrate.mp4',
                    'backends': ['ffmpeg']
                },
                {
                    'media_type': 'video',
                    'height': 1080,
                    'width': 1920,
                    'bitrate': 2808,
                    'url': 'https://example.com/video/high_quality.mp4',
                    'backends': ['ffmpeg']
                }
            ],
            'duration_seconds': 950,
            'embedded_subtitles': [
                {'language': 'fin', 'category': 'käännöstekstitys'},
                {'language': 'swe', 'category': 'käännöstekstitys'}
            ],
            'subtitles': [],
            'region': 'Finland',
            'publish_timestamp': '2018-07-01T00:00:00+03:00',
            'expiration_timestamp': '2019-01-01T00:00:00+03:00'
        }
    ]


def test_print_metadata_incomplete(simple):
    state = {}
    clips = [incomplete_flavors_clip(state)]
    metadata = simple.downloader.get_metadata(clips, simple.io)
    parsed_metadata = json.loads(metadata[0])

    assert len(parsed_metadata) == 1

    # Match filename fuzzily because the exact name depends on the existing
    # file names
    assert 'Test clip' in parsed_metadata[0]['filename']
    del parsed_metadata[0]['filename']

    assert parsed_metadata == [
        {
            'webpage': 'https://areena.yle.fi/1-1234567',
            'title': 'Test clip: S01E01-2018-07-01T00:00',
            'flavors': [
                {
                    'media_type': 'video',
                    'url': 'https://example.com/video/1.mp4',
                    'backends': ['ffmpeg']
                },
                {
                    'media_type': 'video',
                    'height': 360,
                    'width': 640,
                    'url': 'https://example.com/video/2.mp4',
                    'backends': ['ffmpeg']
                },
                {
                    'media_type': 'video',
                    'url': 'https://example.com/video/3.mp4',
                    'backends': ['ffmpeg']
                }
            ],
            'region': 'Finland',
            'embedded_subtitles': [],
            'subtitles': []
        }
    ]


def test_download_failed_clip(simple):
    clips = [failed_clip()]
    res = simple.downloader.download_clips(clips, simple.io, simple.filters)

    assert res == RD_FAILED


def test_download_failed_stream(simple):
    state = {}
    clips = [failed_stream_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, simple.filters)

    assert res == RD_FAILED


def test_print_metadata_failed_clip(simple):
    clips = [failed_clip()]
    metadata = simple.downloader.get_metadata(clips, simple.io)
    parsed_metadata = json.loads(metadata[0])

    assert parsed_metadata == [
        {
            'webpage': 'https://areena.yle.fi/1-1234567',
            'flavors': [
                {
                    'error': failed_clip().flavors[0].streams[0].error_message
                }
            ],
            'embedded_subtitles': [],
            'subtitles': []
        }
    ]

def test_download_fallback(simple):
    state = {}
    clips = [multistream_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, simple.filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == '4'
