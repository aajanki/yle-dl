from __future__ import print_function, absolute_import, unicode_literals
from utils import fetch_title, fetch_stream_url, fetch_metadata


def test_arkisto_title():
    title = fetch_title('https://yle.fi/aihe/artikkeli/2010/10/28'
                        '/studio-julmahuvi-roudasta-rospuuttoon')

    assert 'Roudasta rospuuttoon' in title[0]


def test_arkisto_stream_url():
    streamurl = fetch_stream_url('https://yle.fi/aihe/artikkeli/2010/10/28'
                                 '/studio-julmahuvi-roudasta-rospuuttoon')

    assert streamurl
    assert '/a.mp4' in streamurl[0]


def test_arkisto_regression():
    # There was a regression (#168) related to an invalid downloadUrl
    meta = fetch_metadata('https://yle.fi/aihe/artikkeli/2013/04/11'
                          '/aanien-illoissa-kuunnellaan-kadonneitakin-aania')
    # 12 streams in the article body, possibly more in the footer
    assert len(meta) >= 12
