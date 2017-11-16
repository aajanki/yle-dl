import re
import logging
import json
from subprocess import Popen, PIPE

logger = logging.getLogger('yledl')

def is_complete(filename, ffmpeg, ffprobe):
    """Returns True if a video in filename has been fully downloaded."""
    try:
        metadata = metadata_duration(filename, ffprobe)
        actual = actual_duration(filename, ffmpeg)
        return metadata and actual and actual > 0.98*metadata
    except OSError as ex:
        logger.warn('Failed to read the duration of %s: %s', filename, ex)
        return False


def actual_duration(filename, ffmpeg='ffmpeg'):
    """Returns the video playback duration in seconds."""
    p = Popen([ffmpeg, '-i', 'file:' + filename, '-f', 'null', '-'], stderr=PIPE)
    output = p.communicate()[1]
    if not output:
        return None

    timestamps = re.findall(r'time=(\d{2}):(\d{2}):(\d{2})', output)
    timestamps_seconds = re.findall(r'time=(\d+)', output)
    if not timestamps and not timestamps_seconds:
        return None

    if timestamps:
        last_timestamp = timestamps[-1]
        return (60*60*int(last_timestamp[0]) +
                60*int(last_timestamp[1]) +
                int(last_timestamp[2]))
    else:
        return int(timestamps_seconds[-1])


def metadata_duration(filename, ffprobe='ffprobe'):
    """Returns the nominal video (container) duration in seconds."""
    p = Popen([ffprobe, '-v', 'error', '-show_format', '-of', 'json',
               'file:' + filename],
              stdout=PIPE, stderr=PIPE)
    output = p.communicate()[0]
    if not output:
        return None

    try:
        container = json.loads(output)
        duration = container.get('format', {}).get('duration', '')
        return float(duration)
    except ValueError:
        return None
