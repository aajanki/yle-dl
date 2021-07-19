# -*- coding: utf-8 -*-

import attr
import ipaddress
import logging
import os
import os.path
import random
import re
import subprocess
from .ffprobe import Ffprobe
from .utils import sane_filename

logger = logging.getLogger('yledl')


def which(program):
    """Search for program on $PATH and return the full path if found."""
    # Adapted from http://stackoverflow.com/questions/377017
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


def convert_download_limits(arg):
    return arg or DownloadLimits()


def ffmpeg_default(arg):
    return arg or 'ffmpeg'


def ffprobe_default(arg):
    return arg or 'ffprobe'


def wget_default(arg):
    return arg or 'wget'


def random_elisa_ipv4():
    elisa_ipv4_range = list(ipaddress.ip_network('91.152.0.0/13').hosts())
    return str(random.choice(elisa_ipv4_range))


@attr.s
class DownloadLimits(object):
    # Seek to this position (seconds) before starting the recording
    start_position = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(int)))
    # Limit the duration of the recorded stream (seconds)
    duration = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(int)))
    # Maximum download rate (int in kb/s or "best" or "worst")
    ratelimit = attr.ib(default=None)


@attr.s
class IOContext(object):
    outputfilename = attr.ib(default=None)
    preferred_format = attr.ib(default=None)
    destdir = attr.ib(default=None)
    resume = attr.ib(default=False)
    overwrite = attr.ib(default=True)
    download_limits = attr.ib(default=None, converter=convert_download_limits)
    excludechars = attr.ib(default='*/|')
    proxy = attr.ib(default=None)
    x_forwarded_for = attr.ib(default=None)
    subtitles = attr.ib(default='all')
    metadata_language = attr.ib(default=None)
    postprocess_command = attr.ib(default=None)
    ffmpeg_binary = attr.ib(default='ffmpeg', converter=ffmpeg_default)
    ffprobe_binary = attr.ib(default='ffprobe', converter=ffprobe_default)
    wget_binary = attr.ib(default='wget', converter=wget_default)

    def ffprobe(self):
        if self.ffprobe_binary is None:
            return None

        return Ffprobe(self.ffprobe_binary, self.ffmpeg_binary, self.x_forwarded_for)

    def ffmpeg_version(self):
        if self.ffmpeg_binary:
            args = [self.ffmpeg_binary, '-loglevel', 'quiet', '-version']
            p = subprocess.run(args, stdout=subprocess.PIPE, universal_newlines=True)
            if p.returncode == 0:
                first_line = p.stdout.splitlines()[0]
                m = re.match(r'ffmpeg version (\d+)\.(\d+)\.(\d+)', first_line)
                if m:
                    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


class OutputFileNameGenerator(object):
    def filename(self, title, extension, io):
        """Select a filename for the output."""

        sanitized_title = sane_filename(title, io.excludechars)
        forced_name = io.outputfilename
        destdir = io.destdir

        if forced_name:
            path = self._filename_from_template(
                forced_name, destdir, extension)
        else:
            path = self._filename_from_title(
                sanitized_title, destdir, extension)
            path = self._impose_maximum_filename_length(path)

        return path

    def _filename_from_template(self, basename, destdir, extension):
        extended_path = basename
        if not os.path.isabs(basename) and destdir:
            extended_path = os.path.join(destdir, basename)

        if extension.is_mandatory:
            return self._replace_extension(extended_path, extension)
        else:
            return self._append_ext_if_missing(extended_path, extension)

    def _replace_extension(self, filename, extension):
        ext = extension.extension
        basename, old_ext = os.path.splitext(filename)
        if not old_ext or old_ext != ext:
            if old_ext:
                logger.warn('Unsupported extension {}. Replacing it with {}'
                            .format(old_ext, ext))
            return basename + ext
        else:
            return filename

    def _append_ext_if_missing(self, filename, extension):
        if os.path.splitext(filename)[1]:
            return filename
        else:
            return filename + extension.extension

    def _filename_from_title(self, title, destdir, extension):
        filename = (title or 'ylestream') + extension.extension
        if destdir:
            filename = os.path.join(destdir, filename)
        return filename

    def _impose_maximum_filename_length(self, path):
        """If the last component of the path is longer than 255, shorten it."""
        head, filename = os.path.split(path)
        if len(filename) > 255:
            filename = filename[:225] + '-' + filename[-20:]
            return os.path.join(head, filename)
        else:
            return path
