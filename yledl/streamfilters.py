# This file is part of yle-dl.
#
# Copyright 2010-2025 Antti Ajanki and others
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

from dataclasses import dataclass, field
from typing import Optional
from .backends import Backends


def default_backends():
    return list(Backends.default_order)


@dataclass(frozen=True)
class StreamFilters:
    """Parameters for deciding which of potentially multiple available stream
    versions to download.
    """

    latest_only: bool = False
    maxbitrate: Optional[int] = None
    maxheight: Optional[int] = None
    enabled_backends: list[str] = field(default_factory=default_backends)
