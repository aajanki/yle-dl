from utils import fetch_title, fetch_stream_url


def test_arkisto_title():
    title = fetch_title('https://yle.fi/aihe/artikkeli/2010/10/28'
                        '/studio-julmahuvi-roudasta-rospuuttoon')

    assert 'Roudasta rospuuttoon' in title[0]


def test_arkisto_stream_url():
    streamurl = fetch_stream_url('https://yle.fi/aihe/artikkeli/2010/10/28'
                                 '/studio-julmahuvi-roudasta-rospuuttoon')

    assert streamurl
    assert 'manifest.f4m' in streamurl[0]
