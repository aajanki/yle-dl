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

class FfmpegNotFoundError(Exception):
    pass


class ExternalApplicationNotFoundError(Exception):
    """Downloader backend failed because of a missing external program"""
    pass


class TransientDownloadError(Exception):
    """Download process was interrupted by a potentially transient error.

    Raised on I/O errors and on similar errors where retrying might fix the
    situation.
    """
    def __init__(self, message):
        self.message = message
