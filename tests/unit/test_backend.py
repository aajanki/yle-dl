# This file is part of yle-dl.
#
# Copyright 2010-2026 Antti Ajanki and others
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

from datetime import datetime
from yledl import RD_SUCCESS
from yledl.backends import DASHHLSBackend, WgetBackend
from yledl.clip import Clip
from utils import FixedOffset, MockIOContext

tv1_url = 'https://yletv-lh.akamaihd.net/i/yletv1hls_1@103188/master.m3u8'
io = MockIOContext(destdir='/tmp/')
mock_clip = Clip(
    webpage='https://areena.yle.fi/1-1234567',
    flavors=[],
    title='Test clip: S01E01-2018-07-01T00:00',
    duration_seconds=950,
    region='Finland',
    publish_timestamp=datetime(2018, 7, 1, tzinfo=FixedOffset(3)),
    expiration_timestamp=datetime(2019, 1, 1, tzinfo=FixedOffset(3)),
)


class MockHLSBackend(DASHHLSBackend):
    def __init__(self, url, program_id=None, is_live=False):
        super().__init__(url, program_id, is_live)

        self.executed_commands = None

    def external_downloader(self, commands, env=None):
        self.executed_commands = commands
        return RD_SUCCESS

    def full_stream_already_downloaded(self, filename, clip, io):
        return False


class MockWgetBackend(WgetBackend):
    def __init__(self, url, file_extension):
        super().__init__(url, file_extension)

        self.executed_commands = None

    def external_downloader(self, commands, env=None):
        self.executed_commands = commands
        return RD_SUCCESS

    def full_stream_already_downloaded(self, filename, clip, io):
        return False


def test_hls_backend_save_stream():
    backend = MockHLSBackend(tv1_url, program_id=0)

    res = backend.save_stream('test.mkv', clip=mock_clip, io=io)

    assert res == RD_SUCCESS
    assert len(backend.executed_commands) == 1
    assert tv1_url in backend.executed_commands[0]


def test_hls_backend_pipe():
    backend = MockHLSBackend(tv1_url, program_id=0)

    res = backend.pipe(mock_clip, io)

    assert res == RD_SUCCESS
    assert len(backend.executed_commands) == 1
    assert tv1_url in backend.executed_commands[0]


def test_wget_backend_save_stream():
    backend = MockWgetBackend(tv1_url, file_extension='.mkv')

    res = backend.save_stream('test.mkv', clip=mock_clip, io=io)

    assert res == RD_SUCCESS
    assert len(backend.executed_commands) == 1
    assert tv1_url in backend.executed_commands[0]


def test_wget_backend_pipe():
    backend = MockWgetBackend(tv1_url, file_extension='.mkv')

    res = backend.pipe(mock_clip, io)

    assert res == RD_SUCCESS
    assert len(backend.executed_commands) == 1
    assert tv1_url in backend.executed_commands[0]
