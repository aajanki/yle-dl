# This file is part of yle-dl.
#
# Copyright 2010-2024 Antti Ajanki and others
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

from typing import List, Optional
from datetime import datetime

from dataclasses import dataclass
from .streamflavor import StreamFlavor
from .subtitles import Subtitle


@dataclass(frozen=True)
class AreenaApiProgramInfo:
    media_id: str
    title: str
    episode_title: str
    description: Optional[str]
    flavors: List[StreamFlavor]
    subtitles: List[Subtitle]
    duration_seconds: Optional[int]
    available_at_region: str
    publish_timestamp: Optional[datetime]
    expiration_timestamp: Optional[datetime]
    pending: bool
    expired: bool


@dataclass(frozen=True)
class EpisodeMetadata:
    uri: str
    season_number: Optional[int]
    episode_number: Optional[int]
    release_date: Optional[datetime]

    def sort_key(self):
        return (
            self.season_number or 99999,
            self.episode_number or 99999,
            self.release_date or datetime(1970, 1, 1, 0, 0, 0),
        )

    def with_episode_number(self, ep):
        return EpisodeMetadata(self.uri, self.season_number, ep, self.release_date)
