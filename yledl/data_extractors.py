from typing import Dict, List, Optional
from datetime import datetime

from dataclasses import dataclass, field
from .http import update_url_query
from .io import OutputFileNameGenerator
from .streamflavor import StreamFlavor
from .subtitles import Subtitle

## Clip


@dataclass
class Clip:
    webpage: str
    flavors: list = field(default_factory=list)
    title: str = ''
    episode_title: str = ''
    description: Optional[str] = None
    duration_seconds: Optional[int] = None
    region: str = 'Finland'
    publish_timestamp: Optional[datetime] = None
    expiration_timestamp: Optional[datetime] = None
    subtitles: List = field(default_factory=list)
    program_id: Optional[str] = None
    origin_url: Optional[str] = None

    def metadata(self, io):
        flavors_meta = sorted(
            (self.flavor_meta(f) for f in self.flavors),
            key=lambda x: x.get('bitrate', 0),
        )
        meta = [
            ('program_id', self.program_id),
            ('webpage', self.webpage),
            ('title', self.title),
            ('episode_title', self.episode_title),
            ('description', self.description),
            ('filename', self.meta_file_name(self.flavors, io)),
            ('flavors', flavors_meta),
            ('duration_seconds', self.duration_seconds),
            (
                'subtitles',
                [
                    {'language': x.lang, 'url': x.url, 'category': x.category}
                    for x in self.subtitles
                ],
            ),
            ('region', self.region),
            ('publish_timestamp', self.format_timestamp(self.publish_timestamp)),
            ('expiration_timestamp', self.format_timestamp(self.expiration_timestamp)),
        ]
        return self.ignore_none_values(meta)

    def meta_file_name(self, flavors, io):
        flavors = sorted(flavors, key=lambda x: x.bitrate or 0)
        flavors = [fl for fl in flavors if any(s.is_valid() for s in fl.streams)]
        if flavors:
            extensions = [
                s.file_extension('mkv') for s in flavors[-1].streams if s.is_valid()
            ]
            if extensions:
                return OutputFileNameGenerator().filename(self.title, extensions[0], io)

        return None

    def format_timestamp(self, ts):
        return ts.isoformat() if ts else None

    def flavor_meta(self, flavor):
        if all(not s.is_valid() for s in flavor.streams):
            return self.error_flavor_meta(flavor)
        else:
            return self.valid_flavor_meta(flavor)

    def valid_flavor_meta(self, flavor):
        backends = [s.name for s in flavor.streams if s.is_valid()]

        streams = flavor.streams
        if streams and any(s.is_valid() for s in streams):
            valid_stream = next(s for s in streams if s.is_valid())
            url = valid_stream.stream_url()
        else:
            url = None

        meta = [
            ('media_type', flavor.media_type),
            ('height', flavor.height),
            ('width', flavor.width),
            ('bitrate', flavor.bitrate),
            ('backends', backends),
            ('url', url),
        ]
        return self.ignore_none_values(meta)

    def error_flavor_meta(self, flavor):
        error_messages = [
            s.error_message
            for s in flavor.streams
            if not s.is_valid() and s.error_message
        ]
        if error_messages:
            msg = error_messages[0]
        else:
            msg = 'Unknown error'

        return {'error': msg}

    def ignore_none_values(self, li):
        return {key: value for (key, value) in li if value is not None}


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


class ClipExtractor:
    def __init__(self, httpclient):
        self.httpclient = httpclient

    def extract(self, url, latest_only):
        playlist = self.get_playlist(url, latest_only)
        return (self.extract_clip(clipurl, url) for clipurl in playlist)

    def get_playlist(self, url, latest_only=False):
        return AreenaPlaylistParser(self.httpclient).get(url, latest_only)

    def extract_clip(self, url, origin_url):
        raise NotImplementedError('extract_clip must be overridden')

