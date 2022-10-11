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

import attr
import ipaddress
import logging
import os
import random
import re
import subprocess
from typing import Optional
from .errors import FfmpegNotFoundError
from .ffprobe import Ffprobe
from .utils import sane_filename

logger = logging.getLogger('yledl')


def convert_download_limits(arg):
    return arg or DownloadLimits()


def ffmpeg_default(arg):
    return arg or 'ffmpeg'


def ffprobe_default(arg):
    return arg or 'ffprobe'


def wget_default(arg):
    return arg or 'wget'


def random_elisa_ipv4():
    return str(random_ip(ipaddress.ip_network('91.152.0.0/13')))


def random_ip(ip_network):
    # Convert to an int range, because sampling from a range is efficient
    ip_range_start = ip_network.network_address + 1
    ip_range_end = ip_network.broadcast_address - 1
    int_ip_range = range(int(ip_range_start), int(ip_range_end) + 1)
    return ipaddress.ip_address(random.choice(int_ip_range))


@attr.define
class DownloadLimits:
    # Seek to this position (seconds) before starting the recording
    start_position = attr.field(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(int)))
    # Limit the duration of the recorded stream (seconds)
    duration = attr.field(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(int)))
    # Maximum download rate (int in kb/s or "best" or "worst")
    ratelimit = attr.field(default=None)


@attr.define
class IOContext:
    outputfilename: Optional[str] = attr.field(default=None)
    preferred_format: Optional[str] = attr.field(default=None)
    destdir: Optional[str] = attr.field(default=None)
    resume: bool = attr.field(default=False)
    overwrite: bool = attr.field(default=True)
    download_limits: Optional[DownloadLimits] = attr.field(default=None,
                                                           converter=convert_download_limits)
    excludechars: str = attr.field(default='*/|')
    proxy: Optional[str] = attr.field(default=None)
    x_forwarded_for: Optional[str] = attr.field(default=None)
    subtitles: str = attr.field(default='all')
    metadata_language: Optional[str] = attr.field(default=None)
    postprocess_command: Optional[str] = attr.field(default=None)
    ffmpeg_binary: str = attr.field(default='ffmpeg', converter=ffmpeg_default)
    ffprobe_binary: str = attr.field(default='ffprobe', converter=ffprobe_default)
    wget_binary: str = attr.field(default='wget', converter=wget_default)
    create_dirs: bool = attr.field(default=False)
    xattr: bool = attr.field(default=False)

    def ffprobe(self):
        if self.ffprobe_binary is None:
            return None

        return Ffprobe(self.ffprobe_binary, self.ffmpeg_binary, self.x_forwarded_for)

    def ffmpeg_version(self):
        if self.ffmpeg_binary:
            args = [self.ffmpeg_binary, '-loglevel', 'quiet', '-version']
            try:
                p = subprocess.run(args, stdout=subprocess.PIPE, universal_newlines=True)
                if p.returncode == 0:
                    first_line = p.stdout.splitlines()[0]
                    m = re.match(r'ffmpeg version (\d+)\.(\d+)\.(\d+)', first_line)
                    if m:
                        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except FileNotFoundError:
                raise FfmpegNotFoundError()


class OutputFileNameGenerator:
    def filename(self, title, extension, io):
        """Select a filename for the output."""

        forced_name = io.outputfilename
        destdir = io.destdir

        if forced_name:
            path = self._filename_from_template(
                forced_name, destdir, extension)
        else:
            if '/' in title:
                # Title contains a subdirectory
                path, title = title.rsplit('/', maxsplit=1)
                destdir = destdir or ''
                for subdir in path.split('/'):
                    destdir = os.path.join(destdir, subdir)
            sanitized_title = sane_filename(title, io.excludechars)
            path = self._filename_from_title(
                sanitized_title, destdir, extension)
            path = self._impose_maximum_filename_length(path)

        dir, _ = os.path.split(path)
        if dir and not os.path.exists(dir):
            if not io.create_dirs:
                logger.error(
                    f'Directory "{dir}" does not exist. Use --create-dirs to automatically create.'
                )
                return path
            logger.info(f'Creating directory "{dir}"')
            os.makedirs(dir)

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
                logger.warn(f'Unsupported extension {old_ext}. Replacing it with {ext}')
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
