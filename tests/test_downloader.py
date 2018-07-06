# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr
import copy
import os
import pytest
from yledl import YleDlDownloader, Clip, FailedClip, BaseDownloader, \
    StreamFlavor, StreamFilters, Subtitle, IOContext, BackendFactory, \
    RD_SUCCESS, RD_FAILED
from utils import Capturing


download_state = {'command': None, 'stream_id': None}


def clear_state():
    global download_state
    download_state = {'command': None, 'stream_id': None}


class StateCollectingBackend(BaseDownloader):
    def __init__(self, id):
        BaseDownloader.__init__(self, '.mp4')
        self.id = id

    def save_stream(self, clip_title, io):
        global download_state
        download_state['command'] = 'download'
        download_state['stream_id'] = self.id

        return RD_SUCCESS

    def pipe(self, io, subtitle_url):
        global download_state
        download_state['command'] = 'pipe'
        download_state['stream_id'] = self.id

        return RD_SUCCESS

    def next_available_filename(self, proposed):
        return proposed

    def warn_on_unsupported_feature(self, io):
        pass


class MockStream(object):
    def __init__(self, id):
        self.id = id

    def is_valid(self):
        return True

    def get_error_message(self):
        return None

    def to_url(self):
        return 'https://example.com/video/{}.mp4'.format(self.id)

    def create_downloader(self, backends):
        return StateCollectingBackend(self.id)


def successful_clip(title='Test clip: S01E01-2018-07-01T00:00'):
    return Clip(
        webpage='https://areena.yle.fi/1-1234567',
        flavors=[
            StreamFlavor(
                media_type='video',
                height=360,
                width=640,
                bitrate=880,
                streams=[MockStream('1')]
            ),
            StreamFlavor(
                media_type='video',
                height=720,
                width=1280,
                bitrate=1412,
                streams=[MockStream('2')]
            ),
            StreamFlavor(
                media_type='video',
                height=1080,
                width=1920,
                bitrate=2808,
                streams=[MockStream('3')]
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


def failed_clip():
    return FailedClip('https://areena.yle.fi/1-1234567', 'Failed test clip')


@attr.s
class DownloaderParametersFixture(object):
    io = attr.ib()
    filters = attr.ib()
    downloader = attr.ib()


@pytest.fixture
def simple():
    clear_state()

    return DownloaderParametersFixture(
        io=IOContext(destdir='/tmp/'),
        filters=StreamFilters(),
        downloader=YleDlDownloader([BackendFactory.ADOBEHDSPHP])
    )


def test_download_success(simple):
    global download_state

    clips = [successful_clip()]
    res = simple.downloader.download_episodes(
        clips, simple.io, simple.filters, None)

    assert res == RD_SUCCESS
    assert download_state['command'] == 'download'
    assert download_state['stream_id'] == '1'


def test_pipe_success(simple):
    global download_state

    clips = [successful_clip()]
    res = simple.downloader.pipe(clips, simple.io, simple.filters)

    assert res == RD_SUCCESS
    assert download_state['command'] == 'pipe'
    assert download_state['stream_id'] == '1'


def test_print_urls(simple):
    clips = [successful_clip()]

    res = None
    with Capturing() as output:
        res = simple.downloader.print_urls(clips, simple.filters)

    assert res == RD_SUCCESS
    assert output == ['https://example.com/video/1.mp4']


def test_print_titles(simple):
    titles = ['Uutiset', 'Pasila: S01E01-2018-07-01T00:00']
    clips = [successful_clip(t) for t in titles]

    res = None
    with Capturing() as output:
        res = simple.downloader.print_titles(clips, simple.io, simple.filters)

    assert res == RD_SUCCESS
    assert output == titles


def test_download_failed_clip(simple):
    global download_state

    clips = [failed_clip()]
    res = simple.downloader.download_episodes(
        clips, simple.io, simple.filters, None)

    assert res == RD_FAILED
    assert download_state['command'] == None
    assert download_state['stream_id'] == None
