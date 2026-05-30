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
from typing import Optional
from .backends import (
    BaseDownloader,
    DASHHLSBackend,
    HLSAudioBackend,
    SubtitlesOnlyBackend,
)
from .ffmpeg import Ffprobe
from .streamflavor import StreamFlavor, failed_flavor

logger = logging.getLogger('yledl')


def probe_flavors(
    manifest_url: str, is_live: bool, ffprobe: Ffprobe
) -> list[StreamFlavor]:
    try:
        programs = ffprobe.show_programs_for_url(manifest_url)
        return programs_to_stream_flavors(programs, manifest_url, is_live)
    except ValueError as ex:
        return [failed_flavor(f'Failed to probe stream: {str(ex)}')]


def programs_to_stream_flavors(
    programs: dict, manifest_url: str, is_live: bool
) -> list[StreamFlavor]:
    res: list[StreamFlavor] = []
    for program in programs.get('programs', []):
        streams = program.get('streams', [])
        audio_only_stream = all(x.get('codec_type') == 'audio' for x in streams)
        widths = [x['width'] for x in streams if 'width' in x]
        heights = [x['height'] for x in streams if 'height' in x]
        bitrate = program.get('tags', {}).get('variant_bitrate')
        try:
            start_time = float(streams[0].get('start_time')) if streams else None
        except ValueError:
            start_time = None
        if bitrate:
            bitrate = int(bitrate) / 1000
        pid = program.get('program_id')

        backend: BaseDownloader
        if audio_only_stream:
            backend = HLSAudioBackend(manifest_url)
        else:
            backend = DASHHLSBackend(
                manifest_url,
                program_id=pid,
                is_live=is_live,
            )

        res.append(
            StreamFlavor(
                media_type='audio' if audio_only_stream else 'video',
                height=heights[0] if heights else None,
                width=widths[0] if widths else None,
                bitrate=bitrate,
                start_time=start_time,
                streams=[backend],
            )
        )

    has_subtitles, subtitle_start_time = _get_embedded_subtitles(programs)
    if has_subtitles:
        res.append(
            StreamFlavor(
                media_type='subtitle',
                start_time=subtitle_start_time,
                streams=[SubtitlesOnlyBackend(manifest_url)],
            )
        )

    res = _drop_duplicates(res)
    return sorted(res, key=lambda x: (x.height or 0, x.bitrate or 0))


def _get_embedded_subtitles(programs: dict) -> tuple[bool, Optional[float]]:
    for program in programs.get('programs', []):
        for stream in program.get('streams', []):
            if stream.get('codec_type') == 'subtitle':
                # Take (arbitrarily) the start time of the first of subtitle stream.
                # Usually all streams have the same start time so this shouldn't matter.
                return True, float(stream.get('start_time', 0))

    return False, None


def _drop_duplicates(stream_flavors: list[StreamFlavor]) -> list[StreamFlavor]:
    def flavor_key(s: StreamFlavor):
        return (
            s.media_type,
            s.width,
            s.height,
            s.bitrate,
            next((x.url for x in s.streams), None),
        )

    unique = {flavor_key(s): s for s in stream_flavors}
    return list(unique.values())
