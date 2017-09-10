# -*- coding: utf-8 -*-

from utils import fetch_title, fetch_stream_url, fetch_metadata


def test_radio_title():
    title = fetch_title('https://areena.yle.fi/1-3361013')

    assert len(title) == 1
    assert 'Tiedeykkönen' in title[0]
    assert ('Suorat aurinkobiopolttoaineet mullistavat energiantuotannon'
            in title[0])


def test_radio_stream_url():
    url = fetch_stream_url('https://areena.yle.fi/1-3361013')

    assert len(url) == 1
    assert 'rtmp' in url[0]

def test_radio_metadata():
    metadata = fetch_metadata('https://areena.yle.fi/1-3361013')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) == 1
    assert metadata[0]['flavors'][0]['media_type'] == 'audio'
    assert metadata[0]['flavors'][0]['bitrate'] == 192
    assert metadata[0]['duration_seconds'] == 2884


def test_radio_live_url():
    url = fetch_stream_url('https://yle.fi/radio/ylepuhe/suora/')

    assert len(url) == 1
    assert 'manifest.f4m' in url[0]


def test_radio_live_url2():
    url = fetch_stream_url('https://yle.fi/radio/radiosuomi/turku/suora/')

    assert len(url) == 1
    assert 'manifest.f4m' in url[0]

def test_radio_live_metadata():
    metadata = fetch_metadata('https://yle.fi/radio/ylepuhe/suora/')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) >= 1
    assert all(f.get('media_type') == 'audio' for f in metadata[0]['flavors'])
