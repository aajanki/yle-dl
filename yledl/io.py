# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr
import logging
import os
import os.path
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


@attr.s
class DownloadLimits(object):
    duration = attr.ib(default=None)
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
    embed_subtitles = attr.ib(default=True)
    ffmpeg_binary = attr.ib(default='ffmpeg', converter=ffmpeg_default)
    ffprobe_binary = attr.ib(default='ffprobe', converter=ffprobe_default)
    wget_binary = attr.ib(default='wget', converter=wget_default)

    def ffprobe(self):
        if self.ffprobe_binary is None:
            return None

        return Ffprobe(self.ffprobe_binary, self.ffmpeg_binary)


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
        if '.' in filename:
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
