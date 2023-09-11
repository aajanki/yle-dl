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

from dataclasses import dataclass, field
from typing import List, Optional
from .backends import BaseDownloader, FailingBackend


@dataclass
class StreamFlavor:
    media_type: str
    height: Optional[int] = None
    width: Optional[int] = None
    bitrate: Optional[int] = None
    streams: List[BaseDownloader] = field(default_factory=list)


def failed_flavor(error_message: str) -> StreamFlavor:
    return StreamFlavor(media_type='unknown', streams=[FailingBackend(error_message)])
