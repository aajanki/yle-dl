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

from typing import Dict, List

from dataclasses import dataclass
from .http import update_url_query


@dataclass(frozen=True)
class PlaylistData:
    # The base URL from which to download a playlist
    base_url: str
    # List of query parameters. Each item is a dictionary of query
    # parameters for one season. If empty, a playlist is downloaded
    # from the plain base_url.
    season_parameters: List[Dict]

    def season_playlist_urls(self):
        if self.season_parameters:
            for season_query in self.season_parameters:
                yield update_url_query(self.base_url, season_query)
        else:
            yield self.base_url
