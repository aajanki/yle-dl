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
from .backends import FailingBackend


@attr.define
class StreamFlavor:
    media_type = attr.field()
    height = attr.field(default=None, converter=attr.converters.optional(int))
    width = attr.field(default=None, converter=attr.converters.optional(int))
    bitrate = attr.field(default=None, converter=attr.converters.optional(int))
    streams = attr.field(factory=list)


class FailedFlavor(StreamFlavor):
    def __init__(self, error_message):
        StreamFlavor.__init__(self,
                              media_type='unknown',
                              height=None,
                              width=None,
                              bitrate=None,
                              streams=[FailingBackend(error_message)])
