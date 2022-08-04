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

import logging
from .backends import DASHHLSBackend
from .streamflavor import StreamFlavor, FailedFlavor

logger = logging.getLogger('yledl')


class FullHDFlavorProber:
    def probe_flavors(self, manifest_url, is_live, ffprobe):
        try:
            programs = ffprobe.show_programs_for_url(manifest_url)
        except ValueError as ex:
            return [FailedFlavor(f'Failed to probe stream: {str(ex)}')]

        return self.programs_to_stream_flavors(programs, manifest_url, is_live)

    def programs_to_stream_flavors(self, programs, manifest_url, is_live):
        res = []
        for program in programs.get('programs', []):
            streams = program.get('streams', [])
            any_stream_is_video = any(x['codec_type'] == 'video'
                                      for x in streams if 'codec_type' in x)
            widths = [x['width'] for x in streams if 'width' in x]
            heights = [x['height'] for x in streams if 'height' in x]
            bitrate = program.get('tags', {}).get('variant_bitrate')
            if bitrate:
                bitrate = int(bitrate) / 1000

            pid = program.get('program_id')
            res.append(StreamFlavor(
                media_type='video' if any_stream_is_video else 'audio',
                height=heights[0] if heights else None,
                width=widths[0] if widths else None,
                bitrate=bitrate,
                streams=[
                    DASHHLSBackend(manifest_url, long_probe=True,
                                   program_id=pid, is_live=is_live,
                                   experimental_subtitles=True)
                ]
            ))

        res = self._drop_duplicates(res)
        return sorted(res, key=lambda x: (x.height or 0, x.bitrate or 0))

    def _drop_duplicates(self, stream_flavors):
        def flavor_key(s):
            return (s.width, s.height, s.bitrate, next((x.url for x in s.streams), None))

        unique = {flavor_key(s): s for s in stream_flavors}
        return unique.values()
