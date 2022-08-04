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

from .backends import Backends
from .downloader import YleDlDownloader
from .exitcodes import RD_SUCCESS, RD_FAILED, RD_INCOMPLETE
from .io import IOContext, DownloadLimits
from .streamfilters import StreamFilters
from .version import __version__
from .yledl import execute_action, StreamAction

__all__ = [
    '__version__',
    'execute_action',
    'YleDlDownloader',
    'StreamFilters',
    'DownloadLimits',
    'IOContext',
    'Backends',
    'StreamAction',
    'RD_SUCCESS',
    'RD_FAILED',
    'RD_INCOMPLETE'
]
