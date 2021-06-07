# -*- coding: utf-8 -*-

from utils import fetch_title, fetch_stream_url, fetch_metadata

def test_arkivet_title():
    title = fetch_title('https://svenska.yle.fi/artikel/2014/06/13'
                        '/halla-det-ar-naturvaktarna')

    assert title
    assert title[0].startswith('Seportage om Naturväktarna')


def test_arkivet_stream_url():
    streamurl = fetch_stream_url('https://svenska.yle.fi/artikel/2014/06/13'
                                 '/halla-det-ar-naturvaktarna')
    assert streamurl
    assert '/a.m3u8' in streamurl[0]


def test_arkivet_metadata():
    metadata = fetch_metadata('https://svenska.yle.fi/artikel/2014/06/13'
                              '/halla-det-ar-naturvaktarna')

    assert len(metadata) == 1
    assert metadata[0].get('title').startswith('Seportage om Naturväktarna')
    flavors = metadata[0]['flavors']
    assert all(f.get('media_type') == 'video' for f in flavors)
    assert all('bitrate' in f for f in flavors)
    assert all('height' in f for f in flavors)
    assert all('width' in f for f in flavors)


def test_arkivet_audio_stream_url():
    streamurl = fetch_stream_url(
        'https://svenska.yle.fi/artikel/2014/01/28'
        '/tove-jansson-laser-noveller-ur-dockskapet')

    assert len(streamurl) == 11
    for url in streamurl:
        assert '/a.mp3' in url


def test_arkivet_audio_metadata():
    metadata = fetch_metadata(
        'https://svenska.yle.fi/artikel/2014/01/28'
        '/tove-jansson-laser-noveller-ur-dockskapet')

    assert len(metadata) == 11
    assert metadata[0].get('title').startswith('Apan ur Dockskåpet')
    for m in metadata:
        assert all(f.get('media_type') == 'audio' for f in m.get('flavors'))


def test_arkivet_a__stream_url():
    streamurl = fetch_stream_url('https://svenska.yle.fi/a/7-884297')
    assert streamurl
    assert '/a.m3u8' in streamurl[0]


def test_arkivet_a_metadata():
    metadata = fetch_metadata('https://svenska.yle.fi/a/7-884297')

    assert len(metadata) >= 4
    assert metadata[1].get('title').startswith('Valborg på Borgbacken')
    flavors = metadata[1]['flavors']
    assert all(f.get('media_type') == 'video' for f in flavors)
    assert all('bitrate' in f for f in flavors)
    assert all('height' in f for f in flavors)
    assert all('width' in f for f in flavors)
