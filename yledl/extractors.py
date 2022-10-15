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
import itertools
import json
import logging
import os.path
import re
from datetime import datetime
from requests import HTTPError
from typing import List, Optional
from urllib.parse import urlparse, parse_qs
from .backends import HLSAudioBackend, DASHHLSBackend, WgetBackend
from .http import update_url_query
from .io import OutputFileNameGenerator
from .kaltura import YleKalturaApiClient
from .streamflavor import StreamFlavor, FailedFlavor
from .streamprobe import FullHDFlavorProber
from .timestamp import parse_areena_timestamp, format_finnish_short_weekday_and_date
from .titleformatter import TitleFormatter
from .subtitles import Subtitle, EmbeddedSubtitle


logger = logging.getLogger('yledl')


def extractor_factory(url, language_chooser, httpclient, title_formatter, ffprobe):
    if re.match(r'^https?://yle\.fi/aihe/', url) or \
       re.match(r'^https?://svenska\.yle\.fi/artikel/', url) or \
       re.match(r'^https?://svenska\.yle\.fi/a/', url):
        logger.debug(f'{url} is an Elävä Arkisto URL')
        return ElavaArkistoExtractor(language_chooser, httpclient, title_formatter, ffprobe)
    elif (re.match(r'^https?://areena\.yle\.fi/audio/ohjelmat/[-a-zA-Z0-9]+', url) or
          re.match(r'^https?://areena\.yle\.fi/podcastit/ohjelmat/[-a-zA-Z0-9]+', url) or
          re.match(r'^https?://areena\.yle\.fi/radio/suorat/[-a-zA-Z0-9]+', url)):
        logger.debug(f'{url} is a live radio URL')
        return AreenaLiveRadioExtractor(language_chooser, httpclient, title_formatter, ffprobe)
    elif re.match(r'^https?://yle\.fi/(uutiset|urheilu|saa)/', url):
        logger.debug(f'{url} is a news URL')
        return YleUutisetExtractor(language_chooser, httpclient, title_formatter, ffprobe)
    elif (re.match(r'^https?://(areena|arenan)\.yle\.fi/', url) or
          re.match(r'^https?://yle\.fi/', url)):
        logger.debug(f'{url} is an Areena URL')
        return AreenaExtractor(language_chooser, httpclient, title_formatter, ffprobe)
    else:
        logger.debug(f'{url} is an unrecognized URL')
        return None


def url_language(url):
    arenan = re.match(r'^https?://arenan\.yle\.fi/', url) is not None
    arkivet = re.match(r'^https?://svenska\.yle\.fi/artikel/', url) is not None
    if arenan or arkivet:
        return 'swe'
    else:
        return 'fin'


## Flavors


class Flavors:
    @staticmethod
    def media_type(media):
        mtype = media.get('type')
        if (
            mtype == 'AudioObject' or
            (mtype is None and media.get('containerFormat') == 'mpeg audio')
        ):
            return 'audio'
        else:
            return 'video'


## Clip


@attr.define
class Clip:
    webpage: str
    flavors: list = attr.field(factory=list)
    title: str = attr.field(default='')
    episode_title: str = attr.field(default='')
    description: Optional[str] = attr.field(default=None)
    duration_seconds: Optional[int] = attr.field(default=None,
                                                 converter=attr.converters.optional(int))
    region: str = attr.field(default='Finland')
    publish_timestamp: Optional[datetime] = attr.field(default=None)
    expiration_timestamp: Optional[datetime] = attr.field(default=None)
    embedded_subtitles: List = attr.field(factory=list)
    subtitles: List = attr.field(factory=list)
    program_id: Optional[str] = attr.field(default=None)
    origin_url: Optional[str] = attr.field(default=None)

    def metadata(self, io):
        flavors_meta = sorted(
            (self.flavor_meta(f) for f in self.flavors),
            key=lambda x: x.get('bitrate', 0))
        meta = [
            ('program_id', self.program_id),
            ('webpage', self.webpage),
            ('title', self.title),
            ('episode_title', self.episode_title),
            ('description', self.description),
            ('filename', self.meta_file_name(self.flavors, io)),
            ('flavors', flavors_meta),
            ('duration_seconds', self.duration_seconds),
            ('embedded_subtitles',
             [{'language': x.language, 'category': x.category}
              for x in self.embedded_subtitles]),
            ('subtitles',
             [{'language': x.lang, 'url': x.url, 'category': x.category}
              for x in self.subtitles]),
            ('region', self.region),
            ('publish_timestamp',
             self.format_timestamp(self.publish_timestamp)),
            ('expiration_timestamp',
             self.format_timestamp(self.expiration_timestamp))
        ]
        return self.ignore_none_values(meta)

    def meta_file_name(self, flavors, io):
        flavors = sorted(flavors, key=lambda x: x.bitrate or 0)
        flavors = [fl for fl in flavors
                   if any(s.is_valid() for s in fl.streams)]
        if flavors:
            extensions = [s.file_extension('mkv') for s in flavors[-1].streams
                          if s.is_valid()]
            if extensions:
                return (OutputFileNameGenerator()
                        .filename(self.title, extensions[0], io))

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
            ('url', url)
        ]
        return self.ignore_none_values(meta)

    def error_flavor_meta(self, flavor):
        error_messages = [s.error_message for s in flavor.streams
                          if not s.is_valid() and s.error_message]
        if error_messages:
            msg = error_messages[0]
        else:
            msg = 'Unknown error'

        return {'error': msg}

    def ignore_none_values(self, li):
        return {key: value for (key, value) in li if value is not None}


class FailedClip(Clip):
    def __init__(self, webpage, error_message, **kwargs):
        super().__init__(webpage=webpage, flavors=[FailedFlavor(error_message)], **kwargs)


@attr.frozen
class AreenaApiProgramInfo:
    media_id: str
    title: str
    episode_title: str
    description: Optional[str]
    flavors: List[StreamFlavor]
    embedded_subtitles: List[EmbeddedSubtitle]
    subtitles: List[Subtitle]
    duration_seconds: Optional[int]
    available_at_region: str
    publish_timestamp: Optional[datetime]
    expiration_timestamp: Optional[datetime]
    pending: bool
    expired: bool


@attr.frozen
class PlaylistData:
    base_url: str
    season_parameters: dict

    def season_playlist_urls(self):
        if self.season_parameters:
            for season_query in self.season_parameters:
                yield update_url_query(self.base_url, season_query)
        else:
            yield self.base_url


@attr.frozen
class EpisodeMetadata:
    uri: str
    season_number: Optional[int]
    episode_number: Optional[int]
    release_date: Optional[datetime]

    def sort_key(self):
        return (
            self.season_number or 99999,
            self.episode_number or 99999,
            self.release_date or datetime(1970, 1, 1, 0, 0, 0)
        )


class ClipExtractor:
    def __init__(self, httpclient):
        self.httpclient = httpclient

    def extract(self, url, latest_only):
        playlist = self.get_playlist(url, latest_only)
        return (self.extract_clip(clipurl, url) for clipurl in playlist)

    def get_playlist(self, url, latest_only=False):
        return AreenaPlaylistParser(self.httpclient).get(url, latest_only)

    def extract_clip(self, url, origin_url):
        raise NotImplementedError("extract_clip must be overridden")


class AreenaPlaylistParser:
    """Get a list of episodes in a series from Areena API

    Reference: https://docs.api.yle.fi/api/programs-api-v3
    """
    def __init__(self, httpclient):
        self.httpclient = httpclient

    def get(self, url, latest_only=False):
        """If url is a series page, return a list of included episode pages."""
        tree = self.httpclient.download_html_tree(url)
        if tree is None:
            logger.warning(f'Failed to download {url} while looking for a playlist')
            return [url]

        playlist = []
        playlist_data = None
        if self._is_tv_series_page(tree):
            logger.debug('TV playlist')
            playlist_data = self._parse_series_playlist(tree)
        elif self._is_radio_series_page(tree):
            logger.debug('Radio playlist')
            playlist_data = self._parse_radio_playlist(tree)
        elif self._extract_package_id(tree) is not None:
            logger.debug('Package playlist')
            playlist_data = self._parse_package_playlist(tree)
        else:
            logger.debug('Not a playlist')
            playlist = [url]

        if playlist_data is not None:
            playlist = self._download_playlist_or_latest(playlist_data, latest_only)
            logger.debug(f'playlist page with {len(playlist)} episodes')

        return playlist

    def _is_tv_series_page(self, tree):
        next_data_tag = tree.xpath('//script[@id="__NEXT_DATA__"]')
        if len(next_data_tag) == 0:
            return False

        next_data = json.loads(next_data_tag[0].text)
        ptype = (next_data.get('props', {})
                 .get('pageProps', {})
                 .get('meta', {})
                 .get('item', {})
                 .get('type'))

        return ptype in ['TVSeries', 'TVSeason', 'RadioSeries', 'Package']

    def _is_radio_series_page(self, tree):
        is_radio_page = len(tree.xpath('//div[contains(@class, "RadioPlayer")]')) > 0
        if is_radio_page:
            episode_modal = tree.xpath('//div[starts-with(@class, "EpisodeModal")]')
            play_button = tree.xpath('//main//button[starts-with(@class, "PlayButton")]')
            return not episode_modal and not play_button
        else:
            return False

    def _parse_series_playlist(self, html_tree):
        next_data_tag = html_tree.xpath('//script[@id="__NEXT_DATA__"]')
        if next_data_tag:
            next_data = json.loads(next_data_tag[0].text)
            tabs = next_data.get('props', {}).get('pageProps', {}).get('view', {}).get('tabs', [])
            episodes_tab = [tab for tab in tabs if tab.get('title') == 'Jaksot']
            if episodes_tab:
                episodes_content = episodes_tab[0].get('content', [])
                if episodes_content:
                    playlist_data = episodes_content[0]
                    uri = playlist_data.get('source', {}).get('uri')

                    series_parameters = {}
                    filters = playlist_data.get('filters', [])
                    if filters:
                        options = filters[0].get('options', [])
                        series_parameters = [x['parameters'] for x in options]

                    return PlaylistData(uri, series_parameters)

        return None

    def _parse_package_playlist(self, html_tree):
        package_tag = html_tree.xpath('//div[@class="package-view"]/@data-view')
        if package_tag:
            package_data = json.loads(package_tag[0])
            tabs = package_data.get('tabs', [])
            if tabs:
                content = tabs[0].get('content', [])
                if content:
                    uri = content[0].get('source', {}).get('uri')
                    return PlaylistData(uri, {})

        return None

    def _parse_radio_playlist(self, html_tree):
        state_tag = html_tree.xpath('//script[contains(., "window.STORE_STATE_FROM_SERVER")]')
        if state_tag:
            state_str = state_tag[0].text
            data = json.loads(state_str.split('=', 1)[-1].strip())
            tabs = data.get('viewStore', {}).get('viewPageView', {}).get('tabs', [])
            tabs = [t for t in tabs if t.get('title') == 'Jaksot']
            if tabs:
                all_content = tabs[0].get('allContent')
                if all_content:
                    uri = all_content[0].get('source', {}).get('uri')
                    return PlaylistData(uri, {})

        return None

    def _download_playlist_or_latest(self, playlist_data, latest_only):
        season_urls = list(enumerate(playlist_data.season_playlist_urls(), start=1))
        if latest_only:
            # Optimization: The latest episode belongs to the latest season
            season_urls = season_urls[-1:]

        playlist = self._download_playlist(season_urls)

        # The Areena API might return episodes in wrong order
        playlist = sorted(playlist, key=lambda x: x.sort_key())

        # The episode API doesn't seem to have any way to download only the
        # latest episode or start from the latest. We need to download all and
        # pick the latest.
        if latest_only:
            playlist = playlist[-1:]

        return [x.uri for x in playlist]

    def _download_playlist(self, season_urls):
        playlist = []
        for season_num, season_url in season_urls:
            # Areena server fails (502 Bad gateway) if page_size is larger
            # than 100.
            page_size = 100
            offset = 0
            has_next_page = True
            while has_next_page:
                logger.debug(
                    f'Getting a playlist page, season = {season_num}, '
                    f'size = {page_size}, offset = {offset}')

                params = {
                    'offset': str(offset),
                    'limit': str(page_size),
                    'app_id': 'areena-web-items',
                    'app_key': 'v9No1mV0omg2BppmDkmDL6tGKw1pRFZt',
                }
                playlist_page_url = update_url_query(season_url, params)
                page = self._parse_series_episode_data(playlist_page_url, season_num)

                if page is None:
                    logger.warning(
                        f'Playlist failed at offset {offset}. Some episodes may be missing!')
                    break

                playlist.extend(page)
                offset += len(page)
                has_next_page = len(page) == page_size

        return playlist

    def _parse_series_episode_data(self, playlist_page_url, season_number):
        playlist = self.httpclient.download_json(playlist_page_url)
        if playlist is None:
            return None

        episodes = []
        for data in playlist.get('data', []):
            uri = self._episode_uri(data)
            episode_number = self._episode_number(data)
            release_date = self._tv_release_date(data) or self._radio_release_date(data)

            if uri:
                episodes.append(
                    EpisodeMetadata(uri, season_number, episode_number, release_date)
                )

        return episodes

    @staticmethod
    def _extract_package_id(tree):
        package_id = tree.xpath('/html/body/@data-package-id')
        if package_id:
            return package_id[0]
        else:
            return None

    @staticmethod
    def _episode_uri(data):
        program_uri = data.get('pointer', {}).get('uri')
        if program_uri:
            media_id = program_uri.rsplit('/')[-1]
            return f'https://areena.yle.fi/{media_id}'
        else:
            return None

    @staticmethod
    def _episode_number(data):
        title = data.get('title')
        if title:
            # Try to parse the episode number from the title. That's the
            # only location where the episode number is available in the
            # API response.
            m = re.match(r'Jakso (\d+)', title, flags=re.IGNORECASE)
            if m:
                return int(m.group(1))

        return None

    def _tv_release_date(self, data):
        labels = data.get('labels')
        generics = self._label_by_type(labels, 'generic', 'formatted')
        for val in generics:
            # Look for a label that matches the format "pe 15.3.2019"
            m = re.match(r'[a-z]{2} (?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{4})', val)
            if m:
                return datetime(
                    int(m.group('year')),
                    int(m.group('month')),
                    int(m.group('day'))
                )

        return None

    def _radio_release_date(self, data):
        labels = data.get('labels')
        date_str = self._label_by_type(labels, 'releaseDate', 'raw')
        if date_str:
            try:
                return parse_areena_timestamp(date_str[0])
            except ValueError:
                pass

        return None

    def _label_by_type(self, labels: dict, type_name: str, key_name: str) -> List[str]:
        """Return a key value of an Areena API label object which as the given type."""
        matches = [x for x in labels if x.get('type') == type_name]
        return [x[key_name] for x in matches if key_name in x]


class AreenaPreviewApiParser:
    def __init__(self, data):
        self.preview = data or {}

    def media_id(self):
        if self.is_live():
            return self.ongoing().get('adobe', {}).get('yle_media_id')
        else:
            return self.ongoing().get('media_id')

    def duration_seconds(self):
        return self.ongoing().get('duration', {}).get('duration_in_seconds')

    def title(self, language_chooser):
        title = {}
        ongoing = self.ongoing()
        title_object = ongoing.get('title', {})
        if title_object:
            title['title'] = language_chooser.choose_long_form(title_object).strip()

        series_title_object = ongoing.get('series', {}).get('title', {})
        if series_title_object:
            title['series_title'] = language_chooser.choose_long_form(series_title_object).strip()

        # If title['title'] does not equal title['episode_title'], then
        # the episode title is title['title'].
        #
        # If title['title'] equals title['episode_title'], then either
        # 1. the episode title is the publication date ("pe 16.9.2022"), or
        # 2. the episode title is title['title']
        #
        # It seem impossible to decide which of the cases 1. or 2. should apply
        # based on the preview API response only. We will always use the date
        # (case 1.) because that is the more common case.
        if title.get('title') is not None and title.get('title') == title.get('series_title'):
            title_timestamp = parse_areena_timestamp(ongoing.get('start_time'))
            if title_timestamp:
                # Should be localized (Finnish or Swedish) based on language_chooser
                title['title'] = format_finnish_short_weekday_and_date(title_timestamp)

        return title

    def description(self, language_chooser):
        description_object = self.ongoing().get('description', {})
        if not description_object:
            return None

        return language_chooser.choose_long_form(description_object).strip()

    def episode_number(self):
        episode = self.ongoing().get('episode_number')
        return {'episode': episode} if episode is not None else {}

    def available_at_region(self):
        return self.ongoing().get('region')

    def timestamp(self):
        if self.is_live():
            return datetime.now().replace(microsecond=0)
        else:
            dt = self.ongoing().get('start_time')
            return parse_areena_timestamp(dt)

    def manifest_url(self):
        return self.ongoing().get('manifest_url')

    def media_url(self):
        return self.ongoing().get('media_url')

    def media_type(self):
        if not self.preview:
            return None
        elif self.ongoing().get('content_type') == 'AudioObject':
            return 'audio'
        else:
            return 'video'

    def is_live(self):
        data = self.preview.get('data', {})
        return data.get('ongoing_channel') is not None

    def is_pending(self):
        data = self.preview.get('data', {})
        pending = data.get('pending_event') or data.get('pending_ondemand')
        return pending is not None

    def is_expired(self):
        data = self.preview.get('data', {})
        return data.get('gone') is not None

    def ongoing(self):
        data = self.preview.get('data', {})
        return (data.get('ongoing_ondemand') or
                data.get('ongoing_event', {}) or
                data.get('ongoing_channel', {}) or
                data.get('pending_event') or
                {})

    def subtitles(self):
        langname2to3 = {
            'fi': 'fin',
            'fih': 'fin',
            'sv': 'swe',
            'svh': 'swe',
            'se': 'smi',
            'en': 'eng',
        }
        hearing_impaired_langs = ['fih', 'svh']

        sobj = self.ongoing().get('subtitles', [])
        subtitles = []
        for s in sobj:
            lcode = s.get('lang', None)
            if lcode:
                lang = langname2to3.get(lcode, lcode)
                if lcode in hearing_impaired_langs:
                    category = 'ohjelmatekstitys'
                else:
                    category = 'käännöstekstitys'
            else:
                lang = 'unk'
                category = 'käännöstekstitys'
            url = s.get('uri', None)
            if lang and url:
                subtitles.append(Subtitle(url, lang, category))
        return subtitles


### Extract streams from an Areena webpage ###


class AreenaExtractor(ClipExtractor):
    def __init__(self, language_chooser, httpclient, title_formatter, ffprobe):
        super().__init__(httpclient)
        self.language_chooser = language_chooser
        self.title_formatter = title_formatter
        self.ffprobe = ffprobe

    def extract_clip(self, clip_url, origin_url):
        pid = self.program_id_from_url(clip_url)
        program_info = self.program_info_for_pid(
            pid, clip_url, self.title_formatter, self.ffprobe)
        return self.create_clip_or_failure(pid, program_info, clip_url, origin_url)

    def program_id_from_url(self, url):
        parsed = urlparse(url)
        query_dict = parse_qs(parsed.query)
        play = query_dict.get('play')
        if parsed.path.startswith('/tv/ohjelmat/') and play:
            return play[0]
        else:
            return parsed.path.split('/')[-1]

    def create_clip_or_failure(self, pid, program_info, url, origin_url):
        if not pid:
            return FailedClip(url, 'Failed to parse a program ID')

        if not program_info:
            return FailedClip(url, 'Failed to download program data', program_id=pid)

        return self.create_clip(pid, program_info, url, origin_url)

    def create_clip(self, program_id, program_info, pageurl, origin_url):
        if program_info.flavors:
            all_streams = list(itertools.chain.from_iterable(
                fl.streams for fl in program_info.flavors))
        else:
            all_streams = []

        if program_info.pending:
            error_message = 'Stream not yet available.'
            if program_info.publish_timestamp:
                error_message = (
                    f'{error_message} Becomes available on '
                    f'{program_info.publish_timestamp.isoformat()}'
                )
        elif program_info.expired:
            error_message = 'This stream has expired'
        elif all_streams and all(not s.is_valid() for s in all_streams):
            error_message = all_streams[0].error_message
        elif not program_info.flavors:
            error_message = 'Media not found'
        else:
            error_message = None

        if error_message:
            return FailedClip(
                webpage=pageurl,
                error_message=error_message,
                title=program_info.title,
                description=program_info.description,
                duration_seconds=program_info.duration_seconds,
                region=program_info.available_at_region,
                publish_timestamp=program_info.publish_timestamp,
                expiration_timestamp=program_info.expiration_timestamp,
                program_id=program_id)
        else:
            return Clip(
                webpage=pageurl,
                flavors=program_info.flavors,
                title=program_info.title,
                episode_title=program_info.episode_title,
                description=program_info.description,
                duration_seconds=program_info.duration_seconds,
                region=program_info.available_at_region,
                publish_timestamp=program_info.publish_timestamp,
                expiration_timestamp=program_info.expiration_timestamp,
                embedded_subtitles=program_info.embedded_subtitles,
                subtitles=program_info.subtitles,
                program_id=program_id,
                origin_url=origin_url)

    def media_flavors(self, media_id, hls_manifest_url,
                      download_url, kaltura_flavors,
                      media_type, ffprobe):
        flavors = []

        if download_url:
            flavors.extend(self.download_flavors(download_url, media_type))

        flavors2 = []
        if media_id:
            flavors2.extend(
                self.flavors_by_media_id(
                    media_id, hls_manifest_url, kaltura_flavors, ffprobe))

        if not flavors2 and hls_manifest_url:
            flavors2.extend(self.hls_flavors(hls_manifest_url, media_type))

        flavors.extend(flavors2)

        return flavors or None

    def flavors_by_media_id(self, media_id, hls_manifest_url, kaltura_flavors, ffprobe):
        is_live = self.is_live_media(media_id)
        if self.is_full_hd_media(media_id) or is_live:
            logger.debug('Detected a full-HD media')
            flavors = self.hls_probe_flavors(hls_manifest_url, is_live, ffprobe)
            error = [FailedFlavor('Manifest URL is missing')]
            return flavors or error
        elif self.is_html5_media(media_id):
            logger.debug('Detected an HTML5 media')
            return (kaltura_flavors or
                    self.hls_probe_flavors(hls_manifest_url, False, ffprobe))
        elif self.is_media_67(media_id):
            return []
        else:
            return [FailedFlavor('Unknown stream flavor')]

    def is_html5_media(self, media_id):
        return media_id and media_id.startswith('29-')

    def is_full_hd_media(self, media_id):
        return media_id and media_id.startswith('55-')

    def is_media_67(self, media_id):
        # A new hosting alternative (June 2021)? Hosted on yleawsmpodamdipv4.akamaized.net
        return media_id and media_id.startswith('67-')

    def is_live_media(self, media_id):
        return media_id and media_id.startswith('10-')

    def kaltura_entry_id(self, mediaid):
        return mediaid.split('-', 1)[-1]

    def hls_flavors(self, hls_manifest_url, media_type):
        if not hls_manifest_url:
            return []

        if media_type == 'video':
            backend = DASHHLSBackend(hls_manifest_url, experimental_subtitles=True)
        else:
            backend = HLSAudioBackend(hls_manifest_url)

        return [StreamFlavor(media_type=media_type, streams=[backend])]

    def hls_probe_flavors(self, hls_manifest_url, is_live, ffprobe):
        if not hls_manifest_url:
            return []

        logger.debug('Probing for stream flavors')
        return FullHDFlavorProber().probe_flavors(
            hls_manifest_url, is_live, ffprobe)

    def download_flavors(self, download_url, media_type):
        path = urlparse(download_url)[2]
        ext = os.path.splitext(path)[1] or None
        backend = WgetBackend(download_url, ext)
        return [StreamFlavor(media_type=media_type, streams=[backend])]

    def publish_event(self, program_info):
        events = (program_info or {}).get('data', {}) \
                                     .get('publicationEvent', [])
        areena_events = [e for e in events
                         if e.get('service', {}).get('id') == 'yle-areena']
        has_current = any(self.publish_event_is_current(e)
                          for e in areena_events)
        if has_current:
            areena_events = [e for e in areena_events
                             if self.publish_event_is_current(e)]

        with_media = [e for e in areena_events if e.get('media')]
        if with_media:
            sorted_events = sorted(with_media,
                                   key=lambda e: e.get('startTime'),
                                   reverse=True)
            return sorted_events[0]
        else:
            return {}

    def publish_timestamp(self, program_info):
        ts = self.publish_event(program_info).get('startTime')
        return parse_areena_timestamp(ts)

    def program_info_for_pid(self, pid, pageurl, title_formatter, ffprobe):
        if not pid:
            return None

        preview = self.preview_parser(pid, pageurl)
        publish_timestamp = preview.timestamp()
        titles = preview.title(self.language_chooser)
        title_params = {
            'title': '',
            'program_id': pid,
            'publish_timestamp': publish_timestamp,
        }
        title_params.update(titles)
        season_and_episode = preview.episode_number()
        if season_and_episode:
            season_and_episode.update(self.extract_season_number(pageurl))
        title_params.update(season_and_episode)
        title = title_formatter.format(**title_params) or 'areena'
        simple_formatter = TitleFormatter('${series_separator}${title}')
        episode_title = simple_formatter.format(**title_params)
        media_id = preview.media_id()
        download_url = self.ignore_invalid_download_url(preview.media_url())
        if self.is_html5_media(media_id):
            entry_id = self.kaltura_entry_id(media_id)
            kapi_client = YleKalturaApiClient(self.httpclient)
            playback_context = kapi_client.playback_context(entry_id, pageurl)
            kaltura_flavors = kapi_client.parse_stream_flavors(
                playback_context, pageurl)
            kaltura_embedded_subtitles = kapi_client.parse_embedded_subtitles(playback_context)
            preview_subtitles = preview.subtitles()
        else:
            kaltura_flavors = None
            kaltura_embedded_subtitles = []
            preview_subtitles = []

        return AreenaApiProgramInfo(
            media_id=media_id,
            title=title,
            episode_title=episode_title,
            description=preview.description(self.language_chooser),
            flavors=self.media_flavors(media_id, preview.manifest_url(),
                                       download_url, kaltura_flavors,
                                       preview.media_type(), ffprobe),
            embedded_subtitles=kaltura_embedded_subtitles,
            subtitles=preview_subtitles,
            duration_seconds=preview.duration_seconds(),
            available_at_region=preview.available_at_region() or 'Finland',
            publish_timestamp=publish_timestamp,
            expiration_timestamp=None,
            pending=preview.is_pending(),
            expired=preview.is_expired(),
        )

    def preview_parser(self, pid, pageurl):
        preview_headers = {
            'Referer': pageurl,
            'Origin': 'https://areena.yle.fi'
        }
        url = self.preview_url(pid)
        try:
            preview_json = self.httpclient.download_json(url, preview_headers)
        except HTTPError as ex:
            if ex.response.status_code == 404:
                logger.warning(f'Preview API result not found: {url}')
                preview_json = []
            else:
                raise
        logger.debug(f'preview data:\n{json.dumps(preview_json, indent=2)}')

        return AreenaPreviewApiParser(preview_json)

    def preview_url(self, program_id):
        return (
            f'https://player.api.yle.fi/v1/preview/{program_id}.json?'
            'language=fin&ssl=true&countryCode=FI&host=areenaylefi'
            '&app_id=player_static_prod'
            '&app_key=8930d72170e48303cf5f3867780d549b'
        )

    def publish_event_is_current(self, event):
        return event.get('temporalStatus') == 'currently'

    def ignore_invalid_download_url(self, url):
        # Sometimes download url is missing the file name
        return None if (url and url.endswith('/')) else url

    def extract_season_number(self, pageurl):
        # TODO: how to get the season number without downloading the HTML page?
        tree = self.httpclient.download_html_tree(pageurl)
        title_tag = tree.xpath('/html/head/title/text()')
        if len(title_tag) > 0:
            title = title_tag[0]
            m = re.match(r'K(\d+), J\d+', title)
            if m:
                return {'season': int(m.group(1))}

        return {}


### Areena live radio ###


class AreenaLiveRadioExtractor(AreenaExtractor):
    def get_playlist(self, url, latest_only=False):
        return [url]

    def program_id_from_url(self, url):
        known_channels = {
            '57-p89RepWE0': 'yle-radio-1',
            '57-JAprnp7W2': 'ylex',
            '57-kpDBBz8Pz': 'yle-puhe',
            '57-md5vJP6a2': 'yle-x3m',
            '57-llL6Y4blL': 'yle-klassinen',
            '30-698': 'yle-sami-radio',
        }

        parsed = urlparse(url)
        query_dict = parse_qs(parsed.query)
        if query_dict.get('_c'):
            return query_dict.get('_c')[0]
        else:
            key = parsed.path.split('/')[-1]
            return known_channels.get(key, key)


### Elava Arkisto ###


class ElavaArkistoExtractor(AreenaExtractor):
    def get_playlist(self, url, latest_only=False):
        ids = self.get_dataids(url)
        if latest_only:
            ids = ids[-1:]

        return [f'https://areena.yle.fi/{x}' for x in ids]

    def get_dataids(self, url):
        tree = self.httpclient.download_html_tree(url)
        if tree is None:
            return []

        return self.ordered_union(self._simple_dataids(tree), self._ydd_dataids(tree))

    def ordered_union(self, xs, ys):
        union = list(xs)  # copy
        for y in ys:
            if y not in union:
                union.append(y)
        return union

    def _simple_dataids(self, tree):
        dataids = tree.xpath("//article[@id='main-content']//div/@data-id")
        dataids = [str(d) for d in dataids]
        return [d if '-' in d else f'1-{d}' for d in dataids]

    def _ydd_dataids(self, tree):
        player_props = [
            json.loads(p)
            for p in tree.xpath("//main[@id='main-content']//div/@data-player-props")
        ]
        return [x['id'] for x in player_props if 'id' in x]


### News clips at the Yle news site ###


class YleUutisetExtractor(AreenaExtractor):
    def get_playlist(self, url, latest_only=False):
        tree = self.httpclient.download_html_tree(url)
        if tree is None:
            return []

        state = None
        state_script_nodes = tree.xpath(
            '//script[@type="text/javascript" and '
            '(contains(text(), "window.__INITIAL__STATE__") or '
            ' contains(text(), "window.__INITIAL_STATE__"))]/text()')
        if len(state_script_nodes) > 0:
            state_json = re.sub(r'^window\.__INITIAL__?STATE__\s*=\s*', '', state_script_nodes[0])
            state = json.loads(state_json)

        if state is None:
            state_div_nodes = tree.xpath('//div[@id="initialState"]')
            if len(state_div_nodes) > 0:
                state = json.loads(state_div_nodes[0].attrib.get('data-state'))

        if state is None:
            return []

        data_ids = []
        article = state.get('article', {}).get('article', {})
        if article.get('mainMedia') is not None:
            medias = article.get('mainMedia', [])
            data_ids = [m.get('id') for m in medias if m.get('type') == 'VideoBlock']
        else:
            headline_video_id = article.get('headline', {}).get('video', {}).get('id')
            if headline_video_id:
                data_ids = [headline_video_id]

        content = article.get('content', [])
        data_ids.extend(block.get('id') for block in content
                        if block.get('type') == 'AudioBlock' and block.get('id'))

        logger.debug(f"Found Areena data IDs: {','.join(data_ids)}")

        playlist = [self.id_to_areena_url(id) for id in data_ids]
        if latest_only:
            playlist = playlist[-1:]

        return playlist

    def id_to_areena_url(self, data_id):
        if '-' in data_id:
            areena_id = data_id
        else:
            areena_id = f'1-{data_id}'
        return f'https://areena.yle.fi/{areena_id}'
