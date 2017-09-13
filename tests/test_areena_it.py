# -*- coding: utf-8 -*-

from utils import fetch_title, fetch_stream_url, fetch_episode_pages, \
    fetch_metadata


def test_areena_akamai_title():
    title = fetch_title('https://areena.yle.fi/1-1765055')

    assert len(title) == 1
    assert 'Suomi on ruotsalainen' in title[0]
    assert 'Identiteetti' in title[0]


def test_areena_akamai_stream_url():
    streamurl = fetch_stream_url('https://areena.yle.fi/1-1765055')

    assert len(streamurl) == 1
    assert 'manifest.f4m' in streamurl[0]


def test_areena_akamai_metadata():
    metadata = fetch_metadata('https://areena.yle.fi/1-1765055')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) == 5
    assert all(f.get('media_type') == 'video' for f in metadata[0]['flavors'])
    assert metadata[0]['duration_seconds'] == 1624
    assert metadata[0]['region'] == 'World'
    assert len(metadata[0]['subtitles']) == 3


def test_areena_html5_stream_url():
    streamurl = fetch_stream_url('https://areena.yle.fi/1-403848')

    assert len(streamurl) == 1
    assert streamurl[0].startswith('https://cdnapisec.kaltura.com/')


def test_areena_html5_metadata():
    metadata = fetch_metadata('https://areena.yle.fi/1-403848')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) == 4
    assert all(f.get('media_type') == 'video' for f in metadata[0]['flavors'])
    assert metadata[0]['duration_seconds'] == 3196
    assert metadata[0]['region'] == 'World'
    assert len(metadata[0]['subtitles']) == 1


def test_areena_series_titles():
    titles = fetch_title('https://areena.yle.fi/1-3826480')

    assert len(titles) == 10
    assert all(['Suomi on ruotsalainen' in t for t in titles])


def test_areena_series_urls():
    urls = fetch_stream_url('https://areena.yle.fi/1-3826480')

    assert len(urls) == 10
    assert all(['manifest.f4m' in url for url in urls])


def test_areena_live_url():
    streamurl = fetch_stream_url('https://areena.yle.fi/tv/suorat/yle-tv1')

    assert len(streamurl) == 1
    assert 'manifest.f4m' in streamurl[0]


def test_areena_live_metadata():
    metadata = fetch_metadata('https://areena.yle.fi/tv/suorat/yle-tv1')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) >= 1
    assert all(f.get('media_type') == 'video' for f in metadata[0]['flavors'])
    assert metadata[0]['region'] == 'Finland'


def test_areena_html5_clip_title():
    title = fetch_title('https://areena.yle.fi/1-3523087')

    assert len(title) == 1
    assert 'Metsien kätkemä' in title[0]


def test_areena_html5_clip_stream_url():
    streamurl = fetch_stream_url('https://areena.yle.fi/1-3523087')

    assert len(streamurl) == 1
    assert streamurl[0].startswith('https://cdnapisec.kaltura.com/')


def test_areena_episode_pages():
    episodes = fetch_episode_pages('https://areena.yle.fi/1-3439855')

    # The first page contains 12 episodes, make sure we get several pages
    assert len(episodes) > 50
    assert all(u.startswith('https://areena.yle.fi/1-') for u in episodes)
