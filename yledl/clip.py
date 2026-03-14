# This file is part of yle-dl.
#
# Copyright 2010-2026 Antti Ajanki and others
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

from typing import Optional, Dict, Any, Iterable, Tuple, List
from datetime import datetime
from dataclasses import dataclass, field
from .io import IOContext, OutputFileNameGenerator
from .streamflavor import failed_flavor, StreamFlavor
from .subtitles import Subtitle


@dataclass
class Clip:
    webpage: str
    flavors: List[StreamFlavor] = field(default_factory=list)
    title: str = ''
    episode_title: str = ''
    description: Optional[str] = None
    duration_seconds: Optional[int] = None
    region: str = 'Finland'
    publish_timestamp: Optional[datetime] = None
    expiration_timestamp: Optional[datetime] = None
    subtitles: List[Subtitle] = field(default_factory=list)
    program_id: Optional[str] = None
    origin_url: Optional[str] = None
    thumbnail: Optional[str] = None

    def metadata(self, io: IOContext) -> Dict[str, Any]:
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
            ('thumbnail', self.thumbnail),
            ('region', self.region),
            ('publish_timestamp', self.format_timestamp(self.publish_timestamp)),
            ('expiration_timestamp', self.format_timestamp(self.expiration_timestamp)),
        ]
        return self.ignore_none_values(meta)

    def meta_file_name(
        self, flavors: Iterable[StreamFlavor], io: IOContext
    ) -> Optional[str]:
        flavors = sorted(flavors, key=lambda x: x.bitrate or 0)
        flavors = [fl for fl in flavors if any(s.is_valid() for s in fl.streams)]
        if flavors:
            extensions = [
                s.file_extension('mkv') for s in flavors[-1].streams if s.is_valid()
            ]
            if extensions:
                return OutputFileNameGenerator().filename(self.title, extensions[0], io)

        return None

    def format_timestamp(self, ts: Optional[datetime]) -> Optional[str]:
        return ts.isoformat() if ts else None

    def flavor_meta(self, flavor: StreamFlavor) -> Dict[str, Any]:
        if all(not s.is_valid() for s in flavor.streams):
            return self.error_flavor_meta(flavor)
        else:
            return self.valid_flavor_meta(flavor)

    def valid_flavor_meta(self, flavor: StreamFlavor) -> Dict[str, Any]:
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

    def error_flavor_meta(self, flavor: StreamFlavor) -> Dict[str, Any]:
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

    def ignore_none_values(self, li: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
        return {key: value for (key, value) in li if value is not None}


class FailedClip(Clip):
    def __init__(self, webpage: str, error_message: str, **kwargs):
        super().__init__(
            webpage=webpage, flavors=[failed_flavor(error_message)], **kwargs
        )
