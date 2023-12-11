# This file is part of yle-dl.
#
# Copyright 2010-2022 Antti Ajanki and others
#
# Yle-dl is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Yle-dl is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with yle-dl. If not, see <https://www.gnu.org/licenses/>.

import copy
import logging
import unittest.mock
import pytest
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from unittest.mock import Mock
from utils import FixedOffset
from yledl import StreamFilters, IOContext, RD_SUCCESS, RD_FAILED
from yledl.backends import BaseDownloader, FailingBackend
from yledl.downloader import YleDlDownloader
from yledl.errors import TransientDownloadError
from yledl.extractors import Clip, FailedClip, StreamFlavor
from yledl.titleformatter import TitleFormatter


class MockGeoLocation:
    def located_in_finland(self, referrer):
        return True


class MockExtractor:
    def __init__(self, clips_by_url):
        self.clips_by_url = clips_by_url
        self.title_formatter = TitleFormatter()

    def extract(self, url, latest_only):
        return list(self.clips_by_url.values())

    def get_playlist(self, url, latest_only=False):
        return list(self.clips_by_url.keys())

    def extract_clip(self, url, origin_url):
        return self.clips_by_url[url]


def mock_backend(
        status=RD_SUCCESS,
        name='ffmpeg',
        stream_url='https://areena.example.com/video/areena.mp4'
):
    backend = BaseDownloader()
    backend.name = name
    backend.save_stream = Mock(return_value=status)
    backend.pipe = Mock(return_value=status)
    backend.stream_url = Mock(return_value=stream_url)
    return backend


def backend_that_fails_n_times(n):
    """Return a BaseDownloader instance that first fails and then succeeds.

    The first n calls to save_stream() and pipe() return RD_FAILED and the next
     call after that return RD_SUCCESS.

    save_stream() and pipe() are Mock instances.
    """
    backend = BaseDownloader()
    backend.name = 'ffmpeg'
    return_values = [TransientDownloadError('Failed!')]*n + [RD_SUCCESS]
    backend.save_stream = Mock(side_effect=return_values)
    backend.pipe = Mock(side_effect=return_values)
    return backend


def successful_clip(title='Test clip: S01E01-2018-07-01T00:00'):
    flavors = [
        # The flavors are intentionally unsorted
        StreamFlavor(
            media_type='video',
            height=1080,
            width=1920,
            bitrate=2808,
            streams=[mock_backend(stream_url='https://example.com/video/high_quality.mp4')]
        ),
        StreamFlavor(
            media_type='video',
            height=360,
            width=640,
            bitrate=880,
            streams=[mock_backend(stream_url='https://example.com/video/low_quality.mp4')]
        ),
        StreamFlavor(
            media_type='video',
            height=480,
            width=640,
            bitrate=964,
            streams=[mock_backend(stream_url='https://example.com/video/low_quality_2.mp4')],
        ),
        StreamFlavor(
            media_type='video',
            height=720,
            width=1280,
            bitrate=1412,
            streams=[mock_backend(stream_url='https://example.com/video/medium_quality.mp4')]
        ),
        StreamFlavor(
            media_type='video',
            height=720,
            width=1280,
            bitrate=1872,
            streams=[mock_backend(stream_url='https://example.com/video/medium_quality_high_bitrate.mp4')]
        )
    ]
    return create_clip(flavors, title)


def incomplete_flavors_clip():
    return Clip(
        webpage='https://areena.yle.fi/1-1234567',
        flavors=[
            StreamFlavor(
                media_type='video',
                streams=[mock_backend(stream_url='https://example.com/video/1.mp4')]
            ),
            StreamFlavor(
                media_type='video',
                height=360,
                width=640,
                streams=[mock_backend(stream_url='https://example.com/video/2.mp4')]
            ),
            StreamFlavor(
                media_type='video',
                streams=[mock_backend(stream_url='https://example.com/video/3.mp4')]
            )
        ],
        title='Test clip: S01E01-2018-07-01T00:00',
        duration_seconds=None,
        region='Finland',
        publish_timestamp=None,
        expiration_timestamp=None
    )


def multistream_clip():
    return create_clip([
        StreamFlavor(
            media_type='video',
            height=360,
            width=640,
            bitrate=964,
            streams=[
                FailingBackend('Invalid stream'),
                FailingBackend('Invalid stream'),
                mock_backend(name='wget', stream_url='https://example.com/video/3.mp4'),
                mock_backend(name='ffmpeg', stream_url='https://example.com/video/4.mp4'),
            ]
        )
    ])


def failed_clip():
    return FailedClip('https://areena.yle.fi/1-1234567', 'Failed test clip')


def failed_stream_clip():
    return create_clip([
        StreamFlavor(
            media_type='video',
            height=360,
            width=640,
            bitrate=964,
            streams=[
                FailingBackend('Invalid stream'),
                FailingBackend('Invalid stream')
            ]
        )
    ])


def create_clip(flavors, title='Test clip: S01E01-2018-07-01T00:00'):
    return Clip(
        webpage='https://areena.yle.fi/1-1234567',
        flavors=flavors,
        title=title,
        duration_seconds=950,
        region='Finland',
        publish_timestamp=datetime(2018, 7, 1, tzinfo=FixedOffset(3)),
        expiration_timestamp=datetime(2019, 1, 1, tzinfo=FixedOffset(3)),
    )


@dataclass(frozen=True)
class DownloaderParametersFixture:
    io: IOContext
    filters: StreamFilters


@pytest.fixture
def simple():
    return DownloaderParametersFixture(
        io=IOContext(destdir='/tmp/'),
        filters=StreamFilters()
    )


def downloader(clips_by_url):
    def extractor_factory(*args):
        return MockExtractor(clips_by_url)

    return YleDlDownloader(MockGeoLocation(), TitleFormatter(), None, extractor_factory)


def stream_by_partial_url_match(clip, url_contains):
    for flavor in clip.flavors:
        for stream in flavor.streams:
            if url_contains in stream.stream_url():
                return stream

    return None


def test_download_success(simple):
    clip = successful_clip()
    dl = downloader({'a': clip})
    res = dl.download_clips('', simple.io, simple.filters)

    clip.flavors[0].streams[0].save_stream.assert_called_once()
    assert res == RD_SUCCESS


def test_download_incomplete_metadata(simple):
    clip = incomplete_flavors_clip()
    dl = downloader({'a': clip})
    res = dl.download_clips('', simple.io, simple.filters)

    # flavors[1] is expected to be downloaded because it is the only flavor that
    # has height and width metadata
    clip.flavors[0].streams[0].save_stream.assert_not_called()
    clip.flavors[1].streams[0].save_stream.assert_called_once()
    clip.flavors[2].streams[0].save_stream.assert_not_called()
    assert res == RD_SUCCESS


def test_download_filter_resolution(simple):
    clip = successful_clip()
    filters = StreamFilters(maxheight=400)
    dl = downloader({'a': clip})
    res = dl.download_clips('', simple.io, filters)

    stream_by_partial_url_match(clip, 'low_quality').save_stream.assert_called_once()
    assert res == RD_SUCCESS


def test_download_filter_exact_resolution(simple):
    clip = successful_clip()
    filters = StreamFilters(maxheight=720)
    dl = downloader({'a': clip})
    res = dl.download_clips('', simple.io, filters)

    stream_by_partial_url_match(clip, 'medium_quality').save_stream.assert_called_once()
    assert res == RD_SUCCESS


def test_download_filter_bitrate1(simple):
    clip = successful_clip()
    filters = StreamFilters(maxbitrate=1500)
    dl = downloader({'a': clip})
    res = dl.download_clips('', simple.io, filters)

    stream_by_partial_url_match(clip, 'medium_quality').save_stream.assert_called_once()
    assert res == RD_SUCCESS


def test_download_filter_bitrate2(simple):
    clip = successful_clip()
    filters = StreamFilters(maxbitrate=2000)
    dl = downloader({'a': clip})
    res = dl.download_clips('', simple.io, filters)

    stream_by_partial_url_match(clip, 'medium_quality_high_bitrate').save_stream.assert_called_once()
    assert res == RD_SUCCESS


def test_download_multiple_filters(simple):
    clip = successful_clip()
    filters = StreamFilters(maxheight=700, maxbitrate=900)
    dl = downloader({'a': clip})
    res = dl.download_clips('', simple.io, filters)

    stream_by_partial_url_match(clip, 'low_quality').save_stream.assert_called_once()
    assert res == RD_SUCCESS


def test_pipe_success(simple):
    clip = successful_clip()
    dl = downloader({'a': clip})
    res = dl.pipe('', simple.io, simple.filters)

    stream_by_partial_url_match(clip, 'high_quality').pipe.assert_called_once()
    assert res == RD_SUCCESS


def test_print_urls(simple):
    dl = downloader(OrderedDict([
        ('a', successful_clip()),
        ('b', successful_clip()),
    ]))
    urls = list(dl.get_urls('', simple.io, simple.filters))

    assert urls == [
        'https://example.com/video/high_quality.mp4',
        'https://example.com/video/high_quality.mp4'
    ]


def test_print_titles(simple):
    titles = ['Uutiset', 'Pasila: S01E01-2018-07-01T00:00']
    dl = downloader(OrderedDict([
        ('a', successful_clip(titles[0])),
        ('b', successful_clip(titles[1])),
    ]))

    assert list(dl.get_titles('', simple.io, False)) == titles


def test_print_titles_replaces_whitespace(simple):
    titles = ['   Title with\tall\vkinds\u00a0of\u2003whitespace \t \u00a0 characters']
    expected_titles = ['Title with all kinds of whitespace characters']
    dl = downloader({'a': successful_clip(titles[0])})

    assert list(dl.get_titles('', simple.io, False)) == expected_titles


def test_print_metadata(simple):
    dl = downloader({'a': successful_clip()})
    metadata = dl.get_metadata('', simple.io, False)

    assert len(metadata) == 1

    # Match filename fuzzily because the exact name depends on the existing
    # file names
    assert 'Test clip' in metadata[0]['filename']
    del metadata[0]['filename']
    assert metadata == [
        {
            'webpage': 'https://areena.yle.fi/1-1234567',
            'title': 'Test clip: S01E01-2018-07-01T00:00',
            'episode_title': '',
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
            'subtitles': [],
            'region': 'Finland',
            'publish_timestamp': '2018-07-01T00:00:00+03:00',
            'expiration_timestamp': '2019-01-01T00:00:00+03:00'
        }
    ]


def test_print_metadata_incomplete(simple):
    dl = downloader({'a': incomplete_flavors_clip()})
    metadata = dl.get_metadata('', simple.io, False)

    assert len(metadata) == 1

    # Match filename fuzzily because the exact name depends on the existing
    # file names
    assert 'Test clip' in metadata[0]['filename']
    del metadata[0]['filename']

    assert metadata == [
        {
            'webpage': 'https://areena.yle.fi/1-1234567',
            'title': 'Test clip: S01E01-2018-07-01T00:00',
            'episode_title': '',
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
            'subtitles': []
        }
    ]


def test_download_failed_clip(simple):
    dl = downloader({'a': failed_clip()})
    res = dl.download_clips('', simple.io, simple.filters)

    assert res == RD_FAILED


def test_download_failed_stream(simple):
    dl = downloader({'a': failed_stream_clip()})
    res = dl.download_clips('', simple.io, simple.filters)

    assert res == RD_FAILED


def test_print_metadata_failed_clip(simple):
    dl = downloader({'a': failed_clip()})
    metadata = dl.get_metadata('', simple.io, False)

    assert metadata == [
        {
            'webpage': 'https://areena.yle.fi/1-1234567',
            'flavors': [
                {
                    'error': failed_clip().flavors[0].streams[0].error_message
                }
            ],
            'region': 'Finland',
            'title': '',
            'episode_title': '',
            'subtitles': []
        }
    ]


def test_download_fallback(simple):
    clip = multistream_clip()
    dl = downloader({'a': clip})
    res = dl.download_clips('', simple.io, simple.filters)

    clip.flavors[0].streams[3].save_stream.assert_called_once()
    assert res == RD_SUCCESS


def test_postprocessing_no_log_errors(simple):
    # Smoke test for PR #303
    dl = downloader({'a': successful_clip()})
    io_postprocess = copy.copy(simple.io)
    io_postprocess.postprocess_command = 'echo'
    logger = logging.getLogger('yledl')
    with unittest.mock.patch.object(logger, 'error') as mock_log_error:
        res = dl.download_clips('', io_postprocess, simple.filters)

        mock_log_error.assert_not_called()

    assert res == RD_SUCCESS


def test_download_successful_after_retry(simple):
    backend = backend_that_fails_n_times(2)
    flavors = [
        StreamFlavor(
            media_type='video',
            height=1080,
            width=1920,
            bitrate=2808,
            streams=[backend]
        )
    ]
    dl = downloader({'a': create_clip(flavors)})

    res = dl.download_clips('', simple.io, simple.filters)

    assert res == RD_SUCCESS
    assert backend.save_stream.call_count == 3


def test_download_fails_if_too_many_failures(simple):
    backend = backend_that_fails_n_times(10)
    flavors = [
        StreamFlavor(
            media_type='video',
            height=1080,
            width=1920,
            bitrate=2808,
            streams=[backend]
        )
    ]
    dl = downloader({'a': create_clip(flavors)})

    res = dl.download_clips('', simple.io, simple.filters)

    assert res == RD_FAILED
    assert backend.save_stream.call_count >= 4


def test_pipe_does_not_retry(simple):
    backend = backend_that_fails_n_times(1)
    flavors = [
        StreamFlavor(
            media_type='video',
            height=1080,
            width=1920,
            bitrate=2808,
            streams=[backend]
        )
    ]
    dl = downloader({'a': create_clip(flavors)})

    res = dl.pipe('', simple.io, simple.filters)

    assert res == RD_FAILED
