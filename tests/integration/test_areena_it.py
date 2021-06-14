# -*- coding: utf-8 -*-

import pytest
from utils import fetch_title, fetch_stream_url, fetch_episode_pages, \
    fetch_metadata


def test_areena_html5_stream_url():
    streamurl = fetch_stream_url('https://areena.yle.fi/1-787136')

    assert len(streamurl) == 1
    assert '/a.m3u8?' in streamurl[0]


def test_areena_html5_metadata():
    metadata = fetch_metadata('https://areena.yle.fi/1-787136')

    assert len(metadata) == 1
    flavors = metadata[0]['flavors']
    assert len(flavors) >= 5
    assert all(f.get('media_type') == 'video' for f in flavors)
    assert all('bitrate' in f and
               'height' in f and
               'width' in f
               for f in flavors)
    assert metadata[0]['duration_seconds'] == 907
    assert metadata[0]['region'] == 'World'
    assert metadata[0]['publish_timestamp'] == '2021-04-01T00:01:00+03:00'
    assert 'expired_timestamp' not in metadata[0]
    assert len(metadata[0]['description']) > 150


def test_metadata_language():
    meta_fin = fetch_metadata(
        'https://areena.yle.fi/1-403848', meta_language='fin')
    title_fin = meta_fin[0].get('title')
    assert title_fin.startswith('Suomen tie jatkosotaan')

    meta_swe = fetch_metadata(
        'https://areena.yle.fi/1-403848', meta_language='swe')
    title_swe = meta_swe[0].get('title')
    assert title_swe.startswith('Finlands väg till fortsättningskriget')


def test_areena_series_titles():
    titles = fetch_title('https://areena.yle.fi/1-3826480')

    assert len(titles) == 10
    assert all(['Suomi on ruotsalainen' in t for t in titles])


def test_areena_series_urls():
    urls = fetch_stream_url('https://areena.yle.fi/1-3826480')

    assert len(urls) == 10
    assert all(['a.m3u8' in url for url in urls])


@pytest.mark.geoblocked
def test_areena_live_url():
    streamurl = fetch_stream_url('https://areena.yle.fi/tv/suorat/yle-tv1')

    assert len(streamurl) == 1
    assert '.m3u8' in streamurl[0]


@pytest.mark.geoblocked
def test_areena_live_metadata():
    metadata = fetch_metadata('https://areena.yle.fi/tv/suorat/yle-tv1')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) >= 1
    assert all(f.get('media_type') == 'video' for f in metadata[0]['flavors'])
    assert metadata[0]['region'] == 'Finland'


@pytest.mark.geoblocked
def test_areena_ohjelmat_embedded_live_url():
    streamurl = fetch_stream_url('https://areena.yle.fi/tv/ohjelmat/30-595?play=yle-tv2')

    assert len(streamurl) == 1
    assert 'master.m3u8' in streamurl[0]


@pytest.mark.geoblocked
def test_areena_ohjelmat_embedded_live_metadata():
    metadata = fetch_metadata('https://areena.yle.fi/tv/ohjelmat/30-595?play=yle-tv2')

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
    assert '/a.m3u8?' in streamurl[0]


def test_areena_awsmpodamdipv4_stream_url():
    streamurl = fetch_stream_url('https://areena.yle.fi/1-50875269')

    assert len(streamurl) == 1
    assert '/index.m3u8?' in streamurl[0]


def test_areena_awsmpodamdipv4_metadata():
    metadata = fetch_metadata('https://areena.yle.fi/1-50875269')

    assert len(metadata) == 1
    flavors = metadata[0]['flavors']
    assert len(flavors) >= 1
    assert all(f.get('media_type') == 'video' for f in flavors)
    assert metadata[0]['duration_seconds'] == 257
    assert metadata[0]['region'] == 'World'
    assert metadata[0]['publish_timestamp'] == '2021-06-11T08:40:00+03:00'
    assert 'expired_timestamp' not in metadata[0]
    assert len(metadata[0]['description']) > 150


def test_areena_episode_pages():
    episodes = fetch_episode_pages('https://areena.yle.fi/1-3148871')

    # The first page contains 12 episodes, make sure we get several pages
    assert len(episodes) > 20
