import re
import logging
from subprocess import Popen, PIPE

logger = logging.getLogger('yledl')

def is_complete(filename):
    """Returns True if a video in filename has been fully downloaded."""
    try:
        metadata = metadata_duration(filename)
        actual = actual_duration(filename)
        return metadata and actual and actual > 0.98*metadata
    except OSError as ex:
        logger.warn('Failed to read the duration of %s: %s', filename, ex)
        return False


def actual_duration(filename):
    """Returns the video playback duration in seconds."""
    p = Popen(['ffmpeg', '-i', filename, '-f', 'null', '-'], stderr=PIPE)
    output = p.communicate()[1]
    if not output:
        return None

    timestamps = re.findall(r'time=(\d{2}):(\d{2}):(\d{2})', output)
    if not timestamps:
        return None

    last_timestamp = timestamps[-1]
    return (60*60*int(last_timestamp[0]) +
            60*int(last_timestamp[1]) +
            int(last_timestamp[2]))


def metadata_duration(filename):
    """Returns the nominal video (container) duration in seconds."""
    p = Popen(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
               '-of', 'default=noprint_wrappers=1:nokey=1', filename],
              stdout=PIPE, stderr=PIPE)
    output = p.communicate()[0]
    try:
        return float(output)
    except (ValueError, TypeError):
        return None
