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
