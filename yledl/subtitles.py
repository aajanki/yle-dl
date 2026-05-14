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

import logging
import re
import os.path
from dataclasses import dataclass
from .ffmpeg import optional_stream
from .subprocess import execute_pipe
from .utils import ffmpeg_loglevel

logger = logging.getLogger('yledl')


@dataclass(frozen=True)
class Subtitle:
    url: str
    lang: str
    category: str


def delay_substitles_srt(filename: str, delay_ms: int):
    """Delay subtitle lines in an .srt file by delay_ms milliseconds."""
    logger.debug(f'delaying subtitles by {delay_ms} ms')

    with open(filename, encoding='utf-8') as f:
        content = f.read()
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(delay_substitles_srt_text(content, delay_ms))


def delay_substitles_srt_text(text: str, delay_ms: int) -> str:
    time_re = re.compile(
        r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})'
    )

    def ms_to_srt(ms):
        ms = max(0, ms)
        h, ms = divmod(ms, 3_600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'

    def shift(match):
        start = (
            int(match.group(1)) * 3600 + int(match.group(2)) * 60 + int(match.group(3))
        ) * 1000 + int(match.group(4))
        end = (
            int(match.group(5)) * 3600 + int(match.group(6)) * 60 + int(match.group(7))
        ) * 1000 + int(match.group(8))
        return f'{ms_to_srt(start + delay_ms)} --> {ms_to_srt(end + delay_ms)}'

    return time_re.sub(shift, text)


def delay_subtitles_mkv(
    filename: str, delay_ms: int, ffmpeg_binary: str, ffmpeg_version: tuple[int, int]
):
    """Delay subtitle lines in a .mkv file by delay_ms milliseconds."""
    logger.debug(f'delaying subtitles by {delay_ms} ms')

    delay_s = delay_ms / 1000.0
    sub_spec = optional_stream('1:s', ffmpeg_version)
    base, ext = os.path.splitext(filename)
    tmp = base + '.tmp_subdelay' + ext
    args = [
        ffmpeg_binary,
        '-y',
        '-loglevel',
        ffmpeg_loglevel(logger.getEffectiveLevel()),
        '-i',
        f'file:{filename}',
        '-itsoffset',
        str(delay_s),
        '-i',
        f'file:{filename}',
        '-map',
        '0:v',
        '-map',
        '0:a',
        '-map',
        sub_spec,
        '-c',
        'copy',
        f'file:{tmp}',
    ]
    ret = execute_pipe([args])
    if ret == 0:
        os.replace(tmp, filename)
    else:
        logger.warning('Failed to apply subtitle delay')
        if os.path.exists(tmp):
            os.remove(tmp)
