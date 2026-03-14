# This file is part of yle-dl.
#
# Copyright 2010-2025 Antti Ajanki and others
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

import subprocess
from unittest.mock import patch
import pytest
from yledl.ffmpeg import Ffprobe


def create_ffprobe():
    return Ffprobe(
        ffprobe_binary='ffprobe',
        ffmpeg_binary='ffmpeg',
        x_forwarded_for='1.2.3.4',
    )


class TestShowProgramsForUrl:
    def test_timeout_raises_value_error(self):
        ffprobe = create_ffprobe()

        with patch('yledl.ffmpeg.subprocess.check_output') as mock_check_output:
            mock_check_output.side_effect = subprocess.TimeoutExpired(
                cmd='ffprobe', timeout=20
            )

            with pytest.raises(ValueError, match='Stream probing timed out'):
                ffprobe.show_programs_for_url('https://example.com/master.m3u8')

    def test_successful_probe(self):
        ffprobe = create_ffprobe()
        mock_output = b'{"programs": [{"program_id": 0, "streams": []}]}'

        with patch('yledl.ffmpeg.subprocess.check_output') as mock_check_output:
            mock_check_output.return_value = mock_output

            result = ffprobe.show_programs_for_url('https://example.com/master.m3u8')

            assert result == {'programs': [{'program_id': 0, 'streams': []}]}
            call_kwargs = mock_check_output.call_args[1]
            assert call_kwargs['timeout'] == 20

    def test_called_process_error_raises_value_error(self):
        ffprobe = create_ffprobe()

        with patch('yledl.ffmpeg.subprocess.check_output') as mock_check_output:
            mock_check_output.side_effect = subprocess.CalledProcessError(
                returncode=1, cmd='ffprobe'
            )

            with pytest.raises(ValueError, match='Stream probing failed'):
                ffprobe.show_programs_for_url('https://example.com/master.m3u8')


class TestDurationSecondsFile:
    def test_timeout_raises_value_error(self):
        ffprobe = create_ffprobe()

        with patch('yledl.ffmpeg.subprocess.check_output') as mock_check_output:
            mock_check_output.side_effect = subprocess.TimeoutExpired(
                cmd='ffmpeg', timeout=180
            )

            with pytest.raises(ValueError, match='Duration probing timed out'):
                ffprobe.duration_seconds_file('/tmp/test.mkv')

    def test_successful_duration_probe(self):
        ffprobe = create_ffprobe()
        mock_output = b'frame=0\rsize=     123kB time=01:23:45.67 bitrate= 200.0kbits/s'

        with patch('yledl.ffmpeg.subprocess.check_output') as mock_check_output:
            mock_check_output.return_value = mock_output

            result = ffprobe.duration_seconds_file('/tmp/test.mkv')

            assert result == 1 * 3600 + 23 * 60 + 45 + 0.67
            call_kwargs = mock_check_output.call_args[1]
            assert call_kwargs['timeout'] is not None
