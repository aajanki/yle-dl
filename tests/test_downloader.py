# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr
import json
import pytest
from yledl import StreamFilters, IOContext, RD_SUCCESS, RD_FAILED
from yledl.backends import BaseDownloader
from yledl.downloader import YleDlDownloader, SubtitleDownloader
from yledl.extractors import Clip, FailedClip, StreamFlavor, Subtitle
from yledl.streams import InvalidStream


class StateCollectingBackend(BaseDownloader):
    def __init__(self, state_dict, id, name):
        BaseDownloader.__init__(self, '.mp4')
        self.id = id
        self.state_dict = state_dict
        self.name = name

    def save_stream(self, clip_title, io):
        self.state_dict['command'] = 'download'
        self.state_dict['stream_id'] = self.id
        self.state_dict['backend'] = self.name

        return RD_SUCCESS

    def pipe(self, io, subtitle_url):
        self.state_dict['command'] = 'pipe'
        self.state_dict['stream_id'] = self.id
        self.state_dict['backend'] = self.name

        return RD_SUCCESS

    def next_available_filename(self, proposed):
        return proposed

    def warn_on_unsupported_feature(self, io):
        pass


class FailingBackend(StateCollectingBackend):
    def save_stream(self, clip_title, io):
        return RD_FAILED

    def pipe(self, io, subtitle_url):
        return RD_FAILED


class MockStream(object):
    def __init__(self, state_dict, id, backend_name='ffmpeg'):
        self.id = id
        self.state_dict = state_dict
        self.backend_name = backend_name

    def is_valid(self):
        return True

    def get_error_message(self):
        return None

    def to_url(self):
        return 'https://example.com/video/{}.mp4'.format(self.id)

    def create_downloader(self):
        return StateCollectingBackend(self.state_dict, self.id, self.backend_name)


class FailingStream(MockStream):
    def create_downloader(self):
        return FailingBackend(self.state_dict, self.id, self.backend_name)


class MockSubtitleDownloader(SubtitleDownloader):
    def download(self, subtitles, videofilename):
        # Don't actually download anything
        return []


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
                streams=[MockStream(state_dict, 'high_quality')]
            ),
            StreamFlavor(
                media_type='video',
                height=360,
                width=640,
                bitrate=880,
                streams=[MockStream(state_dict, 'low_quality')]
            ),
            StreamFlavor(
                media_type='video',
                height=360,
                width=640,
                bitrate=864,
                streams=[MockStream(state_dict, 'low_quality_finnish_subs')],
                hard_subtitle=Subtitle(url=None, lang='fi')
            ),
            StreamFlavor(
                media_type='video',
                height=720,
                width=1280,
                bitrate=1412,
                streams=[MockStream(state_dict, 'medium_quality')]
            ),
            StreamFlavor(
                media_type='video',
                height=720,
                width=1280,
                bitrate=1872,
                streams=[MockStream(state_dict, 'medium_quality_high_bitrate')]
            )
        ],
        title=title,
        duration_seconds=950,
        region='Finland',
        publish_timestamp='2018-07-01T00:00:00+03:00',
        expiration_timestamp='2019-01-01T00:00:00+03:00',
        subtitles=[
            Subtitle('https://example.com/subtitle/fin.srt', 'fin'),
            Subtitle('https://example.com/subtitle/swe.srt', 'swe')
        ]
    )


def incomplete_flavors_clip(state_dict):
    return Clip(
        webpage='https://areena.yle.fi/1-1234567',
        flavors=[
            StreamFlavor(
                media_type='video',
                streams=[MockStream(state_dict, '1')]
            ),
            StreamFlavor(
                media_type='video',
                height=360,
                width=640,
                streams=[MockStream(state_dict, '2')]
            ),
            StreamFlavor(
                media_type='video',
                streams=[MockStream(state_dict, '3')]
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
                bitrate=864,
                streams=[
                    FailingStream(state_dict, '1', 'wget'),
                    InvalidStream('Invalid stream'),
                    MockStream(state_dict, '3', 'wget'),
                    MockStream(state_dict, '4', 'youtubedl')
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
                bitrate=864,
                streams=[
                    FailingStream(state_dict, '1', 'wget'),
                    FailingStream(state_dict, '2', 'ffmpeg')
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
        io=IOContext(destdir='/tmp/', rtmpdump_binary='rtmpdump'),
        filters=StreamFilters(),
        downloader=YleDlDownloader(MockSubtitleDownloader()))


def test_download_success(simple):
    state = {}
    clips = [successful_clip(state)]
    res = simple.downloader.download_clips(
        clips, simple.io, simple.filters, None)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'high_quality'


def test_download_incomplete_metadata(simple):
    state = {}
    clips = [incomplete_flavors_clip(state)]
    res = simple.downloader.download_clips(
        clips, simple.io, simple.filters, None)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == '3'


def test_download_filter_resolution(simple):
    state = {}
    filters = StreamFilters(maxheight=700)
    clips = [successful_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, filters, None)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'low_quality'


def test_download_filter_exact_resolution(simple):
    state = {}
    filters = StreamFilters(maxheight=720)
    clips = [successful_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, filters, None)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'medium_quality'


def test_download_filter_bitrate1(simple):
    state = {}
    filters = StreamFilters(maxbitrate=1500)
    clips = [successful_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, filters, None)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'medium_quality'


def test_download_filter_bitrate2(simple):
    state = {}
    filters = StreamFilters(maxbitrate=2000)
    clips = [successful_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, filters, None)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'medium_quality_high_bitrate'


def test_download_multiple_filters(simple):
    state = {}
    filters = StreamFilters(maxheight=720, maxbitrate=1000)
    clips = [successful_clip(state)]
    res = simple.downloader.download_clips(clips, simple.io, filters, None)

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


def test_print_metadata(simple):
    state = {}
    clips = [successful_clip(state)]
    metadata = simple.downloader.get_metadata(clips)
    parsed_metadata = json.loads(metadata[0])

    assert len(metadata) == 1
    assert parsed_metadata == [
        {
            'webpage': 'https://areena.yle.fi/1-1234567',
            'title': 'Test clip: S01E01-2018-07-01T00:00',
            'flavors': [
                {
                    'media_type': 'video',
                    'height': 360,
                    'width': 640,
                    'bitrate': 864,
                    'hard_subtitle_language': 'fin',
                    'backends': ['ffmpeg']
                },
                {
                    'media_type': 'video',
                    'height': 360,
                    'width': 640,
                    'bitrate': 880,
                    'backends': ['ffmpeg']
                },
                {
                    'media_type': 'video',
                    'height': 720,
                    'width': 1280,
                    'bitrate': 1412,
                    'backends': ['ffmpeg']
                },
                {
                    'media_type': 'video',
                    'height': 720,
                    'width': 1280,
                    'bitrate': 1872,
                    'backends': ['ffmpeg']
                },
                {
                    'media_type': 'video',
                    'height': 1080,
                    'width': 1920,
                    'bitrate': 2808,
                    'backends': ['ffmpeg']
                }
            ],
            'duration_seconds': 950,
            'subtitles': [
                {'url': 'https://example.com/subtitle/fin.srt', 'lang': 'fin'},
                {'url': 'https://example.com/subtitle/swe.srt', 'lang': 'swe'}
            ],
            'region': 'Finland',
            'publish_timestamp': '2018-07-01T00:00:00+03:00',
            'expiration_timestamp': '2019-01-01T00:00:00+03:00'
        }
    ]


def test_print_metadata_incomplete(simple):
    state = {}
    clips = [incomplete_flavors_clip(state)]
    metadata = simple.downloader.get_metadata(clips)
    parsed_metadata = json.loads(metadata[0])

    assert len(metadata) == 1
    assert parsed_metadata == [
        {
            'webpage': 'https://areena.yle.fi/1-1234567',
            'title': 'Test clip: S01E01-2018-07-01T00:00',
            'flavors': [
                {
                    'media_type': 'video',
                    'backends': ['ffmpeg']
                },
                {
                    'media_type': 'video',
                    'height': 360,
                    'width': 640,
                    'backends': ['ffmpeg']
                },
                {
                    'media_type': 'video',
                    'backends': ['ffmpeg']
                }
            ],
            'region': 'Finland',
            'subtitles': []
        }
    ]


def test_download_failed_clip(simple):
    clips = [failed_clip()]
    res = simple.downloader.download_clips(
        clips, simple.io, simple.filters, None)

    assert res == RD_FAILED


def test_download_failed_stream(simple):
    state = {}
    clips = [failed_stream_clip(state)]
    res = simple.downloader.download_clips(
        clips, simple.io, simple.filters, None)

    assert res == RD_FAILED


def test_download_fallback(simple):
    state = {}
    clips = [multistream_clip(state)]
    res = simple.downloader.download_clips(
        clips, simple.io, simple.filters, None)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == '3'
