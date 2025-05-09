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

import json
import itertools
import logging
import os.path
import re
from requests import HTTPError
from urllib.parse import urlparse, parse_qs


from .backends import HLSAudioBackend, DASHHLSBackend, WgetBackend
from .clip import Clip, ClipExtractor, FailedClip
from .areena_api import AreenaApiProgramInfo
from .areena_extractors import AreenaPreviewApiParser
from .kaltura import YleKalturaApiClient
from .streamflavor import StreamFlavor, failed_flavor
from .streamprobe import FullHDFlavorProber
from .timestamp import parse_areena_timestamp
from .titleformatter import TitleFormatter


logger = logging.getLogger('yledl')


def extractor_factory(url, language_chooser, httpclient, title_formatter, ffprobe):
    if (
        re.match(r'^https?://yle\.fi/aihe/', url)
        or re.match(r'^https?://svenska\.yle\.fi/artikel/', url)
        or re.match(r'^https?://svenska\.yle\.fi/a/', url)
    ):
        logger.debug(f'{url} is an Elävä Arkisto URL')
        return ElavaArkistoExtractor(
            language_chooser, httpclient, title_formatter, ffprobe
        )
    elif (
        re.match(r'^https?://areena\.yle\.fi/audio/ohjelmat/[-a-zA-Z0-9]+', url)
        or re.match(r'^https?://areena\.yle\.fi/podcastit/ohjelmat/[-a-zA-Z0-9]+', url)
        or re.match(r'^https?://areena\.yle\.fi/radio/suorat/[-a-zA-Z0-9]+', url)
    ):
        logger.debug(f'{url} is a live radio URL')
        return AreenaLiveRadioExtractor(
            language_chooser, httpclient, title_formatter, ffprobe
        )
    elif re.match(r'^https?://yle\.fi/(a|uutiset|urheilu|saa)/', url):
        logger.debug(f'{url} is a news URL')
        return YleUutisetExtractor(
            language_chooser, httpclient, title_formatter, ffprobe
        )
    elif re.match(r'^https?://(areena|arenan)\.yle\.fi/', url) or re.match(
        r'^https?://yle\.fi/', url
    ):
        logger.debug(f'{url} is an Areena URL')
        return AreenaExtractor(language_chooser, httpclient, title_formatter, ffprobe)
    elif url.lower() in ['tv1', 'tv2', 'teema']:
        logger.debug(f'{url} is a live TV channel')
        return AreenaLiveTVExtractor(
            language_chooser, httpclient, title_formatter, ffprobe
        )
    else:
        logger.debug(f'{url} is an unrecognized URL')
        return None


## Flavors


class Flavors:
    @staticmethod
    def media_type(media):
        mtype = media.get('type')
        if mtype == 'AudioObject' or (
            mtype is None and media.get('containerFormat') == 'mpeg audio'
        ):
            return 'audio'
        else:
            return 'video'


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
            pid, clip_url, self.title_formatter, self.ffprobe
        )
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
            all_streams = list(
                itertools.chain.from_iterable(fl.streams for fl in program_info.flavors)
            )
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
                program_id=program_id,
            )
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
                subtitles=program_info.subtitles,
                program_id=program_id,
                origin_url=origin_url,
                thumbnail=program_info.thumbnail,
            )

    def media_flavors(
        self,
        media_id,
        hls_manifest_url,
        download_url,
        media_type,
        is_live,
        pageurl,
        ffprobe,
    ):
        flavors = []

        if download_url:
            flavors.extend(self.download_flavors(download_url, media_type))

        flavors2 = []
        if media_id:
            flavors2.extend(
                self.flavors_by_media_id(media_id, hls_manifest_url, is_live, ffprobe)
            )

        if not flavors2 and hls_manifest_url:
            flavors2.extend(self.hls_flavors(hls_manifest_url, media_type))

        flavors.extend(flavors2)

        if self.is_kaltura_media(media_id):
            # Get mp4 streams (for wget support) from Kaltura if available.
            # Web Areena no longer uses Kaltura, so this may break (Dec 2023).
            flavors.extend(self.kaltura_mp4_flavors(media_id, pageurl))

        return flavors or None

    def flavors_by_media_id(self, media_id, hls_manifest_url, is_live, ffprobe):
        if self.is_full_hd_media(media_id) or is_live:
            logger.debug('Detected a full-HD media')
            flavors = self.hls_probe_flavors(hls_manifest_url, is_live, ffprobe)
            error = [failed_flavor('Manifest URL is missing')]
            return flavors or error
        elif self.is_html5_media(media_id):
            logger.debug('Detected an HTML5 media')
            return self.hls_probe_flavors(hls_manifest_url, False, ffprobe)
        elif self.is_media_67(media_id) or self.is_mp3_podcast(media_id):
            return []
        elif hls_manifest_url:
            # Fall-back options for new media_id types
            logger.debug('Detected a possible HLS media')
            return self.hls_probe_flavors(hls_manifest_url, False, ffprobe)
        else:
            return [failed_flavor('Unknown stream flavor')]

    def kaltura_mp4_flavors(self, media_id, pageurl):
        entry_id = self.kaltura_entry_id(media_id)
        kapi_client = YleKalturaApiClient(self.httpclient)
        playback_context = kapi_client.playback_context(entry_id, pageurl)
        if playback_context:
            return kapi_client.parse_stream_flavors(playback_context, pageurl)
        else:
            return []

    def is_html5_media(self, media_id):
        # 29- is the most common media ID
        # 84-, hosted on yleawsmpondemand-04.akamaized.net, April 2024
        # 85-, ylekvodmod01.akamaized.net, also seen on podcasts, Summer 2024
        return media_id and (
            media_id.startswith('29-')
            or media_id.startswith('84-')
            or media_id.startswith('85-')
        )

    def is_kaltura_media(self, media_id):
        return media_id and media_id.startswith('29-')

    def is_full_hd_media(self, media_id):
        return media_id and media_id.startswith('55-')

    def is_media_67(self, media_id):
        # A new hosting alternative (June 2021)? Hosted on yleawsmpodamdipv4.akamaized.net
        return media_id and media_id.startswith('67-')

    def is_mp3_podcast(self, media_id):
        # Podcast streams, "78-" seen on Spring 2023
        # Prefer download_url, no extra flavors here.
        return media_id and media_id.startswith('78-')

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
        return FullHDFlavorProber().probe_flavors(hls_manifest_url, is_live, ffprobe)

    def download_flavors(self, download_url, media_type):
        path = urlparse(download_url)[2]
        ext = os.path.splitext(path)[1] or None
        backend = WgetBackend(download_url, ext)
        return [StreamFlavor(media_type=media_type, streams=[backend])]

    def publish_event(self, program_info):
        events = (program_info or {}).get('data', {}).get('publicationEvent', [])
        areena_events = [
            e for e in events if e.get('service', {}).get('id') == 'yle-areena'
        ]
        has_current = any(self.publish_event_is_current(e) for e in areena_events)
        if has_current:
            areena_events = [
                e for e in areena_events if self.publish_event_is_current(e)
            ]

        with_media = [e for e in areena_events if e.get('media')]
        if with_media:
            sorted_events = sorted(
                with_media, key=lambda e: e.get('startTime'), reverse=True
            )
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
        season_and_episode = preview.season_and_episode()
        if season_and_episode and 'season' not in season_and_episode:
            logger.debug('Checking the webpage for a season number')
            season_and_episode.update(self.extract_season_number(pageurl))
        title_params.update(season_and_episode)
        title = title_formatter.format(**title_params) or 'areena'
        simple_formatter = TitleFormatter('${series_separator}${title}')
        episode_title = simple_formatter.format(**title_params)
        media_id = preview.media_id()
        is_live = self.is_live_media(media_id) or preview.is_live()
        download_url = self.ignore_invalid_download_url(preview.media_url())
        if self.is_html5_media(media_id):
            preview_subtitles = preview.subtitles()
        else:
            preview_subtitles = []

        return AreenaApiProgramInfo(
            media_id=media_id,
            title=title,
            episode_title=episode_title,
            description=preview.description(self.language_chooser),
            flavors=self.media_flavors(
                media_id,
                preview.manifest_url(),
                download_url,
                preview.media_type(),
                is_live,
                pageurl,
                ffprobe,
            ),
            thumbnail=preview.thumbnail_url(),
            subtitles=preview_subtitles,
            duration_seconds=preview.duration_seconds(),
            available_at_region=preview.available_at_region() or 'Finland',
            publish_timestamp=publish_timestamp,
            expiration_timestamp=None,
            pending=preview.is_pending(),
            expired=preview.is_expired(),
        )

    def preview_parser(self, pid, pageurl):
        preview_headers = {'Referer': pageurl, 'Origin': 'https://areena.yle.fi'}
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
            'language=fin'
            '&ssl=true'
            '&countryCode=FI'
            '&host=areenaylefi'
            '&app_id=player_static_prod'
            '&app_key=8930d72170e48303cf5f3867780d549b'
            '&isPortabilityRegion=true'
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


### Areena live TV ###


class AreenaLiveTVExtractor(AreenaExtractor):
    def get_playlist(self, url, latest_only=False):
        return [url]

    def program_id_from_url(self, url):
        known_channels = {
            'tv1': 'yle-tv1',
            'tv2': 'yle-tv2',
            'teema': 'yle-teema-fem',
        }

        return known_channels.get(url.lower())


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
            '57-bN8gjw7AY': 'yle-sami-radio',
            # Radio Suomi and Vega have regional channels selected by the query
            # parameter _c. If _c is missing, use these hard coded values.
            '57-3gO4bl7J6': 'yle-radio-suomi-helsinki',
            '57-P3mO0mdm6': 'radio-vega-huvudstadsregionen',
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

        if ids:
            return [f'https://areena.yle.fi/{x}' for x in ids]
        else:
            # Fallback to Yle news parser because sometimes Elävä
            # arkisto pages are published using the same article type
            # as news articles.
            return parse_playlist_from_yle_article(url, self.httpclient, latest_only)

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
        return parse_playlist_from_yle_article(url, self.httpclient, latest_only)


def parse_playlist_from_yle_article(url, httpclient, latest_only):
    def id_to_areena_url(data_id):
        if '-' in data_id:
            areena_id = data_id
        else:
            areena_id = f'1-{data_id}'
        return f'https://areena.yle.fi/{areena_id}'

    tree = httpclient.download_html_tree(url)
    if tree is None:
        return []

    state = None
    state_script_nodes = tree.xpath(
        '//script[@type="text/javascript" and '
        '(contains(text(), "window.__INITIAL__STATE__") or '
        ' contains(text(), "window.__INITIAL_STATE__"))]/text()'
    )
    if len(state_script_nodes) > 0:
        state_json = re.sub(
            r'^window\.__INITIAL__?STATE__\s*=\s*', '', state_script_nodes[0]
        )
        state = json.loads(state_json)

    if state is None:
        state_div_nodes = tree.xpath('//div[@id="initialState"]')
        if len(state_div_nodes) > 0:
            state = json.loads(state_div_nodes[0].attrib.get('data-state'))

    if state is None:
        return []

    data_ids = []
    article = state.get('pageData', {}).get('article', {})
    if article.get('mainMedia') is not None:
        medias = article['mainMedia']
        data_ids = [
            media['id']
            for media in medias
            if media.get('type') in ['VideoBlock', 'video'] and 'id' in media
        ]
    else:
        headline_video_id = article.get('headline', {}).get('video', {}).get('id')
        if headline_video_id:
            data_ids = [headline_video_id]

    content = article.get('content', [])
    inline_media = [
        block['id']
        for block in content
        if block.get('type') in ['AudioBlock', 'audio', 'VideoBlock', 'video']
        and 'id' in block
    ]
    for id in inline_media:
        if id not in data_ids:
            data_ids.append(id)

    logger.debug(f"Found Areena data IDs: {','.join(data_ids)}")

    playlist = [id_to_areena_url(id) for id in data_ids]
    if latest_only:
        playlist = playlist[-1:]

    return playlist
