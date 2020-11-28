# -*- coding: utf-8 -*-

from utils import fetch_title, fetch_stream_url, fetch_metadata
from yledl import StreamFilters


def test_radio_title():
    title = fetch_title('https://areena.yle.fi/1-3361013')

    assert len(title) == 1
    assert title[0].startswith(
        'Tiedeykkönen: '
        'Suorat aurinkobiopolttoaineet mullistavat energiantuotannon')


def test_radio_title_hls():
    title = fetch_title('https://areena.yle.fi/1-4551633')

    assert len(title) == 1
    assert title[0].startswith(
        'Tiedeykkönen Extra: Ilmastonmuutos: '
        'Ihminen elää ilman vettä vain muutaman päivän')


def test_radio_stream_url_hls():
    url = fetch_stream_url('https://areena.yle.fi/1-4551633')

    assert len(url) == 1
    assert 'a.mp3' in url[0]


def test_radio_metadata_hls():
    metadata = fetch_metadata('https://areena.yle.fi/1-4551633')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) == 1
    assert metadata[0]['flavors'][0]['media_type'] == 'audio'
    assert metadata[0]['duration_seconds'] == 2954
    assert len(metadata[0]['description']) > 150


def test_radio_live_url():
    url = fetch_stream_url('https://areena.yle.fi/audio/ohjelmat/57-kpDBBz8Pz')

    assert len(url) == 1
    assert '.m3u8' in url[0]


def test_radio_live_url2():
    url = fetch_stream_url(
        'https://areena.yle.fi/audio/ohjelmat/57-3gO4bl7J6?'
        '_c=yle-radio-suomi-oulu')

    assert len(url) == 1
    assert '.m3u8' in url[0]

def test_radio_live_metadata():
    metadata = fetch_metadata('https://areena.yle.fi/audio/ohjelmat/57-kpDBBz8Pz')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) >= 1
    assert all(f.get('media_type') == 'audio' for f in metadata[0]['flavors'])
    assert metadata[0]['title'].startswith('Yle Puhe')


def test_radio_series_2020():
    urls = fetch_stream_url('https://areena.yle.fi/audio/1-50198109')

    assert len(urls) >= 6


def test_radio_metadata_2020():
    metadata = fetch_metadata('https://areena.yle.fi/audio/1-50198110')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) == 1
    assert metadata[0]['flavors'][0]['media_type'] == 'audio'
    assert metadata[0]['duration_seconds'] == 1451
    assert len(metadata[0]['description']) > 150
