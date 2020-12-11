# -*- coding: utf-8 -*-

import logging
from .backends import HLSBackend
from .streamflavor import StreamFlavor, FailedFlavor


logger = logging.getLogger('yledl')


class FullHDFlavorProber(object):
    def probe_flavors(self, manifest_url, is_live, ffprobe):
        try:
            programs = ffprobe.show_programs_for_url(manifest_url)
        except ValueError as ex:
            return [FailedFlavor('Failed to probe stream: {}'.format(str(ex)))]

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
                    HLSBackend(manifest_url, long_probe=True,
                               program_id=pid, is_live=is_live)
                ]
            ))

        return sorted(res, key=lambda x: x.height or 0)
