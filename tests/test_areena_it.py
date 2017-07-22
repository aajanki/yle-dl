from utils import fetch_title, fetch_stream_url


def test_areena_title():
    title = fetch_title('http://areena.yle.fi/1-1765055')

    assert 'Suomi on ruotsalainen' in title[0]
    assert 'Identiteetti' in title[0]


def test_areena_stream_url():
    streamurl = fetch_stream_url('http://areena.yle.fi/1-1765055')

    assert streamurl
    assert 'manifest.f4m' in streamurl[0]


def test_areena_live_url():
    streamurl = fetch_stream_url('http://areena.yle.fi/tv/suorat/yle-tv1')

    assert streamurl
    assert 'manifest.f4m' in streamurl[0]
