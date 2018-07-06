# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr
import base64
import json
import logging
import re
from future.moves.urllib.parse import urlparse, quote_plus, parse_qs
from . import hds
from .http import download_page, download_html_tree
from .streams import *

try:
    # pycryptodome
    from Cryptodome.Cipher import AES
except ImportError:
    # fallback on the obsolete pycrypto
    from Crypto.Cipher import AES


logger = logging.getLogger('yledl')


def extractor_factory(url):
    return AreenaExtractor()


def normalize_language_code(lang, subtype):
    if lang == 'all' or lang == 'none':
        return lang
    elif subtype == 'hearingimpaired':
        return lang + 'h'
    else:
        language_map = {'fi': 'fin', 'sv': 'swe'}
        return language_map.get(lang, lang)


class JSONP(object):
    @staticmethod
    def load_jsonp(url, headers=None):
        json_string = JSONP.remove_jsonp_padding(download_page(url, headers))
        if not json_string:
            return None

        try:
            json_parsed = json.loads(json_string)
        except ValueError:
            return None

        return json_parsed

    @staticmethod
    def remove_jsonp_padding(jsonp):
        if not jsonp:
            return None

        without_padding = re.sub(r'^[\w.]+\(|\);$', '', jsonp)
        if without_padding[:1] != '{' or without_padding[-1:] != '}':
            return None

        return without_padding


class AreenaDecrypt(object):
    @staticmethod
    def areena_decrypt(data, aes_key):
        try:
            bytestring = base64.b64decode(str(data))
        except (UnicodeEncodeError, TypeError):
            return None

        iv = bytestring[:16]
        ciphertext = bytestring[16:]
        padlen = 16 - (len(ciphertext) % 16)
        ciphertext = ciphertext + b'\0'*padlen

        decrypter = AES.new(aes_key, AES.MODE_CFB, iv, segment_size=16*8)
        return decrypter.decrypt(ciphertext)[:-padlen].decode('latin-1')


class KalturaUtils(object):
    def kaltura_flavors_meta(self, program_id, media_id, referer):
        mw = self.load_mwembed(media_id, program_id, referer)
        package_data = self.package_data_from_mwembed(mw)
        flavors = self.valid_flavors(package_data)
        meta = package_data.get('entryResult', {}).get('meta', {})
        return (flavors, meta, package_data.get('error'))

    def load_mwembed(self, media_id, program_id, referer):
        entryid = self.kaltura_entry_id(media_id)
        url = self.mwembed_url(entryid, program_id)
        logger.debug('mwembed URL: {}'.format(url))

        mw = JSONP.load_jsonp(url, {'Referer': referer})

        if mw:
            logger.debug('mwembed:')
            logger.debug(json.dumps(mw))

        return (mw or {}).get('content', '')

    def mwembed_url(self, entryid, program_id):
        return ('https://cdnapisec.kaltura.com/html5/html5lib/v2.60.2/'
                'mwEmbedFrame.php?&wid=_1955031&uiconf_id=37558971'
                '&cache_st=1442926927&entry_id={entry_id}'
                '&flashvars\[streamerType\]=auto'
                '&flashvars\[EmbedPlayer.HidePosterOnStart\]=true'
                '&flashvars\[EmbedPlayer.OverlayControls\]=true'
                '&flashvars\[IframeCustomPluginCss1\]='
                '%%2F%%2Fplayer.yle.fi%%2Fassets%%2Fcss%%2Fkaltura.css'
                '&flashvars\[mediaProxy\]='
                '%7B%22mediaPlayFrom%22%3Anull%7D'
                '&flashvars\[autoPlay\]=true'
                '&flashvars\[KalturaSupport.LeadWithHTML5\]=true'
                '&flashvars\[loop\]=false'
                '&flashvars\[sourceSelector\]='
                '%7B%22hideSource%22%3Atrue%7D'
                '&flashvars\[comScoreStreamingTag\]='
                '%7B%22logUrl%22%3A%22%2F%2Fda.yle.fi%2Fyle%2Fareena%2Fs'
                '%3Fname%3Dareena.kaltura.prod%22%2C%22plugin%22%3Atrue'
                '%2C%22position%22%3A%22before%22%2C%22persistentLabels'
                '%22%3A%22ns_st_mp%3Dareena.kaltura.prod%22%2C%22debug'
                '%22%3Atrue%2C%22asyncInit%22%3Atrue%2C%22relativeTo%22'
                '%3A%22video%22%2C%22trackEventMonitor%22%3A'
                '%22trackEvent%22%7D'
                '&flashvars\[closedCaptions\]='
                '%7B%22hideWhenEmpty%22%3Atrue%7D'
                '&flashvars\[Kaltura.LeadHLSOnAndroid\]=true'
                '&playerId=kaltura-{program_id}-1&forceMobileHTML5=true'
                '&urid=2.60'
                '&protocol=https'
                '&callback=mwi_kaltura121210530'.format(
                    entry_id=quote_plus(entryid),
                    program_id=quote_plus(program_id)))

    def kaltura_entry_id(self, mediaid):
        return mediaid.split('-', 1)[-1]

    def valid_flavors(self, package_data):
        flavors = (package_data
                   .get('entryResult', {})
                   .get('contextData', {})
                   .get('flavorAssets', []))
        web_flavors = [fl for fl in flavors if fl.get('isWeb', True)]
        num_non_web = len(flavors) - len(web_flavors)

        if num_non_web > 0:
            logger.debug('Ignored %d non-web flavors' % num_non_web)

        return web_flavors

    def package_data_from_mwembed(self, mw):
        m = re.search('window.kalturaIframePackageData\s*=\s*', mw, re.DOTALL)
        if not m:
            return {}

        try:
            # The string contains extra stuff after the JSON object,
            # so let's use raw_decode()
            return json.JSONDecoder().raw_decode(mw[m.end():])[0]
        except ValueError:
            logger.error('Failed to parse kalturaIframePackageData!')
            return {}


## Flavors


class Flavors(object):
    @staticmethod
    def single_flavor_meta(flavor, media_type=None):
        if media_type is None:
            media_type = Flavors.media_type(flavor)

        res = {'media_type': media_type}
        if 'height' in flavor:
            res['height'] = flavor['height']
        if 'width' in flavor:
            res['width'] = flavor['width']
        if 'bitrate' in flavor or 'audioBitrateKbps' in flavor:
            res['bitrate'] = (flavor.get('bitrate', 0) +
                              flavor.get('audioBitrateKbps', 0))
        return res

    @staticmethod
    def bitrate_meta(bitrate, media_type):
        return {
            'bitrate': bitrate,
            'media_type': media_type
        }

    @staticmethod
    def media_type(media):
        return 'audio' if media.get('type') == 'AudioObject' else 'video'


class AkamaiFlavorParser(object):
    def parse(self, medias, pageurl, aes_key):
        flavors = []
        for media in medias:
            flavors.extend(self.parse_media(media, pageurl, aes_key))
        return flavors

    def parse_media(self, media, pageurl, aes_key):
        is_hds = media.get('protocol') == 'HDS'
        crypted_url = media.get('url')
        media_url = self.decrypt_url(crypted_url, is_hds, aes_key)
        logger.debug('Media URL: {}'.format(media_url))
        if is_hds:
            if media_url:
                manifest = hds.parse_manifest(download_page(media_url))
            else:
                manifest = None
            return self.hds_flavors(media, media_url, manifest or [])
        else:
            return self.rtmp_flavors(media, media_url, pageurl)

    def decrypt_url(self, crypted_url, is_hds, aes_key):
        if crypted_url:
            baseurl = AreenaDecrypt.areena_decrypt(crypted_url, aes_key)
            if is_hds:
                sep = '&' if '?' in baseurl else '?'
                return baseurl + sep + \
                    'g=ABCDEFGHIJKL&hdcore=3.8.0&plugin=flowplayer-3.8.0.0'
            else:
                return baseurl
        else:
            return None

    def hds_flavors(self, media, media_url, manifest):
        flavors = []
        for mf in manifest:
            bitrate = mf.get('bitrate')
            flavor_id = mf.get('mediaurl')
            streams = [Areena2014HDSStreamUrl(media_url, bitrate, flavor_id)]
            flavors.append(StreamFlavor(
                media_type=Flavors.media_type(media),
                height=mf.get('height'),
                width=mf.get('width'),
                bitrate=bitrate,
                streams=streams))

        return flavors

    def rtmp_flavors(self, media, media_url, pageurl):
        streams = [Areena2014RTMPStreamUrl(pageurl, media_url)]
        return [
            StreamFlavor(
                media_type=Flavors.media_type(media),
                height=media.get('height'),
                width=media.get('width'),
                bitrate=media.get('bitrate'),
                streams=streams)
        ]


class KalturaFlavorParser(object):
    def parse(self, flavor_data, meta):
        # See http://cdnapi.kaltura.com/html5/html5lib/v2.56/load.php
        # for the actual Areena stream selection logic
        h264flavors = [f for f in flavor_data if self.is_h264_flavor(f)]
        if h264flavors:
            # Prefer non-adaptive HTTP stream
            stream_format = 'url'
            filtered_flavors = h264flavors
        elif meta.get('duration', 0) < 10:
            # short and durationless streams are not available as HLS
            stream_format = 'url'
            filtered_flavors = flavor_data
        else:
            # fallback to HLS if nothing else is available
            stream_format = 'applehttp'
            filtered_flavors = flavor_data

        return self.parse_streams(filtered_flavors, stream_format)

    def parse_streams(self, flavors_data, stream_format):
        flavors = []
        for fl in flavors_data:
            if 'entryId' in fl:
                entry_id = fl.get('entryId')
                flavor_id = fl.get('id') or '0_00000000'
                ext = '.' + (fl.get('fileExt') or 'mp4')
                bitrate = fl.get('bitrate', 0) + fl.get('audioBitrateKbps', 0)
                if bitrate <= 0:
                    bitrate = None
                streams = [KalturaStreamUrl(entry_id, flavor_id, stream_format, ext)]

                flavors.append(StreamFlavor(
                    media_type=Flavors.media_type(fl),
                    height=fl.get('height'),
                    width=fl.get('width'),
                    bitrate=bitrate,
                    streams=streams))

        return flavors

    def is_h264_flavor(self, flavor):
        tags = flavor.get('tags', '').split(',')
        ipad_h264 = 'ipad' in tags or 'iphone' in tags
        web_h264 = (('web' in tags or 'mbr' in tags) and
                    (flavor.get('fileExt') == 'mp4'))
        return ipad_h264 or web_h264


## Clip


@attr.s
class Clip(object):
    webpage = attr.ib()
    flavors = attr.ib()
    title = attr.ib(converter=attr.converters.optional(str))
    duration_seconds = attr.ib(converter=attr.converters.optional(int))
    region = attr.ib(converter=attr.converters.optional(str))
    publish_timestamp = attr.ib(converter=attr.converters.optional(str))
    expiration_timestamp = attr.ib(converter=attr.converters.optional(str))
    subtitles = attr.ib(default=attr.Factory(list))


@attr.s
class StreamFlavor(object):
    media_type = attr.ib()
    height = attr.ib(converter=attr.converters.optional(int))
    width = attr.ib(converter=attr.converters.optional(int))
    bitrate = attr.ib(converter=attr.converters.optional(str))
    streams = attr.ib(default=attr.Factory(list))


class FailedFlavor(StreamFlavor):
    def __init__(self, error_message):
        StreamFlavor.__init__(self,
                              media_type='unknown',
                              height=None,
                              width=None,
                              bitrate=None,
                              streams=[InvalidStreamUrl(error_message)])


class FailedClip(Clip):
    def __init__(self, webpage, error_message):
        Clip.__init__(self,
                      webpage=webpage,
                      flavors=[FailedFlavor(error_message)],
                      title=None,
                      duration_seconds=None,
                      region=None,
                      publish_timestamp=None,
                      expiration_timestamp=None,
                      subtitles=[])


@attr.s
class Subtitle(object):
    url = attr.ib()
    language = attr.ib()


class ClipExtractor(object):
    def extract(self, url):
        playlist = self.get_playlist(url)
        return [self.extract_clip(clipurl) for clipurl in playlist]

    def get_playlist(self, url):
        raise NotImplementedError("get_playlist must be overridden")

    def extract_clip(self, url):
        raise NotImplementedError("extract_clip must be overridden")


class AreenaParsers(object):
    @staticmethod
    def program_id_from_url(url):
        parsed = urlparse(url)
        query_dict = parse_qs(parsed.query)
        play = query_dict.get('play')
        if parsed.path.startswith('/tv/ohjelmat/') and play:
            return play[0]
        else:
            return parsed.path.split('/')[-1]


class AreenaPlaylist(object):
    def get_playlist(self, url):
        """If url is a series page, return a list of included episode pages."""
        playlist = []
        series_id = AreenaParsers.program_id_from_url(url)
        if not self.is_tv_ohjelmat_url(url):
            playlist = self.get_playlist_old_style_url(url, series_id)

        if playlist is None:
            logger.error('Failed to parse a playlist')
            return []
        elif playlist:
            logger.debug('playlist page with %d clips' % len(playlist))
        else:
            logger.debug('not a playlist')
            playlist = [url]

        return playlist

    def is_tv_ohjelmat_url(self, url):
        return urlparse(url).path.startswith('/tv/ohjelmat/')

    def get_playlist_old_style_url(self, url, series_id):
        playlist = []
        html = download_html_tree(url)
        if html is not None and self.is_playlist_page(html):
            playlist = self.playlist_episode_urls(series_id)
        return playlist

    def playlist_episode_urls(self, series_id):
        # Areena server fails (502 Bad gateway) if page_size is larger
        # than 100.
        offset = 0
        page_size = 100
        playlist = []
        has_next_page = True
        while has_next_page:
            page = self.playlist_page(series_id, page_size, offset)
            if page is None:
                return None

            playlist.extend(page)
            offset += page_size
            has_next_page = len(page) == page_size
        return playlist

    def playlist_page(self, series_id, page_size, offset):
        logger.debug('Getting a playlist page {series_id}, '
                     'size = {size}, offset = {offset}'.format(
                         series_id=series_id, size=page_size, offset=offset))

        playlist_json = download_page(
            self.playlist_url(series_id, page_size, offset))
        if not playlist_json:
            return None

        try:
            playlist = json.loads(playlist_json)
        except ValueError:
            return None

        playlist_data = playlist.get('data', [])
        episode_ids = (x['id'] for x in playlist_data if 'id' in x)
        return ['https://areena.yle.fi/' + x for x in episode_ids]

    def playlist_url(self, series_id, page_size=100, offset=0):
        if offset:
            offset_param = '&offset={offset}'.format(offset=str(offset))
        else:
            offset_param = ''

        return ('https://areena.yle.fi/api/programs/v1/items.json?'
                'series={series_id}&type=program&availability=ondemand&'
                'order=episode.hash%3Adesc%2C'
                'publication.starttime%3Adesc%2Ctitle.fi%3Aasc&'
                'app_id=89868a18&app_key=54bb4ea4d92854a2a45e98f961f0d7da&'
                'limit={limit}{offset_param}'.format(
                    series_id=quote_plus(series_id),
                    limit=str(page_size),
                    offset_param=offset_param))

    def is_playlist_page(self, html_tree):
        body = html_tree.xpath('/html/body[contains(@class, "series-cover-page")]')
        return len(body) != 0


class AreenaExtractor(AreenaPlaylist, KalturaUtils, ClipExtractor):
    # Extracted from
    # http://player.yle.fi/assets/flowplayer-1.4.0.3/flowplayer/flowplayer.commercial-3.2.16-encrypted.swf
    AES_KEY = b'yjuap4n5ok9wzg43'

    def extract_clip(self, clip_url):
        pid = AreenaParsers.program_id_from_url(clip_url)
        program_info = self.program_info_for_pid(pid)
        return self.create_clip_or_failure(pid, program_info, clip_url)

    def create_clip_or_failure(self, pid, program_info, url):
        if not pid:
            return FailedClip(url, 'Failed to parse a program ID')

        if not program_info:
            return FailedClip(url, 'Failed to download program data')

        return self.create_clip(pid, program_info, url)

    def create_clip(self, program_id, program_info, pageurl):
        media_id = self.program_media_id(program_info)
        medias = self.akamai_medias(program_id, media_id, program_info)
        subtitles = self.parse_subtitles(medias)
        
        flavors = self.flavors_by_program_info(
            program_id, program_info, pageurl)
        if flavors:
            return Clip(
                webpage=pageurl,
                flavors=flavors,
                title=self.program_title(program_info),
                duration_seconds=self.program_info_duration_seconds(program_info),
                region=self.available_at_region(program_info),
                publish_timestamp=self.publish_timestamp(program_info),
                expiration_timestamp=self.expiration_timestamp(program_info),
                subtitles=subtitles)
        else:
            return FailedClip(pageurl, 'Media not found')

    def flavors_by_program_info(self, program_id, program_info, pageurl):
        media_id = self.program_media_id(program_info)
        is_html5 = media_id.startswith('29-')
        proto = 'HLS' if is_html5 else 'HDS'
        medias = self.akamai_medias(program_id, media_id, program_info)

        if media_id and is_html5:
            logger.debug('Detected an HTML5 video')

            flavors_data, meta, error = self.kaltura_flavors_meta(
                program_id, media_id, pageurl)

            if error:
                return [] # InvalidFlavors(error)  ## FIXME
            else:
                return KalturaFlavorParser().parse(flavors_data, meta)

        elif media_id and medias:
            return AkamaiFlavorParser().parse(medias, pageurl, self.AES_KEY)

        else:
            return None

    def akamai_medias(self, program_id, media_id, program_info):
        is_html5 = media_id.startswith('29-')
        default_proto = 'HLS' if is_html5 else 'HDS'
        proto = self.program_protocol(program_info, default_proto)
        descriptor = self.yle_media_descriptor(program_id, media_id, proto)
        descriptor_proto = descriptor.get('meta', {}).get('protocol') or 'HDS'
        return descriptor.get('data', {}) \
                         .get('media', {}) \
                         .get(descriptor_proto, [])

    def parse_subtitles(self, medias):
        subtitles = []
        for subtitle_media in medias:
            subtitles.extend(self.media_subtitles(subtitle_media))
        return subtitles

    def program_protocol(self, program_info, default_video_proto):
        event = self.publish_event(program_info)
        if (event.get('media', {}).get('type') == 'AudioObject' or
            program_info.get('mediaFormat') == 'audio'):
            return 'RTMPE'
        else:
            return default_video_proto

    def yle_media_descriptor(self, program_id, media_id, protocol):
        media_jsonp_url = 'https://player.yle.fi/api/v1/media.jsonp?' \
                          'id=%s&callback=yleEmbed.startPlayerCallback&' \
                          'mediaId=%s&protocol=%s&client=areena-flash-player' \
                          '&instance=1' % \
            (quote_plus(media_id), quote_plus(program_id),
             quote_plus(protocol))
        media = JSONP.load_jsonp(media_jsonp_url)

        if media:
            logger.debug('media:')
            logger.debug(json.dumps(media))

        return media

    def program_media_id(self, program_info):
        event = self.publish_event(program_info)
        return event.get('media', {}).get('id')

    def publish_event(self, program_info):
        events = (program_info or {}).get('data', {}) \
                                     .get('program', {}) \
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

    def publish_date(self, program_info):
        event = self.publish_event(program_info)
        start_time = event.get('startTime')
        short = re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', start_time or '')
        if short:
            return short.group(0)
        else:
            return start_time

    def publish_timestamp(self, program_info):
        return self.publish_event(program_info).get('startTime')

    def expiration_timestamp(self, program_info):
        return self.publish_event(program_info).get('endTime')

    def program_info_for_pid(self, pid):
        if not pid:
            return None

        program_info = JSONP.load_jsonp(self.program_info_url(pid))
        if not program_info:
            return None

        logger.debug('program data:')
        logger.debug(json.dumps(program_info))

        return program_info

    def program_info_url(self, program_id):
        return 'https://player.yle.fi/api/v1/programs.jsonp?' \
            'id=%s&callback=yleEmbed.programJsonpCallback' % \
            (quote_plus(program_id))

    def publish_event_is_current(self, event):
        return event.get('temporalStatus') == 'currently'

    def media_subtitles(self, media):
        subtitles = []
        for s in media.get('subtitles', []):
            uri = s.get('uri')
            lang = self.language_code_from_subtitle_uri(uri) or \
                normalize_language_code(s.get('lang'), s.get('type'))
            if uri:
                subtitles.append(Subtitle(uri, lang))
        return subtitles

    def language_code_from_subtitle_uri(self, uri):
        if uri.endswith('.srt'):
            ext = uri[:-4].rsplit('.', 1)[-1]
            if len(ext) <= 3:
                return ext
            else:
                return None
        else:
            return None

    def program_info_duration_seconds(self, program_info):
        pt_duration = ((program_info or {})
                       .get('data', {})
                       .get('program', {})
                       .get('duration'))
        return self.pt_duration_as_seconds(pt_duration) if pt_duration else None

    def pt_duration_as_seconds(self, pt_duration):
        r = r'PT(?:(?P<hours>\d+)H)?(?:(?P<mins>\d+)M)?(?:(?P<secs>\d+)S)?$'
        m = re.match(r, pt_duration)
        if m:
            hours = m.group('hours') or 0
            mins = m.group('mins') or 0
            secs = m.group('secs') or 0
            return 3600*int(hours) + 60*int(mins) + int(secs)
        else:
            return None

    def available_at_region(self, program_info):
        return self.publish_event(program_info).get('region')

    def program_title(self, program_info):
        program = program_info.get('data', {}).get('program', {})
        titleObject = program.get('title')
        title = self.fi_or_sv_text(titleObject) or 'areena'

        if ':' in title:
            prefix, rest = title.split(':', 1)
            if prefix in rest:
                title = rest.strip()

        partOfSeasonObject = program.get('partOfSeason')

        if partOfSeasonObject:
            seasonNumberObject = partOfSeasonObject.get('seasonNumber')
        else:
            seasonNumberObject = program.get('seasonNumber')

        episodeNumberObject = program.get('episodeNumber')

        if seasonNumberObject and episodeNumberObject:
            title += ': S%02dE%02d' % (seasonNumberObject, episodeNumberObject)
        elif episodeNumberObject:
            title += ': E%02d' % (episodeNumberObject)

        itemTitleObject = program.get('itemTitle')
        itemTitle = self.fi_or_sv_text(itemTitleObject)

        promoTitleObject = program.get('promotionTitle')
        promotionTitle = self.fi_or_sv_text(promoTitleObject)

        if itemTitle and itemTitle not in title:
            title += ': ' + itemTitle
        elif promotionTitle and promotionTitle not in title:
            title += ': ' + promotionTitle

        title = self.remove_genre_prefix(title)

        timestamp = self.publish_date(program_info)
        if timestamp:
            title += '-' + timestamp.replace('/', '-').replace(' ', '-')

        return title

    def remove_genre_prefix(self, title):
        genre_prefixes = ['Elokuva:', 'Kino:', 'Kino Klassikko:',
                          'Kino Suomi:', 'Kotikatsomo:', 'Uusi Kino:', 'Dok:',
                          'Dokumenttiprojekti:', 'Historia:']
        for prefix in genre_prefixes:
            if title.startswith(prefix):
                return title[len(prefix):].strip()
        return title


    def localized_text(self, alternatives, language='fi'):
        if alternatives:
            return alternatives.get(language) or alternatives.get('fi')
        else:
            return None

    def fi_or_sv_text(self, alternatives):
        return self.localized_text(alternatives, 'fi') or \
            self.localized_text(alternatives, 'sv')

    def fin_or_swe_text(self, alternatives):
        return self.localized_text(alternatives, 'fin') or \
            self.localized_text(alternatives, 'swe')
