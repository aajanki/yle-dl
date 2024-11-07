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

