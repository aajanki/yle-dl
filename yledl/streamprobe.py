# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import json
import logging
import subprocess
from .backends import HLSBackend
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


class Ffprobe(object):
    def __init__(self, ffprobe_binary):
        self.ffprobe_binary = ffprobe_binary

    def show_programs_for_url(self, url):
        debug = logger.isEnabledFor(logging.DEBUG)
        loglevel = 'info' if debug else 'error'
        args = [self.ffprobe_binary, '-v', loglevel, '-show_programs',
                '-print_format', 'json=c=1', '-strict', 'experimental',
                '-probesize', '80000000', '-i', url]
        try:
            return json.loads(subprocess.check_output(args))
        except subprocess.CalledProcessError as ex:
            raise ValueError(
                f'Stream probing failed with status {ex.returncode}')

    def duration_seconds_file(self, filename):
        args = [self.ffprobe_binary, '-v', 'error', '-show_entries',
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                filename]

        try:
            return float(subprocess.check_output(args))
        except subprocess.CalledProcessError as ex:
            raise ValueError(
                f'Stream probing failed with status {ex.returncode}')
