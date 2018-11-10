# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
from utils import fetch_title, fetch_stream_url, fetch_metadata

def test_arkivet_title():
    title = fetch_title('https://svenska.yle.fi/artikel/2014/06/13'
                        '/halla-det-ar-naturvaktarna')

    assert title
    assert title[0] == 'Seportage om Naturväktarna'


def test_arkivet_stream_url():
    streamurl = fetch_stream_url('https://svenska.yle.fi/artikel/2014/06/13'
                                 '/halla-det-ar-naturvaktarna')
    assert streamurl
    assert 'manifest.f4m' in streamurl[0]


def test_arkivet_metadata():
    metadata = fetch_metadata('https://svenska.yle.fi/artikel/2014/06/13'
                              '/halla-det-ar-naturvaktarna')

    assert len(metadata) == 1
    assert metadata[0].get('title') == 'Seportage om Naturväktarna'
    flavors = metadata[0]['flavors']
    assert all(f.get('media_type') == 'video' for f in flavors)
    assert all('bitrate' in f for f in flavors)
    assert all('height' in f for f in flavors)
    assert all('width' in f for f in flavors)


def test_arkivet_audio_stream_url():
    streamurl = fetch_stream_url('https://svenska.yle.fi/artikel/2014/04/03'
                                 '/tove-jansson-laser-smatrollen-och-'
                                 'den-stora-oversvamningen')
    assert streamurl
    assert streamurl[0].startswith('rtmpe://')


def test_arkivet_audio_metadata():
    metadata = fetch_metadata('https://svenska.yle.fi/artikel/2014/04/03'
                              '/tove-jansson-laser-smatrollen-och-'
                              'den-stora-oversvamningen')

    assert len(metadata) == 2
    for m in metadata:
        assert m.get('title').startswith('Småtrollen')
        assert all(f.get('media_type') == 'audio' for f in m.get('flavors'))
