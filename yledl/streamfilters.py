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
from .backends import Backends


@attr.frozen
class StreamFilters:
    """Parameters for deciding which of potentially multiple available stream
    versions to download.
    """
    latest_only = attr.field(default=False)
    maxbitrate = attr.field(default=None)
    maxheight = attr.field(default=None)
    enabled_backends = attr.field(default=attr.Factory(
        lambda: list(Backends.default_order)
    ))
