# -*- coding: utf-8 -*-

from utils import fetch_title, fetch_stream_url


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
