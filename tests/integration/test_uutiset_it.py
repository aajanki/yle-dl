# This file is part of yle-dl.
#
# Copyright 2010-2024 Antti Ajanki and others
#
# Yle-dl is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Yle-dl is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with yle-dl. If not, see <https://www.gnu.org/licenses/>.

from utils import fetch_metadata


def test_uutiset_main_media_metadata():
    # This page has a video embedded as "mainMedia"
    metadata = fetch_metadata('https://yle.fi/a/3-11822823')

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
    metadata = fetch_metadata('https://yle.fi/a/3-12328632')

    assert len(metadata) == 1
    assert metadata[0]['webpage'] == 'https://areena.yle.fi/1-61842917'
    assert metadata[0]['title'].startswith('Uutisvideot 2022: Presidentti Sauli Niinistö')
    assert metadata[0]['duration_seconds'] == 49
    assert metadata[0]['region'] == 'World'
    assert metadata[0]['publish_timestamp'] == '2022-02-22T14:36:36+02:00'
    assert 'expired_timestamp' not in metadata[0]
    assert len(metadata[0]['description']) > 100

    flavors = metadata[0]['flavors']
    assert len(flavors) >= 1
    assert all(f.get('media_type') == 'video' for f in flavors)


def test_uutiset_inline_video_block_metadata():
    # This page has two videos embedded as inline blocks
    metadata = fetch_metadata('https://yle.fi/a/74-20036911')

    assert len(metadata) == 2
    assert metadata[0]['title'].startswith('Minuutin uutisvideot: Kymmenien ihmisten ryhmissä kuljetaan pummilla')
    assert metadata[0]['duration_seconds'] == 48
    assert metadata[1]['title'].startswith('Uutisvideot: Raitiovaunuliikennettä Helsingin Hakaniemessä')
    assert metadata[1]['duration_seconds'] == 14

    flavors = metadata[0]['flavors'] + metadata[1]['flavors']
    assert len(flavors) >= 1
    assert all(f.get('media_type') == 'video' for f in flavors)


def test_uutiset_inline_audio_block_metadata():
    # This page has an inline AudioBlock
    metadata = fetch_metadata('https://yle.fi/a/3-11843834')

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


def test_uutiset_svenska():
    metadata = fetch_metadata('https://svenska.yle.fi/a/7-10023932')

    assert len(metadata) >= 1
    assert metadata[0]['webpage'] == 'https://areena.yle.fi/1-64379365'
    assert metadata[0]['title'].startswith('Yle Nyheter')
    assert metadata[0]['duration_seconds'] == 73
    assert metadata[0]['region'] == 'World'
    assert metadata[0]['publish_timestamp'] == '2022-12-05T12:28:13+02:00'
    assert 'expired_timestamp' not in metadata[0]

    flavors = metadata[0]['flavors']
    assert len(flavors) >= 1
    assert all(f.get('media_type') == 'video' for f in flavors)


def test_uutiset_metadata_old_address():
    # Before Nov 2022, news articles were published at /uutiset/
    # instead of /a/
    metadata = fetch_metadata('https://yle.fi/uutiset/74-20006891')

    assert len(metadata) == 1
    assert metadata[0]['webpage'] == 'https://areena.yle.fi/1-64358035'
    assert metadata[0]['title'].startswith('Puoli seitsemän: Neljä pukeutumisvinkkiä talvipyöräilyyn')
    assert metadata[0]['duration_seconds'] == 74
    assert metadata[0]['region'] == 'World'
    assert metadata[0]['publish_timestamp'] == '2022-12-02T10:09:44+02:00'
    assert 'expired_timestamp' not in metadata[0]

    flavors = metadata[0]['flavors']
    assert len(flavors) >= 1
    assert all(f.get('media_type') == 'video' for f in flavors)
