import json
import logging
import re
import subprocess
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
            '-loglevel', ffmpeg_loglevel(logger.getEffectiveLevel()),
            '-headers', f'X-Forwarded-For: {self.x_forwarded_for}\r\n',
            '-show_programs',
            '-print_format', 'json=c=1',
            '-probesize', '80000000',
            '-i', url,
        ]
        try:
            return json.loads(subprocess.check_output(args).decode('utf-8'))
        except subprocess.CalledProcessError as ex:
            raise ValueError(
                f'Stream probing failed with status {ex.returncode}')
        except FileNotFoundError:
            raise FfmpegNotFoundError()

    def duration_seconds_file(self, filename):
        args = [
            self.ffmpeg_binary,
            '-stats',
            '-loglevel', 'fatal',
            '-i', f'file:{filename}',
            '-f', 'null',
            '-',
        ]

        try:
            decoding_result = (
                subprocess.check_output(args, stderr=subprocess.STDOUT)
                .decode('utf-8')
                .rsplit('\r', 1)[-1])
        except subprocess.CalledProcessError as ex:
            raise ValueError(
                f'Stream probing failed with status {ex.returncode}')
        except UnicodeDecodeError:
            raise ValueError('Unexpected encoding on stream probing response')
        except FileNotFoundError:
            raise FfmpegNotFoundError()

        m = re.search(r'time=(\d\d):(\d\d):(\d\d)\.(\d\d) ', decoding_result)
        if not m:
            raise ValueError('Failed to parse duration in the ffmpeg output')

        return (float(m.group(1)) * 60 * 60 + float(m.group(2)) * 60 +
                float(m.group(3)) + float(m.group(4)) / 100)
