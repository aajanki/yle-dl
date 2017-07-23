# -*- coding: utf-8 -*-

import sys
import pytest
from utils import fetch_title, fetch_stream_url


def test_areena_title():
    title = fetch_title('https://areena.yle.fi/1-1765055')

    assert len(title) == 1
    assert 'Suomi on ruotsalainen' in title[0]
    assert 'Identiteetti' in title[0]


def test_areena_stream_url():
    streamurl = fetch_stream_url('https://areena.yle.fi/1-1765055')

    assert len(streamurl) == 1
    assert 'manifest.f4m' in streamurl[0]


@pytest.mark.skipif(sys.version_info < (2,7),
                    reason="SSL broken on Python 2.6")
def test_areena_series_titles():
    titles = fetch_title('https://areena.yle.fi/1-3826480')

    assert len(titles) == 10
    assert all(['Suomi on ruotsalainen' in t for t in titles])


@pytest.mark.skipif(sys.version_info < (2,7),
                    reason="SSL broken on Python 2.6")
def test_areena_series_urls():
    urls = fetch_stream_url('https://areena.yle.fi/1-3826480')

    assert len(urls) == 10
    assert all(['manifest.f4m' in url for url in urls])


def test_areena_live_url():
    streamurl = fetch_stream_url('https://areena.yle.fi/tv/suorat/yle-tv1')

    assert len(streamurl) == 1
    assert 'manifest.f4m' in streamurl[0]


def test_areena_html5_clip_title():
    title = fetch_title('https://areena.yle.fi/1-3523087')

    assert len(title) == 1
    assert 'Metsien kätkemä' in title[0]


def test_areena_html5_clip_stream_url():
    streamurl = fetch_stream_url('https://areena.yle.fi/1-3523087')

    assert len(streamurl) == 1
    assert 'cdnapi.kaltura.com' in streamurl[0]
