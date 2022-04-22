import attr
import itertools
import json
import logging
import os.path
import re
from datetime import datetime
from requests import HTTPError
from urllib.parse import urlparse, parse_qs
from .backends import HLSAudioBackend, HLSBackend, WgetBackend
from .io import OutputFileNameGenerator
from .kaltura import YleKalturaApiClient
from .streamflavor import StreamFlavor, FailedFlavor
from .streamprobe import FullHDFlavorProber
from .timestamp import parse_areena_timestamp
from .subtitles import Subtitle
from .http import Redirected


logger = logging.getLogger('yledl')


class PlaylistRedirected(Exception):
    def __init__(self, message: str, suggested_url: str) -> None:
        super().__init__(message)
        self.suggested_url = suggested_url


def extractor_factory(url, language_chooser, httpclient):
    if re.match(r'^https?://yle\.fi/aihe/', url) or \
       re.match(r'^https?://svenska\.yle\.fi/artikel/', url) or \
       re.match(r'^https?://svenska\.yle\.fi/a/', url):
        logger.debug(f'{url} is an Elava Arkisto URL')
        return ElavaArkistoExtractor(language_chooser, httpclient)
    elif (re.match(r'^https?://areena\.yle\.fi/audio/ohjelmat/[-a-zA-Z0-9]+', url) or
          re.match(r'^https?://areena\.yle\.fi/radio/suorat/[-a-zA-Z0-9]+', url)):
        logger.debug(f'{url} is a live radio URL')
        return AreenaLiveRadioExtractor(language_chooser, httpclient)
    elif re.match(r'^https?://(areena|arenan)\.yle\.fi/audio/[-0-9]+', url):
        logger.debug(f'{url} is an audio URL')
        return AreenaAudio2020Extractor(language_chooser, httpclient)
    elif re.match(r'^https?://yle\.fi/(uutiset|urheilu|saa)/', url):
        logger.debug(f'{url} is a news URL')
        return YleUutisetExtractor(language_chooser, httpclient)
    elif (re.match(r'^https?://(areena|arenan)\.yle\.fi/', url) or
          re.match(r'^https?://yle\.fi/', url)):
        logger.debug(f'{url} is an Areena URL')
        return AreenaExtractor(language_chooser, httpclient)
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


@attr.s
class Clip:
    webpage = attr.ib()
    flavors = attr.ib()
    title = attr.ib(default='')
    description = attr.ib(default=None)
    duration_seconds = attr.ib(default=None, converter=attr.converters.optional(int))
    region = attr.ib(default='Finland')
    publish_timestamp = attr.ib(default=None)
    expiration_timestamp = attr.ib(default=None)
    embedded_subtitles = attr.ib(factory=list)
    subtitles = attr.ib(factory=list)
    program_id = attr.ib(default=None)

    def metadata(self, io):
        flavors_meta = sorted(
            (self.flavor_meta(f) for f in self.flavors),
            key=lambda x: x.get('bitrate', 0))
        meta = [
            ('program_id', self.program_id),
            ('webpage', self.webpage),
            ('title', self.title),
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
    def __init__(self, webpage, error_message, title=None, description=None,
                 duration_seconds=None, region=None, publish_timestamp=None,
                 expiration_timestamp=None, program_id=None):
        Clip.__init__(
            self,
            webpage=webpage,
            flavors=[FailedFlavor(error_message)],
            title=title,
            description=description,
            duration_seconds=duration_seconds,
            region=region,
            publish_timestamp=publish_timestamp,
            expiration_timestamp=expiration_timestamp,
            program_id=program_id)


@attr.s
class AreenaApiProgramInfo:
    media_id = attr.ib()
    title = attr.ib()
    description = attr.ib()
    flavors = attr.ib()
    embedded_subtitles = attr.ib()
    subtitles = attr.ib()
    duration_seconds = attr.ib()
    available_at_region = attr.ib()
    publish_timestamp = attr.ib()
    expiration_timestamp = attr.ib()
    pending = attr.ib()
    expired = attr.ib()


class ClipExtractor:
    def __init__(self, httpclient):
        self.httpclient = httpclient

    def extract(self, url, latest_only, title_formatter, ffprobe):
        playlist = self.guarded_get_playlist(url, latest_only)
        return (self.extract_clip(clipurl, title_formatter, ffprobe)
                for clipurl in playlist)

    def guarded_get_playlist(self, url, latest_only=False):
        # get_playlist, but with a guard to turn a http Redirected error to a PlaylistRedirected
        # for upstream handling
        try:
            return self.get_playlist(url, latest_only)
        except Redirected as r:
            raise PlaylistRedirected(
                f"Redirected while retrieving playlist: please try {r.response.url!r} instead",
                suggested_url=r.response.url,
            ) from r

    def get_playlist(self, url, latest_only=False):
        raise NotImplementedError("get_playlist must be overridden")

    def extract_clip(self, url, title_formatter, ffprobe):
        raise NotImplementedError("extract_clip must be overridden")


class AreenaPlaylist(ClipExtractor):
    def get_playlist(self, url, latest_only=False):
        """If url is a series page, return a list of included episode pages."""
        playlist = []
        if not self.is_tv_ohjelmat_url(url):
            playlist = self.get_playlist_series_page(url, latest_only)

        if playlist is None:
            logger.error('Failed to parse a playlist')
            playlist = []
        elif playlist:
            logger.debug(f'playlist page with {len(playlist)} clips')
        else:
            logger.debug('not a playlist')
            playlist = [url]

        return playlist

    def program_id_from_url(self, url):
        parsed = urlparse(url)
        query_dict = parse_qs(parsed.query)
        play = query_dict.get('play')
        if parsed.path.startswith('/tv/ohjelmat/') and play:
            return play[0]
        else:
            return parsed.path.split('/')[-1]

    def is_tv_ohjelmat_url(self, url):
        return urlparse(url).path.startswith('/tv/ohjelmat/')

    def get_playlist_series_page(self, url, latest_only):
        playlist = []
        html = self.httpclient.download_html_tree(url, raise_if_redirected=True)
        if html is not None and self.is_playlist_page(html):
            sid1 = self.extract_series_id_from_html(html)
            sid2 = self.program_id_from_url(url)
            series_id = sid1 or sid2
            playlist = self.playlist_episode_urls(series_id, latest_only)
        return playlist

    def extract_series_id_from_html(self, html_tree):
        series_main_url = html_tree.xpath('//div[@id = "seriesInfo"]/section/header/h2/a/@href')
        if len(series_main_url) > 0:
            sid = str(series_main_url[0]).split('/')[-1]

            # Make sure that we got a media ID instead of some random URL
            if re.match(r'^\d-\d+$', sid):
                return sid

        return None

    def playlist_episode_urls(self, series_id, latest_only):
        # Areena server fails (502 Bad gateway) if page_size is larger
        # than 100.
        if latest_only:
            page_size = 1
            sort_order = 'desc'
        else:
            page_size = 100
            sort_order = 'asc'
        offset = 0
        playlist = []
        has_next_page = True
        while has_next_page:
            page = self.playlist_page(series_id, sort_order, page_size, offset)
            if page is None:
                logger.warning(f'Playlist failed at offset {offset}. Some episodes may be missing!')
                break

            playlist.extend(page)
            offset += len(page)
            has_next_page = (len(page) == page_size) and not latest_only

        return playlist

    def playlist_page(self, series_id, sort_order, page_size, offset):
        logger.debug(f'Getting a playlist page {series_id}, size = {page_size}, offset = {offset}')

        pl_url = self.playlist_url(series_id, sort_order, page_size, offset)
        playlist = self.httpclient.download_json(pl_url)
        if playlist is None:
            return None

        playlist_data = playlist.get('data', [])
        episode_ids = (x['id'] for x in playlist_data if 'id' in x)
        return [f'https://areena.yle.fi/{episode_id}' for episode_id in episode_ids]

    def playlist_url(self, series_id, sort_order, page_size=100, offset=0):
        offset_param = f'&offset={str(offset)}' if offset else ''
        order_param = '%2C'.join((
            f'episode.hash%3A{sort_order}',
            f'publication.starttime%3A{sort_order}',
            'title.fi%3Aasc'
        ))
        return (
            f'https://areena.yle.fi/api/programs/v1/episodes/{series_id}.json?'
            f'type=program&availability=&'
            f'limit={str(page_size)}&'
            f'order={order_param}&'
            f'app_id=areena_web_frontend_prod&'
            f'app_key=4622a8f8505bb056c956832a70c105d4'
            f'{offset_param}'
        )

    def is_playlist_page(self, html_tree):
        body = html_tree.xpath('/html/body[contains(@class, "series-cover-page")]')
        return len(body) != 0


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
        title_object = self.ongoing().get('title', {})
        if not title_object:
            return {}

        return {'title': language_chooser.choose_long_form(title_object).strip()}

    def description(self, language_chooser):
        description_object = self.ongoing().get('description', {})
        if not description_object:
            return None

        return language_chooser.choose_long_form(description_object).strip()

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


class AreenaExtractor(AreenaPlaylist):
    def __init__(self, language_chooser, httpclient):
        super().__init__(httpclient)
        self.language_chooser = language_chooser

    def extract_clip(self, clip_url, title_formatter, ffprobe):
        pid = self.program_id_from_url(clip_url)
        program_info = self.program_info_for_pid(
            pid, clip_url, title_formatter, ffprobe)
        return self.create_clip_or_failure(pid, program_info, clip_url)

    def create_clip_or_failure(self, pid, program_info, url):
        if not pid:
            return FailedClip(url, 'Failed to parse a program ID')

        if not program_info:
            return FailedClip(url, 'Failed to download program data', program_id=pid)

        return self.create_clip(pid, program_info, url)

    def create_clip(self, program_id, program_info, pageurl):
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
                description=program_info.description,
                duration_seconds=program_info.duration_seconds,
                region=program_info.available_at_region,
                publish_timestamp=program_info.publish_timestamp,
                expiration_timestamp=program_info.expiration_timestamp,
                embedded_subtitles=program_info.embedded_subtitles,
                subtitles=program_info.subtitles,
                program_id=program_id)

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
                    media_id, hls_manifest_url, kaltura_flavors,
                    media_type, ffprobe))

        if not flavors2 and hls_manifest_url:
            flavors2.extend(self.hls_flavors(hls_manifest_url, media_type))

        flavors.extend(flavors2)

        return flavors or None

    def flavors_by_media_id(self, media_id, hls_manifest_url, kaltura_flavors,
                            media_type, ffprobe):
        is_live = self.is_live_media(media_id)
        if self.is_full_hd_media(media_id) or is_live:
            logger.debug('Detected a full-HD media')
            flavors = self.hls_probe_flavors(hls_manifest_url, media_type,
                                             is_live, ffprobe)
            error = [FailedFlavor('Manifest URL is missing')]
            return flavors or error
        elif self.is_html5_media(media_id):
            logger.debug('Detected an HTML5 media')
            return (kaltura_flavors or
                    self.hls_probe_flavors(hls_manifest_url, media_type,
                                           False, ffprobe))
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
            backend = HLSBackend(hls_manifest_url)
        else:
            backend = HLSAudioBackend(hls_manifest_url)

        return [StreamFlavor(media_type=media_type, streams=[backend])]

    def hls_probe_flavors(self, hls_manifest_url, media_type, is_live, ffprobe):
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
        titles = preview.title(self.language_chooser) or {'title': 'areena'}
        title_params = {
            'program_id': pid,
            'publish_timestamp': publish_timestamp,
        }
        title_params.update(titles)
        title = title_formatter.format(**title_params)
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


### Extract streams from an Areena audio webpage ###


class AreenaAudio2020Extractor(AreenaExtractor):
    def get_playlist(self, url, latest_only=False):
        if self.is_playlist(url):
            series_id = self.program_id_from_url(url)
            return self.playlist_episode_urls(series_id, latest_only)
        else:
            return [url]

    def is_playlist(self, url):
        html_tree = self.httpclient.download_html_tree(url)
        if html_tree is None:
            return []

        episode_modal = html_tree.xpath('//div[starts-with(@class, "EpisodeModal")]')
        play_button = html_tree.xpath('//main//button[starts-with(@class, "PlayButton")]')
        return not episode_modal and not play_button

    def playlist_url(self, series_id, sort_order, page_size=100, offset=0):
        offset_param = f'&offset={str(offset)}' if offset else ''
        order_param = '%2C'.join([
            f'episode.hash%3A{sort_order}',
            f'publication.starttime%3A{sort_order}',
            'title.fi%3Aasc',
        ])
        return (f'https://areena.yle.fi/api/programs/v1/episodes/{series_id}.json?'
                f'type=program&availability=&'
                f'limit={str(page_size)}&'
                f'order={order_param}&'
                f'app_id=areena_web_radio_prod&'
                f'app_key=b3a0dc973c0aab997f1021bc7a0e3157'
                f'{offset_param}')


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
