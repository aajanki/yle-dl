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

from utils import fetch_title, fetch_stream_url, fetch_metadata


def test_arkisto_title():
    title = fetch_title('https://yle.fi/aihe/artikkeli/2010/10/28'
                        '/studio-julmahuvi-roudasta-rospuuttoon')

    assert 'Roudasta rospuuttoon' in title[0]


def test_arkisto_stream_url():
    streamurls = fetch_stream_url('https://yle.fi/aihe/artikkeli/2010/10/28'
                                 '/studio-julmahuvi-roudasta-rospuuttoon')

    assert len(streamurls) >= 1
    for url in streamurls:
        assert '/manifest.mpd' in url or '.m3u8' in url


def test_arkisto_a_stream_url():
    streamurl = fetch_stream_url('https://yle.fi/aihe/a/20-10001712')

    assert len(streamurl) >= 2
    assert all(('.m3u8' in url or '.mp3' in url) for url in streamurl)


def test_arkisto_regression():
    # There was a regression (#168) related to an invalid downloadUrl
    meta = fetch_metadata('https://yle.fi/aihe/artikkeli/2013/04/11'
                          '/aanien-illoissa-kuunnellaan-kadonneitakin-aania')
    # 12 streams in the article body, possibly more in the footer
    assert len(meta) >= 12
