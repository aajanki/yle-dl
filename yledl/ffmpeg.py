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

import json
import logging
import os.path
import re
import subprocess
from functools import lru_cache
from typing import Tuple
from .errors import FfmpegNotFoundError
from .utils import ffmpeg_loglevel


logger = logging.getLogger('yledl')


class Ffprobe:
    def __init__(self, ffprobe_binary, ffmpeg_binary, x_forwarded_for):
        self.ffprobe_binary = ffprobe_binary
        self.ffmpeg_binary = ffmpeg_binary
        self.x_forwarded_for = x_forwarded_for

    def show_programs_for_url(self, url):
        args = [
            self.ffprobe_binary,
            '-loglevel',
            ffmpeg_loglevel(logger.getEffectiveLevel()),
            '-headers',
            f'X-Forwarded-For: {self.x_forwarded_for}\r\n',
            '-show_programs',
            '-print_format',
            'json=c=1',
            '-analyzeduration',
            '10000000',  # 10 seconds
            '-probesize',
            '80000000',  # bytes
            '-i',
            url,
        ]
        try:
            return json.loads(subprocess.check_output(args).decode('utf-8'))
        except subprocess.CalledProcessError as ex:
            raise ValueError(f'Stream probing failed with status {ex.returncode}')
        except FileNotFoundError:
            raise FfmpegNotFoundError()

    def duration_seconds_file(self, filename):
        args = [
            self.ffmpeg_binary,
            '-stats',
            '-loglevel',
            'fatal',
            '-i',
            f'file:{filename}',
            '-f',
            'null',
            '-',
        ]

        try:
            decoding_result = (
                subprocess.check_output(args, stderr=subprocess.STDOUT)
                .decode('utf-8')
                .rsplit('\r', 1)[-1]
            )
        except subprocess.CalledProcessError as ex:
            raise ValueError(f'Stream probing failed with status {ex.returncode}')
        except UnicodeDecodeError:
            raise ValueError('Unexpected encoding on stream probing response')
        except FileNotFoundError:
            raise FfmpegNotFoundError()

        m = re.search(r'time=(\d\d):(\d\d):(\d\d)\.(\d\d) ', decoding_result)
        if not m:
            raise ValueError('Failed to parse duration in the ffmpeg output')

        return (
            float(m.group(1)) * 60 * 60
            + float(m.group(2)) * 60
            + float(m.group(3))
            + float(m.group(4)) / 100
        )

    def full_stream_already_downloaded(self, filename, clip):
        """Returns True if a stream file called "filename" exists and is complete.

        This calls ffprobe to analyze the file (or returns False if ffprobe is not
        available).
        """
        if not os.path.exists(filename):
            return False

        logger.info(
            f'{filename} already exists.\nChecking if the stream is complete...'
        )

        expected_duration = clip.duration_seconds
        if expected_duration is None or expected_duration <= 0:
            return False

        try:
            downloaded_duration = self.duration_seconds_file(filename)
        except ValueError as ex:
            logger.warning(f'Failed to get duration for the file {filename}: {ex}')
            return False
        except FfmpegNotFoundError:
            logger.warning('ffmpeg not found on path')
            return False

        logger.debug(
            f'Downloaded duration {downloaded_duration} s, expected {expected_duration} s'
        )

        return downloaded_duration >= 0.98 * expected_duration


class NullProbe:
    """Null probe that doesn't do anything.

    Faster than Ffprobe for cases where stream data is not needed.
    """

    def show_programs_for_url(self, _url):
        return {}

    def duration_seconds_file(self, _filename):
        return 0

    def full_stream_already_downloaded(self, _filename, _clip):
        return False


@lru_cache
def ffmpeg_version(ffmpeg_binary: str) -> Tuple[int, int]:
    """Get the ffmpeg application version.

    The parameter ffmpeg_binary is the path to the ffmpeg executable.

    Returns the version as a two-tuple (major, minor). If parsing the version
    number in the ffmpeg output fails, returns an all-zero version (0, 0).

    Throws FfmpegNotFoundError, if ffmpeg application is not found.
    """
    ver = 0, 0
    if ffmpeg_binary:
        args = [ffmpeg_binary, '-loglevel', 'quiet', '-version']
        try:
            p = subprocess.run(args, stdout=subprocess.PIPE, universal_newlines=True)
            if p.returncode == 0:
                first_line = p.stdout.splitlines()[0]
                m = re.match(r'ffmpeg version (\d+)\.(\d+)', first_line)
                if m:
                    ver = int(m.group(1)), int(m.group(2))
        except FileNotFoundError:
            raise FfmpegNotFoundError()

    return ver
