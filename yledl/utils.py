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

import logging
import re
import sys


def print_enc(msg, out=None, linefeed_and_flush=True):
    if out is None:
        out = sys.stdout

    if hasattr(out, 'buffer'):
        bytes_out = out.buffer
    else:
        bytes_out = out

    if hasattr(out, 'encoding'):
        enc = out.encoding or 'UTF-8'
    else:
        enc = 'UTF-8'

    bytes_out.write(bytes(msg.encode(enc, 'ignore')))
    if linefeed_and_flush:
        bytes_out.write(b'\n')
        bytes_out.flush()


def sane_filename(name, excludechars):
    tr = {ord(c): ord('_') for c in excludechars}
    x = re.sub(r'\s+', ' ', name, flags=re.UNICODE).strip(' .').translate(tr)
    return x or 'ylevideo'


def ffmpeg_loglevel(py_loglevel):
    """Convert a Python log level to the corresponding ffmpeg log level."""
    if py_loglevel >= logging.CRITICAL:
        return 'fatal'
    elif py_loglevel >= logging.ERROR:
        return 'error'
    elif py_loglevel >= logging.DEBUG:
        return 'warning'
    else:
        return 'info'
