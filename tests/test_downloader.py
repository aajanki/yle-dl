import attr
import copy
import logging
import unittest.mock
import pytest
from collections import OrderedDict
from datetime import datetime
from utils import FixedOffset
from yledl import StreamFilters, IOContext, RD_SUCCESS, RD_FAILED
from yledl.backends import BaseDownloader
from yledl.downloader import YleDlDownloader
from yledl.extractors import Clip, FailedClip, StreamFlavor
from yledl.subtitles import EmbeddedSubtitle
from yledl.titleformatter import TitleFormatter


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
        return f'https://example.com/video/{self.id}.mp4'

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


class MockGeoLocation:
    def located_in_finland(self, referrer):
        return True


class MockExtractor:
    def __init__(self, clips_by_url):
        self.clips_by_url = clips_by_url
        self.title_formatter = TitleFormatter()

    def extract(self, url, latest_only):
        return self.clips_by_url.values()

    def get_playlist(self, url, latest_only=False):
        return self.clips_by_url.keys()

    def extract_clip(self, url):
        return self.clips_by_url[url]


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


@attr.frozen
class DownloaderParametersFixture:
    io = attr.field()
    filters = attr.field()


@pytest.fixture
def simple():
    return DownloaderParametersFixture(
        io=IOContext(destdir='/tmp/'),
        filters=StreamFilters()
    )


def downloader(clips_by_url):
    return YleDlDownloader(MockExtractor(clips_by_url), MockGeoLocation())


def test_download_success(simple):
    state = {}
    dl = downloader({'a': successful_clip(state)})
    res = dl.download_clips('', simple.io, simple.filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'high_quality'


def test_download_incomplete_metadata(simple):
    state = {}
    dl = downloader({'a': incomplete_flavors_clip(state)})
    res = dl.download_clips('', simple.io, simple.filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == '3'


def test_download_filter_resolution(simple):
    state = {}
    filters = StreamFilters(maxheight=400)
    dl = downloader({'a': successful_clip(state)})
    res = dl.download_clips('', simple.io, filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'low_quality'


def test_download_filter_exact_resolution(simple):
    state = {}
    filters = StreamFilters(maxheight=720)
    dl = downloader({'a': successful_clip(state)})
    res = dl.download_clips('', simple.io, filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'medium_quality'


def test_download_filter_bitrate1(simple):
    state = {}
    filters = StreamFilters(maxbitrate=1500)
    dl = downloader({'a': successful_clip(state)})
    res = dl.download_clips('', simple.io, filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'medium_quality'


def test_download_filter_bitrate2(simple):
    state = {}
    filters = StreamFilters(maxbitrate=2000)
    dl = downloader({'a': successful_clip(state)})
    res = dl.download_clips('', simple.io, filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'medium_quality_high_bitrate'


def test_download_multiple_filters(simple):
    state = {}
    filters = StreamFilters(maxheight=700, maxbitrate=900)
    dl = downloader({'a': successful_clip(state)})
    res = dl.download_clips('', simple.io, filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == 'low_quality'


def test_pipe_success(simple):
    state = {}
    dl = downloader({'a': successful_clip(state)})
    res = dl.pipe('', simple.io, simple.filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'pipe'
    assert state['stream_id'] == 'high_quality'


def test_print_urls(simple):
    dl = downloader(OrderedDict([
        ('a', successful_clip({})),
        ('b', successful_clip({})),
    ]))
    urls = list(dl.get_urls('', simple.filters))

    assert urls == [
        'https://example.com/video/high_quality.mp4',
        'https://example.com/video/high_quality.mp4'
    ]


def test_print_titles(simple):
    titles = ['Uutiset', 'Pasila: S01E01-2018-07-01T00:00']
    dl = downloader(OrderedDict([
        ('a', successful_clip({}, titles[0])),
        ('b', successful_clip({}, titles[1])),
    ]))

    assert list(dl.get_titles('', False, simple.io)) == titles


def test_print_titles_replaces_whitespace(simple):
    titles = ['   Title with\tall\vkinds\u00a0of\u2003whitespace \t \u00a0 characters']
    expected_titles = ['Title with all kinds of whitespace characters']
    dl = downloader({'a': successful_clip({}, titles[0])})

    assert list(dl.get_titles('', False, simple.io)) == expected_titles


def test_print_metadata(simple):
    dl = downloader({'a': successful_clip({})})
    metadata = dl.get_metadata('', False, simple.io)

    assert len(metadata) == 1

    # Match filename fuzzily because the exact name depends on the existing
    # file names
    assert 'Test clip' in metadata[0]['filename']
    del metadata[0]['filename']
    assert metadata == [
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
    dl = downloader({'a': incomplete_flavors_clip({})})
    metadata = dl.get_metadata('', False, simple.io)

    assert len(metadata) == 1

    # Match filename fuzzily because the exact name depends on the existing
    # file names
    assert 'Test clip' in metadata[0]['filename']
    del metadata[0]['filename']

    assert metadata == [
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
    dl = downloader({'a': failed_clip()})
    res = dl.download_clips('', simple.io, simple.filters)

    assert res == RD_FAILED


def test_download_failed_stream(simple):
    dl = downloader({'a': failed_stream_clip({})})
    res = dl.download_clips('', simple.io, simple.filters)

    assert res == RD_FAILED


def test_print_metadata_failed_clip(simple):
    dl = downloader({'a': failed_clip()})
    metadata = dl.get_metadata('', False, simple.io)

    assert metadata == [
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
    dl = downloader({'a': multistream_clip(state)})
    res = dl.download_clips('', simple.io, simple.filters)

    assert res == RD_SUCCESS
    assert state['command'] == 'download'
    assert state['stream_id'] == '4'


def test_postprocessing_no_log_errors(simple):
    # Smoke test for PR #303
    dl = downloader({'a': successful_clip({})})
    io_postprocess = copy.copy(simple.io)
    io_postprocess.postprocess_command = 'echo'
    logger = logging.getLogger('yledl')
    with unittest.mock.patch.object(logger, 'error') as mock_log_error:
        res = dl.download_clips('', io_postprocess, simple.filters)

        mock_log_error.assert_not_called()

    assert res == RD_SUCCESS
