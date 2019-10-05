# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import json
import logging
import subprocess


logger = logging.getLogger('yledl')


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
                'Stream probing failed with status {}'.format(ex.returncode))

    def duration_seconds_file(self, filename):
        args = [self.ffprobe_binary, '-v', 'error', '-show_entries',
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                filename]

        try:
            return float(subprocess.check_output(args))
        except subprocess.CalledProcessError as ex:
            raise ValueError(
                'Stream probing failed with status {}'.format(ex.returncode))
