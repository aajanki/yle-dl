# -*- coding: utf-8 -*-

from utils import fetch_title, fetch_stream_url


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


def test_radio_live_url():
    url = fetch_stream_url('https://yle.fi/radio/ylepuhe/suora/')

    assert len(url) == 1
    assert 'manifest.f4m' in url[0]


def test_radio_live_url2():
    url = fetch_stream_url('https://yle.fi/radio/radiosuomi/turku/suora/')

    assert len(url) == 1
    assert 'manifest.f4m' in url[0]
