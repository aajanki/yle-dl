# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
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
    url = fetch_stream_url('https://areena.yle.fi/radio/ohjelmat/yle-puhe')

    assert len(url) == 1
    assert '.m3u8' in url[0]


def test_radio_live_url2():
    url = fetch_stream_url('https://areena.yle.fi/radio/ohjelmat/'
                           'yle-radio-suomi?_c=yle-radio-suomi-oulu')

    assert len(url) == 1
    assert '.m3u8' in url[0]

def test_radio_live_metadata():
    metadata = fetch_metadata('https://areena.yle.fi/radio/ohjelmat/yle-puhe')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) >= 1
    assert all(f.get('media_type') == 'audio' for f in metadata[0]['flavors'])
