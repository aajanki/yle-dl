from datetime import datetime
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
    # The title changed sometime in Autumn 2021
    t = title[0]
    assert (
        t.startswith('Tiedeykkönen Extra: Ilmastonmuutos: Ihminen elää ilman vettä vain muutaman päivän')
        or t.startswith('Ilmastonmuutoksen vaikutukset: Ihminen elää ilman vettä vain muutaman päivän'))


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


def test_radio_episodes_sort_order():
    metadata = fetch_metadata('https://areena.yle.fi/audio/1-50677839')

    # Should be sorted from oldest to newest
    timestamps = [x['publish_timestamp'] for x in metadata]
    assert len(timestamps) > 1
    assert timestamps == sorted(timestamps)


def test_radio_latest():
    # Test fetching the latest radio episode and also implicitly that
    # getting the latest episode is fast even though there are
    # hundreds of news episodes.
    filters = StreamFilters(latest_only=True)
    metadata = fetch_metadata('https://areena.yle.fi/audio/1-1440981', filters)

    assert len(metadata) == 1

    publish_date = datetime.strptime(metadata[0]['publish_timestamp'][:10], '%Y-%m-%d')
    assert publish_date >= datetime(2021, 1, 1)
