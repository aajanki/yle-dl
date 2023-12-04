# This file is part of yle-dl.
#
# Copyright 2010-2022 Antti Ajanki and others
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

import pytest
from datetime import datetime
from utils import fetch_title, fetch_stream_url, fetch_metadata
from yledl import StreamFilters


def test_radio_title():
    title = fetch_title('https://areena.yle.fi/1-3361013')

    assert len(title) == 1
    assert title[0].startswith(
        'Tiedeykkönen: '
        'Suorat aurinkobiopolttoaineet mullistavat energiantuotannon')


def test_radio_stream_url_hls():
    url = fetch_stream_url('https://areena.yle.fi/1-4551633')

    assert len(url) == 1
    assert '.mp3' in url[0]


def test_radio_metadata_hls():
    metadata = fetch_metadata('https://areena.yle.fi/1-4551633')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) >= 1
    assert metadata[0]['flavors'][0]['media_type'] == 'audio'
    assert metadata[0]['duration_seconds'] == 2954
    assert len(metadata[0]['description']) > 150


@pytest.mark.geoblocked
def test_radio_live_url():
    url = fetch_stream_url('https://areena.yle.fi/podcastit/ohjelmat/57-kpDBBz8Pz')

    assert len(url) == 1
    assert '.m3u8' in url[0]


@pytest.mark.geoblocked
def test_radio_live_url2():
    url = fetch_stream_url(
        'https://areena.yle.fi/podcastit/ohjelmat/57-3gO4bl7J6?'
        '_c=yle-radio-suomi-oulu')

    assert len(url) == 1
    assert '.m3u8' in url[0]


@pytest.mark.geoblocked
def test_radio_live_metadata():
    metadata = fetch_metadata('https://areena.yle.fi/podcastit/ohjelmat/57-kpDBBz8Pz')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) >= 1
    assert all(f.get('media_type') == 'audio' for f in metadata[0]['flavors'])
    assert metadata[0]['title'].startswith('Yle Puhe')


def test_radio_series_2020():
    urls = fetch_stream_url('https://areena.yle.fi/podcastit/1-50198109')

    assert len(urls) >= 6


def test_radio_series_redirect():
    # Will get redirected to https://areena.yle.fi/podcastit/1-61070264
    urls = fetch_stream_url('https://areena.yle.fi/1-61070264')

    assert len(urls) >= 10


def test_radio_series_redirect_from_old_audio_url():
    # The address for radio programs was changed from /audio/ to /podcastit/
    # in September 2022. Test that the old address is redirected to the new.
    urls = fetch_stream_url('https://areena.yle.fi/audio/1-61070277')

    assert len(urls) == 1
    assert '.mp3' in urls[0]


def test_radio_metadata_2020():
    metadata = fetch_metadata('https://areena.yle.fi/podcastit/1-50198110')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) >= 1
    assert metadata[0]['flavors'][0]['media_type'] == 'audio'
    assert metadata[0]['duration_seconds'] == 1451
    assert len(metadata[0]['description']) > 150


def test_radio_metadata_media_id_78():
    # This has a media_id starting with 78-
    metadata = fetch_metadata('https://areena.yle.fi/podcastit/1-65772446')

    assert len(metadata) == 1
    assert len(metadata[0]['flavors']) >= 1
    assert not any('error' in fl for fl in metadata[0]['flavors'])
    assert metadata[0]['flavors'][0]['media_type'] == 'audio'
    assert metadata[0]['duration_seconds'] == 1769
    assert len(metadata[0]['description']) > 150


def test_radio_episodes_sort_order_latest_last_source():
    # This page lists episodes in the latest-last order
    metadata = fetch_metadata('https://areena.yle.fi/podcastit/1-50375734')

    # Should be sorted from oldest to newest
    timestamps = [x['publish_timestamp'] for x in metadata]
    assert len(timestamps) > 1
    assert timestamps == sorted(timestamps)


def test_radio_latest():
    # Test fetching the latest radio episode.
    filters = StreamFilters(latest_only=True)
    metadata = fetch_metadata('https://areena.yle.fi/podcastit/1-4442351', filters)

    assert len(metadata) == 1

    publish_date = datetime.strptime(metadata[0]['publish_timestamp'][:10], '%Y-%m-%d')
    assert publish_date >= datetime(2022, 8, 7)


def test_radio_return_empty_list_if_there_are_no_episodes():
    # This series has no published episodes
    metadata = fetch_metadata('https://areena.yle.fi/podcastit/1-3114806')

    assert len(metadata) == 0
