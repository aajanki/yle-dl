# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import logging
from .backends import HLSBackend
from .ffprobe import Ffprobe
from .streamflavor import StreamFlavor, FailedFlavor


logger = logging.getLogger('yledl')


class FullHDFlavorProber(object):
    def __init__(self, ffprobe_binary):
        self.probe = Ffprobe(ffprobe_binary)

    def probe_flavors(self, manifest_url):
        try:
            programs = self.probe.show_programs_for_url(manifest_url)
        except ValueError as ex:
            return [FailedFlavor(f'Failed to probe stream: {str(ex)}')]

        return self.programs_to_stream_flavors(programs, manifest_url)

    def programs_to_stream_flavors(self, programs, manifest_url):
        res = []
        for program in programs.get('programs', []):
            streams = program.get('streams', [])
            any_stream_is_video = any(x['codec_type'] == 'video'
                                      for x in streams if 'codec_type' in x)
            widths = [x['width'] for x in streams if 'width' in x]
            heights = [x['height'] for x in streams if 'height' in x]

            pid = program.get('program_id')
            res.append(StreamFlavor(
                media_type='video' if any_stream_is_video else 'audio',
                height=heights[0] if heights else None,
                width=widths[0] if widths else None,
                streams=[HLSBackend(manifest_url, long_probe=True, program_id=pid)]
            ))

        return sorted(res, key=lambda x: x.height)
