from utils import fetch_metadata


def test_uutiset_main_media_metadata():
    # This page has a video embedded as "mainMedia"
    metadata = fetch_metadata('https://yle.fi/uutiset/3-11822823')

    assert len(metadata) == 1
    assert metadata[0]['webpage'] == 'https://areena.yle.fi/1-50653021'
    assert metadata[0]['title'].startswith('Perjantai-dokkari: Tuomas, vaatimaton maailmantähti')
    assert metadata[0]['duration_seconds'] == 690
    assert metadata[0]['region'] == 'World'
    assert metadata[0]['publish_timestamp'] == '2021-03-05T21:30:00+02:00'
    assert 'expired_timestamp' not in metadata[0]
    assert len(metadata[0]['description']) > 150

    flavors = metadata[0]['flavors']
    assert len(flavors) >= 3
    assert all(f.get('media_type') == 'video' for f in flavors)
    assert all('bitrate' in f and
               'height' in f and
               'width' in f
               for f in flavors)


def test_uutiset_headline_metadata():
    # This page has a video embedded as "headline.video"
    metadata = fetch_metadata('https://yle.fi/uutiset/3-12328632')

    assert len(metadata) == 1
    assert metadata[0]['webpage'] == 'https://areena.yle.fi/1-61842917'
    assert metadata[0]['title'].startswith('Uutisvideot: Presidentti Sauli Niinistö')
    assert metadata[0]['duration_seconds'] == 49
    assert metadata[0]['region'] == 'World'
    assert metadata[0]['publish_timestamp'] == '2022-02-22T14:36:36+02:00'
    assert 'expired_timestamp' not in metadata[0]
    assert len(metadata[0]['description']) > 100

    flavors = metadata[0]['flavors']
    assert len(flavors) >= 1
    assert all(f.get('media_type') == 'video' for f in flavors)


def test_uutiset_inline_audio_block_metadata():
    # This page has an inline AudioBlock
    metadata = fetch_metadata('https://yle.fi/uutiset/3-11843834')

    assert len(metadata) == 1
    assert metadata[0]['webpage'] == 'https://areena.yle.fi/1-50762351'
    assert metadata[0]['title'].startswith('Ykkösaamun kolumni: Janne Saarikivi: On kriisi')
    assert metadata[0]['duration_seconds'] == 333
    assert metadata[0]['region'] == 'World'
    assert metadata[0]['publish_timestamp'] == '2021-03-23T07:00:00+02:00'
    assert 'expired_timestamp' not in metadata[0]
    assert len(metadata[0]['description']) > 150

    flavors = metadata[0]['flavors']
    assert len(flavors) >= 1
    assert all(f.get('media_type') == 'audio' for f in flavors)
    assert all('bitrate' in f for f in flavors)
