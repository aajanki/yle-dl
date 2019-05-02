# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import attr
import base64
import itertools
import json
import logging
import os.path
import re
import subprocess
import sys
from datetime import datetime
from future.moves.urllib.parse import urlparse, quote_plus, parse_qs
from . import localization
from . import hds
from .backends import HDSBackend, HLSAudioBackend, HLSBackend, RTMPBackend, \
    WgetBackend, YoutubeDLHDSBackend
from .http import html_unescape
from .kaltura import YleKalturaApiClient
from .rtmp import create_rtmp_params
from .streamfilters import normalize_language_code
from .streamflavor import StreamFlavor, FailedFlavor
from .subtitles import Subtitle
from .timestamp import parse_areena_timestamp
from .utils import sane_filename


try:
    # pycryptodome
    from Cryptodome.Cipher import AES
except ImportError:
    # fallback on the obsolete pycrypto
    from Crypto.Cipher import AES


logger = logging.getLogger('yledl')


def extractor_factory(url, filters, httpclient):
    if re.match(r'^https?://yle\.fi/aihe/', url) or \
       re.match(r'^https?://(areena|arenan)\.yle\.fi/26-', url):
        return ElavaArkistoExtractor(httpclient)
    elif re.match(r'^https?://svenska\.yle\.fi/artikel/', url):
        return ArkivetExtractor(httpclient)
    elif (re.match(r'^https?://areena\.yle\.fi/radio/ohjelmat/[-a-zA-Z0-9]+', url) or
          re.match(r'^https?://areena\.yle\.fi/radio/suorat/[-a-zA-Z0-9]+', url)):
        return AreenaLiveRadioExtractor(httpclient)
    elif re.match(r'^https?://(areena|arenan)\.yle\.fi/tv/suorat/', url):
        return MergingExtractor([
            AreenaLiveTVHLSExtractor(httpclient),
            AreenaLiveTVHDSExtractor(filters, httpclient)
        ])
    elif re.match(r'^https?://yle\.fi/(uutiset|urheilu|saa)/', url):
        return YleUutisetExtractor(httpclient)
    elif re.match(r'^https?://(areena|arenan)\.yle\.fi/', url) or \
            re.match(r'^https?://yle\.fi/', url):
        return AreenaExtractor(httpclient)
    else:
        return None


class JSONP(object):
    @staticmethod
    def load_jsonp(url, httpclient, headers=None):
        json_string = JSONP.remove_jsonp_padding(
            httpclient.download_page(url, headers))
        if not json_string:
            return None

        try:
            json_parsed = json.loads(json_string)
        except ValueError:
            return None

        return json_parsed

    @staticmethod
    def load_json(url, httpclient, headers=None):
        json_string = httpclient.download_page(url, headers)
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


## Flavors


class Flavors(object):
    @staticmethod
    def media_type(media):
        mtype = media.get('type')
        if (mtype == 'AudioObject' or
            (mtype is None and media.get('containerFormat') == 'mpeg audio')):
            return 'audio'
        else:
            return 'video'


class AkamaiFlavorParser(object):
    def __init__(self, httpclient):
        self.httpclient = httpclient

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
                manifest = hds.parse_manifest(self.httpclient.download_page(media_url))
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

        hard_subtitle = None
        hard_subtitle_lang = media.get('hardsubtitle', {}).get('lang')
        if hard_subtitle_lang:
            hard_subtitle = Subtitle(url=None, lang=hard_subtitle_lang)

        for mf in manifest:
            bitrate = mf.get('bitrate')
            flavor_id = mf.get('mediaurl')
            streams = [
                HDSBackend(media_url, bitrate, flavor_id),
                YoutubeDLHDSBackend(media_url, bitrate, flavor_id)
            ]
            flavors.append(StreamFlavor(
                media_type=Flavors.media_type(media),
                height=mf.get('height'),
                width=mf.get('width'),
                bitrate=bitrate,
                streams=streams,
                hard_subtitle=hard_subtitle))

        return flavors

    def rtmp_flavors(self, media, media_url, pageurl):
        rtmp_params = create_rtmp_params(media_url, pageurl, self.httpclient)
        if rtmp_params:
            streams = [RTMPBackend(rtmp_params)]
        else:
            streams = []
        bitrate = media.get('bitrate', 0) + media.get('audioBitrateKbps', 0)
        return [
            StreamFlavor(
                media_type=Flavors.media_type(media),
                height=media.get('height'),
                width=media.get('width'),
                bitrate=bitrate,
                streams=streams)
        ]


class FullHDFlavorProber(object):
    def probe_flavors(self, manifest_url, ffprobe_binary):
        try:
            programs = self.ffprobe_programs(manifest_url, ffprobe_binary)
        except ValueError:
            return [FailedFlavor('Failed to parse ffprobe output')]
        except subprocess.CalledProcessError as ex:
            return [FailedFlavor('Stream probing failed with status {}: {}'
                                 .format(ex.returncode, ex.output))]

        return self.programs_to_stream_flavors(programs, manifest_url)

    def ffprobe_programs(self, url, ffprobe_binary):
        debug = logger.isEnabledFor(logging.DEBUG)
        loglevel = 'info' if debug else 'error'
        args = [ffprobe_binary, '-v', loglevel, '-show_programs',
                '-print_format', 'json=c=1', '-strict', 'experimental',
                '-probesize', '80000000', '-i', url]

        return json.loads(subprocess.check_output(args))

    def programs_to_stream_flavors(self, programs, manifest_url):
        res = []
        for program in programs.get('programs', []):
            streams = program.get('streams', [])
            any_stream_is_video = any(x['codec_type'] == 'video'
                                      for x in streams if 'codec_type' in x)
            widths = [x['width'] for x in streams if 'width' in x]
            heights = [x['height'] for x in streams if 'height' in x]

            pid = program.get('program_id')
            res.append(StreamFlavor(
                media_type='video' if any_stream_is_video else 'audio',
                height=heights[0] if heights else None,
                width=widths[0] if widths else None,
                streams=[HLSBackend(manifest_url, long_probe=True, program_id=pid)]
            ))

        return sorted(res, key=lambda x: x.height)


## Clip


@attr.s
class Clip(object):
    webpage = attr.ib()
    flavors = attr.ib()
    title = attr.ib(default='')
    duration_seconds = attr.ib(default=None, converter=attr.converters.optional(int))
    region = attr.ib(default='Finland')
    publish_timestamp = attr.ib(default=None)
    expiration_timestamp = attr.ib(default=None)
    embedded_subtitles = attr.ib(factory=list)

    def output_file_name(self, extension, io, resume_job=False):
        if io.outputfilename:
            return self.filename_from_template(io.outputfilename, extension)
        else:
            return self.filename_from_title(extension, io, resume_job)

    def filename_from_title(self, extension, io, resume_job):
        title = self.title or 'ylestream'
        ext = extension.extension
        filename = sane_filename(title, io.excludechars) + ext
        if io.destdir:
            filename = os.path.join(io.destdir, filename)
        if not resume_job:
            filename = self.next_available_filename(filename)
        return filename

    def next_available_filename(self, proposed):
        i = 1
        enc = sys.getfilesystemencoding()
        filename = proposed
        basename, ext = os.path.splitext(filename)
        while os.path.exists(filename.encode(enc, 'replace')):
            logger.info('%s exists, trying an alternative name' % filename)
            filename = basename + '-' + str(i) + ext
            i += 1
        return filename

    def filename_from_template(self, basename, extension):
        if extension.is_mandatory:
            return self.replace_extension(basename, extension)
        else:
            return self.append_ext_if_missing(basename, extension)

    def replace_extension(self, filename, extension):
        ext = extension.extension
        basename, old_ext = os.path.splitext(filename)
        if not old_ext or old_ext != ext:
            if old_ext:
                logger.warn('Unsupported extension {}. Replacing it with {}'.format(old_ext, ext))
            return basename + ext
        else:
            return filename

    def append_ext_if_missing(self, filename, extension):
        if '.' in filename:
            return filename
        else:
            return filename + extension.extension

    def metadata(self, io):
        flavors_meta = sorted(
            [self.flavor_meta(f) for f in self.flavors],
            key=lambda x: x.get('bitrate', 0))
        meta = [
            ('webpage', self.webpage),
            ('title', self.title),
            ('filename', self.meta_file_name(self.flavors, io)),
            ('flavors', flavors_meta),
            ('duration_seconds', self.duration_seconds),
            ('embedded_subtitles',
             [{'language': x.language, 'category': x.category}
              for x in self.embedded_subtitles]),
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
                return self.output_file_name(extensions[0], io)

        return None

    def format_timestamp(self, ts):
        return ts.isoformat() if ts else None

    def flavor_meta(self, flavor):
        if all(not s.is_valid() for s in flavor.streams):
            return self.error_flavor_meta(flavor)
        else:
            return self.valid_flavor_meta(flavor)

    def valid_flavor_meta(self, flavor):
        hard_sub_lang = flavor.hard_subtitle and flavor.hard_subtitle.lang
        if hard_sub_lang:
            hard_sub_lang = normalize_language_code(hard_sub_lang, None)

        backends = [s.name for s in flavor.streams if s.is_valid()]

        meta = [
            ('media_type', flavor.media_type),
            ('height', flavor.height),
            ('width', flavor.width),
            ('bitrate', flavor.bitrate),
            ('hard_subtitle_language', hard_sub_lang),
            ('backends', backends)
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
    def __init__(self, webpage, error_message):
        Clip.__init__(self,
                      webpage=webpage,
                      flavors=[FailedFlavor(error_message)],
                      title=None,
                      duration_seconds=None,
                      region=None,
                      publish_timestamp=None,
                      expiration_timestamp=None,
                      embedded_subtitles=[])


@attr.s
class AreenaApiProgramInfo(object):
    media_id = attr.ib()
    title = attr.ib()
    flavors = attr.ib()
    embedded_subtitles = attr.ib()
    duration_seconds = attr.ib()
    available_at_region = attr.ib()
    publish_timestamp = attr.ib()
    expiration_timestamp = attr.ib()
    pending = attr.ib()


class ClipExtractor(object):
    def __init__(self, httpclient):
        self.httpclient = httpclient

    def extract(self, url, latest_only, title_formatter, ffprobe):
        playlist = self.get_playlist(url)
        if latest_only:
            playlist = playlist[:1]

        return [self.extract_clip(clipurl, title_formatter, ffprobe)
                for clipurl in playlist]

    def get_playlist(self, url):
        raise NotImplementedError("get_playlist must be overridden")

    def extract_clip(self, url, title_formatter, ffprobe):
        raise NotImplementedError("extract_clip must be overridden")


class MergingExtractor(ClipExtractor):
    """Executes several ClipExtractors and combines stream flavors from all of them."""

    def __init__(self, extractors):
        self.extractors = extractors

    def get_playlist(self, url):
        playlist = []
        for extractor in self.extractors:
            for clip_url in extractor.get_playlist(url):
                if clip_url not in playlist:
                    playlist.append(clip_url)
        return playlist

    def extract_clip(self, url, titlerformatter, ffprobe):
        clips = [x.extract_clip(url, titlerformatter, ffprobe)
                 for x in self.extractors]
        valid_clips = [c for c in clips if not isinstance(c, FailedClip)]
        failed_clips = [c for c in clips if isinstance(c, FailedClip)]
        if valid_clips:
            all_flavors = list(itertools.chain.from_iterable(
                c.flavors for c in valid_clips))
            clip = valid_clips[0]
            clip.flavors = all_flavors
            return clip
        elif failed_clips:
            return failed_clips[0]
        else:
            return FailedClip(url, 'No clips to merge')


class AreenaPlaylist(object):
    def __init__(self, httpclient):
        self.httpclient = httpclient

    def get_playlist(self, url):
        """If url is a series page, return a list of included episode pages."""
        playlist = []
        series_id = self.program_id_from_url(url)
        if not self.is_tv_ohjelmat_url(url):
            playlist = self.get_playlist_old_style_url(
                url, series_id)

        if playlist is None:
            logger.error('Failed to parse a playlist')
            return []
        elif playlist:
            logger.debug('playlist page with %d clips' % len(playlist))
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

    def get_playlist_old_style_url(self, url, series_id):
        playlist = []
        html = self.httpclient.download_html_tree(url)
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

        playlist_json = self.httpclient.download_page(
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
                'order=publication.starttime%3Adesc%2C'
                'episode.hash%3Aasc%2Ctitle.fi%3Aasc&'
                'app_id=areena_web_frontend_prod&'
                'app_key=4622a8f8505bb056c956832a70c105d4&'
                'limit={limit}{offset_param}'.format(
                    series_id=quote_plus(series_id),
                    limit=str(page_size),
                    offset_param=offset_param))

    def is_playlist_page(self, html_tree):
        body = html_tree.xpath('/html/body[contains(@class, "series-cover-page")]')
        return len(body) != 0


class AreenaPreviewApiParser(object):
    def preview_media_id(self, data):
        return self.preview_ongoing(data).get('media_id')

    def preview_duration_seconds(self, data):
        return self.preview_ongoing(data).get('duration', {}).get('duration_in_seconds')

    def preview_title(self, data, publish_timestamp, title_formatter):
        title_object = self.preview_ongoing(data).get('title', {})
        if not title_object:
            return None

        raw_title = localization.fin_or_swe_text(title_object).strip()
        return title_formatter.format(raw_title, publish_timestamp)

    def preview_available_at_region(self, data):
        return self.preview_ongoing(data).get('region')

    def preview_timestamp(self, data):
        dt = self.preview_ongoing(data).get('start_time')
        return parse_areena_timestamp(dt)

    def preview_manifest_url(self, data):
        return self.preview_ongoing(data).get('manifest_url')

    def preview_media_url(self, data):
        return self.preview_ongoing(data).get('media_url')

    def preview_media_type(self, data):
        if not data:
            return None
        elif self.preview_ongoing(data).get('content_type') == 'AudioObject':
            return 'audio'
        else:
            return 'video'

    def preview_is_live(self, data):
        return (data or {}).get('data', {}).get('ongoing_channel') is not None

    def preview_is_pending(self, data):
        return (data or {}).get('data', {}).get('pending_event') is not None

    def preview_ongoing(self, preview):
        data = (preview or {}).get('data', {})
        return (data.get('ongoing_ondemand') or
                data.get('ongoing_event', {}) or
                data.get('ongoing_channel', {}) or
                data.get('pending_event') or
                {})


### Extract streams from an Areena webpage ###


class AreenaExtractor(AreenaPlaylist, AreenaPreviewApiParser, ClipExtractor):
    # Extracted from
    # http://player.yle.fi/assets/flowplayer-1.4.0.3/flowplayer/flowplayer.commercial-3.2.16-encrypted.swf
    AES_KEY = b'yjuap4n5ok9wzg43'

    def extract_clip(self, clip_url, title_formatter, ffprobe):
        pid = self.program_id_from_url(clip_url)
        program_info = self.program_info_for_pid(pid, clip_url,
                                                 title_formatter, ffprobe)
        return self.create_clip_or_failure(pid, program_info, clip_url)

    def create_clip_or_failure(self, pid, program_info, url):
        if not pid:
            return FailedClip(url, 'Failed to parse a program ID')

        if not program_info:
            return FailedClip(url, 'Failed to download program data')

        return self.create_clip(pid, program_info, url)

    def create_clip(self, program_id, program_info, pageurl):
        failed = self.failed_clip_if_only_invalid_streams(
            program_info.flavors, pageurl)

        if program_info.pending:
            msg = 'Stream not yet available.'
            if program_info.publish_timestamp:
                msg = ('{} Becomes available on {}'.format(
                    msg, program_info.publish_timestamp.isoformat()))
            return FailedClip(pageurl, msg)
        elif failed:
            return failed
        elif program_info.flavors:
            return Clip(
                webpage=pageurl,
                flavors=program_info.flavors,
                title=program_info.title,
                duration_seconds=program_info.duration_seconds,
                region=program_info.available_at_region,
                publish_timestamp=program_info.publish_timestamp,
                expiration_timestamp=program_info.expiration_timestamp,
                embedded_subtitles=program_info.embedded_subtitles)
        else:
            return FailedClip(pageurl, 'Media not found')

    def failed_clip_if_only_invalid_streams(self, flavors, pageurl):
        if flavors:
            all_streams = list(itertools.chain.from_iterable(
                fl.streams for fl in flavors))
        else:
            all_streams = []

        if all_streams and all(not s.is_valid() for s in all_streams):
            return FailedClip(pageurl, all_streams[0].error_message)
        else:
            return None

    def media_flavors(self, media_id, program_id, hls_manifest_url,
                      download_url, kaltura_flavors, akamai_protocol,
                      media_type, pageurl, ffprobe_binary):
        flavors = []

        if download_url:
            flavors.extend(self.download_flavors(download_url, media_type))

        if media_id:
            flavors.extend(
                self.flavors_by_media_id(
                    media_id, program_id, hls_manifest_url, kaltura_flavors,
                    akamai_protocol, media_type, pageurl, ffprobe_binary))
        elif hls_manifest_url:
            flavors.extend(
                self.hls_flavors(hls_manifest_url, media_type))

        return flavors or None

    def flavors_by_media_id(self, media_id, program_id,
                            hls_manifest_url, kaltura_flavors,
                            akamai_protocol, media_type, pageurl,
                            ffprobe_binary):
        if self.is_full_hd_media(media_id):
            logger.debug('Detected a full-HD media')
            flavors = self.hls_probe_flavors(hls_manifest_url, media_type,
                                             ffprobe_binary)
            error = [FailedFlavor('Manifest URL is missing')]
            return flavors or error
        elif self.is_html5_media(media_id):
            logger.debug('Detected an HTML5 media')
            return (kaltura_flavors or
                    self.hls_probe_flavors(hls_manifest_url, media_type,
                                           ffprobe_binary))
        elif self.is_mediakanta_media(media_id):
            parser = AkamaiFlavorParser(self.httpclient)
            medias = self.akamai_medias(program_id, media_id, akamai_protocol)
            return parser.parse(medias, pageurl, self.AES_KEY)
        else:
            return [FailedFlavor('Unknown stream flavor')]

    def is_html5_media(self, media_id):
        return media_id and media_id.startswith('29-')

    def is_full_hd_media(self, media_id):
        return media_id and media_id.startswith('55-')

    def is_elava_arkisto_media(self, media_id):
        return media_id and media_id.startswith('26-')

    def is_mediakanta_media(self, media_id):
        return media_id and media_id.startswith('6-')

    def kaltura_entry_id(self, mediaid):
        return mediaid.split('-', 1)[-1]

    def akamai_medias(self, program_id, media_id, media_protocol):
        if not media_id:
            return []

        descriptor = self.yle_media_descriptor(program_id, media_id,
                                               media_protocol)
        descriptor_proto = descriptor.get('meta', {}).get('protocol') or 'HDS'
        return descriptor.get('data', {}) \
                         .get('media', {}) \
                         .get(descriptor_proto, [])

    def hls_flavors(self, hls_manifest_url, media_type):
        if not hls_manifest_url:
            return []

        if media_type == 'video':
            backend = HLSBackend(hls_manifest_url)
        else:
            backend = HLSAudioBackend(hls_manifest_url)

        return [StreamFlavor(media_type=media_type, streams=[backend])]

    def hls_probe_flavors(self, hls_manifest_url, media_type, ffprobe_binary):
        if not hls_manifest_url:
            return []

        logger.debug('Probing for stream flavors')
        return FullHDFlavorProber().probe_flavors(
            hls_manifest_url, ffprobe_binary)

    def download_flavors(self, download_url, media_type):
        path = urlparse(download_url)[2]
        ext = os.path.splitext(path)[1] or None
        backend = WgetBackend(download_url, ext)
        return [StreamFlavor(media_type=media_type, streams=[backend])]

    def program_protocol(self, program_info, default_video_proto):
        pinfo = program_info or {}
        event = self.publish_event(program_info)
        if (event.get('media', {}).get('type') == 'AudioObject' or
            pinfo.get('mediaFormat') == 'audio' or
            pinfo.get('data', {}).get('ea', {}).get('mediaFormat') == 'audio'):
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
        media = JSONP.load_jsonp(media_jsonp_url, self.httpclient)

        if media:
            logger.debug('media:\n' + json.dumps(media, indent=2))

        return media

    def program_media_id(self, program_info):
        event = self.publish_event(program_info)
        return event.get('media', {}).get('id')

    def program_media_type(self, program_info):
        return None

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

    def publish_timestamp(self, program_info):
        ts = self.publish_event(program_info).get('startTime')
        return parse_areena_timestamp(ts)

    def expiration_timestamp(self, program_info):
        ts = self.publish_event(program_info).get('endTime')
        return parse_areena_timestamp(ts)

    def force_program_info(self):
        return False

    def program_info_for_pid(self, pid, pageurl, title_formatter, ffprobe):
        if not pid:
            return None

        if self.is_elava_arkisto_media(pid):
            preview = None
        else:
            preview_headers = {
                'Referer': pageurl,
                'Origin': 'https://areena.yle.fi'
            }
            preview = JSONP.load_json(self.preview_url(pid),
                                      self.httpclient,
                                      headers=preview_headers)

            logger.debug('preview data:\n' + json.dumps(preview, indent=2))

        if self.preview_is_live(preview) and not self.force_program_info():
            info = None
        else:
            info = JSONP.load_jsonp(self.program_info_url(pid), self.httpclient)
            logger.debug('program data:\n' + json.dumps(info, indent=2))

        media_id = (self.program_media_id(info) or
                    self.preview_media_id(preview))
        manifest_url = self.preview_manifest_url(preview)
        download_url = ((info and info.get('downloadUrl')) or
                        self.preview_media_url(preview))
        download_url = self.ignore_invalid_download_url(download_url)
        media_type = (self.program_media_type(info) or
                      self.preview_media_type(preview))
        publish_timestamp = (self.publish_timestamp(info) or
                             self.preview_timestamp(preview))
        title = (self.program_title(info, publish_timestamp, title_formatter) or
                 self.preview_title(preview, publish_timestamp, title_formatter))
        akamai_protocol = self.program_protocol(info, 'HDS')
        if self.is_html5_media(media_id):
            entry_id = self.kaltura_entry_id(media_id)
            kapi_client = YleKalturaApiClient(self.httpclient)
            playback_context = kapi_client.playback_context(entry_id, pageurl)
            kaltura_flavors = kapi_client.parse_stream_flavors(
                playback_context, pageurl)
            kaltura_subtitles = kapi_client.parse_embedded_subtitles(playback_context)
        else:
            kaltura_flavors = None
            kaltura_subtitles = []

        return AreenaApiProgramInfo(
            media_id = media_id,
            title = title,
            flavors = self.media_flavors(media_id, pid, manifest_url,
                                         download_url, kaltura_flavors,
                                         akamai_protocol, media_type,
                                         pageurl, ffprobe),
            embedded_subtitles = kaltura_subtitles,
            duration_seconds = (self.program_info_duration_seconds(info) or
                                self.preview_duration_seconds(preview)),
            available_at_region = (self.available_at_region(info) or
                                   self.preview_available_at_region(preview) or
                                   'Finland'),
            publish_timestamp = publish_timestamp,
            expiration_timestamp = self.expiration_timestamp(info),
            pending = self.preview_is_pending(preview)
        )

    def program_info_url(self, program_id):
        return 'https://player.yle.fi/api/v1/programs.jsonp?' \
            'id=%s&callback=yleEmbed.programJsonpCallback' % \
            (quote_plus(program_id))

    def preview_url(self, program_id):
        return 'https://player.api.yle.fi/v1/preview/{}.json?' \
            'language=fin&ssl=true&countryCode=FI&host=areenaylefi' \
            '&app_id=player_static_prod' \
            '&app_key=8930d72170e48303cf5f3867780d549b'.format(program_id)

    def publish_event_is_current(self, event):
        return event.get('temporalStatus') == 'currently'

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

    def program_title(self, program_info, publish_timestamp, title_formatter):
        if not program_info:
            return None

        program = program_info.get('data', {}).get('program', {})
        title_object = program.get('title')
        title = localization.fi_or_sv_text(title_object) or 'areena'

        series_title_object = program.get('partOfSeries', {}).get('title')
        series_title = localization.fi_or_sv_text(series_title_object)

        item_title = localization.fi_or_sv_text(program.get('itemTitle'))
        promotion_title = localization.fi_or_sv_text(program.get('promotionTitle'))

        part_of_season_object = program.get('partOfSeason')
        if part_of_season_object:
            season = part_of_season_object.get('seasonNumber')
        else:
            season = program.get('seasonNumber')

        return title_formatter.format(
            title=title,
            series_title=series_title,
            publish_timestamp=publish_timestamp,
            subheading=item_title or promotion_title,
            season=season,
            episode=program.get('episodeNumber')
        )

    def ignore_invalid_download_url(self, url):
        # Sometimes download url is missing the file name
        return None if (url and url.endswith('/')) else url



### Areena Live TV ###


class AreenaLiveTVHDSExtractor(AreenaExtractor):
    # TODO: get rid of the constructor and the filters argument
    def __init__(self, filters, httpclient):
        super(AreenaLiveTVHDSExtractor, self).__init__(httpclient)
        self.outlet_sort_key = self.create_outlet_sort_key(filters)

    def force_program_info(self):
        return True

    def program_info_url(self, program_id):
        quoted_pid = quote_plus(program_id)
        return 'https://player.yle.fi/api/v1/services.jsonp?' \
            'id=%s&callback=yleEmbed.simulcastJsonpCallback&' \
            'region=fi&instance=1&dataId=%s' % \
            (quoted_pid, quoted_pid)

    def program_media_id(self, program_info):
        if program_info:
            outlets = program_info.get('data', {}).get('outlets', [{}])
            sorted_outlets = sorted(outlets, key=self.outlet_sort_key)
            selected_outlet = sorted_outlets[0]
            return selected_outlet.get('outlet', {}).get('media', {}).get('id')
        else:
            return None

    def create_outlet_sort_key(self, filters):
        preferred_ordering = {"fi": 1, None: 2, "sv": 3}

        def key_func(outlet):
            language = outlet.get("outlet", {}).get("language", [None])[0]
            if filters.audiolang_matches(language):
                return 0  # Prefer the language selected by the user
            else:
                return preferred_ordering.get(language) or 99

        return key_func
    
    def program_title(self, program_info, publish_timestamp, title_formatter):
        service = self._service_info(program_info)
        title = localization.fi_or_sv_text(service.get('title')) or 'areena'
        timestamp = publish_timestamp or datetime.now()
        return title_formatter.format(title, publish_timestamp=timestamp)

    def available_at_region(self, program_info):
        return self._service_info(program_info).get('region')

    def _service_info(self, program_info):
        return (program_info or {}).get('data', {}).get('service', {})


class AreenaLiveTVHLSExtractor(AreenaExtractor):
    def get_playlist(self, url):
        return [url]

    def program_id_from_url(self, url):
        parsed = urlparse(url)
        return parsed.path.split('/')[-1]

    def preview_title(self, data, publish_timestamp, title_formatter):
        return (super(AreenaLiveTVHLSExtractor, self)
                .preview_title(data, datetime.now(), title_formatter))


### Areena live radio ###


class AreenaLiveRadioExtractor(AreenaLiveTVHLSExtractor):
    def program_id_from_url(self, url):
        parsed = urlparse(url)
        query_dict = parse_qs(parsed.query)
        if query_dict.get('_c'):
            return query_dict.get('_c')[0]
        else:
            return parsed.path.split('/')[-1]


### Elava Arkisto ###


class ElavaArkistoExtractor(AreenaExtractor):
    def get_playlist(self, url):
        tree = self.httpclient.download_html_tree(url)
        if tree is None:
            return []

        ids = tree.xpath("//article[@id='main-content']//div/@data-id")

        # TODO: The 26- IDs will point to non-existing pages. This
        # only shows up on --showepisodepage, everything else works.
        return ['https://areena.yle.fi/' + x for x in ids]

    def program_info_url(self, program_id):
        if self.is_elava_arkisto_media(program_id):
            did = program_id.split('-')[-1]
            return ('https://yle.fi/elavaarkisto/embed/%s.jsonp'
                    '?callback=yleEmbed.eaJsonpCallback'
                    '&instance=1&id=%s&lang=fi' %
                    (quote_plus(did), quote_plus(did)))
        else:
            return (super(ElavaArkistoExtractor, self)
                    .program_info_url(program_id))

    def program_media_id(self, program_info):
        mediakanta_id = program_info.get('mediakantaId')
        if mediakanta_id:
            return '6-' + mediakanta_id
        else:
            return (super(ElavaArkistoExtractor, self)
                    .program_media_id(program_info))

    def program_media_type(self, program_info):
        return program_info.get('mediaFormat')

    def program_title(self, program_info, publish_timestamp, title_formatter):
        return program_info.get('otsikko') or \
            program_info.get('title') or \
            program_info.get('originalTitle') or \
            (super(ElavaArkistoExtractor, self)
             .program_title(program_info, publish_timestamp,
                            title_formatter)) or \
            'elavaarkisto'


### Svenska Arkivet ###


class ArkivetExtractor(AreenaExtractor):
    def get_playlist(self, url):
        # The note about '26-' in ElavaArkistoDownloader applies here
        # as well
        ids = self.get_dataids(url)
        return ['https://areena.yle.fi/' + x for x in ids]

    def program_info_url(self, program_id):
        if self.is_elava_arkisto_media(program_id):
            plain_id = program_id.split('-')[-1]
            return 'https://player.yle.fi/api/v1/arkivet.jsonp?' \
                'id=%s&callback=yleEmbed.eaJsonpCallback&instance=1&lang=sv' % \
                (quote_plus(plain_id))
        else:
            return super(ArkivetExtractor, self).program_info_url(program_id)

    def program_media_id(self, program_info):
        mediakanta_id = program_info.get('data', {}) \
                                    .get('ea', {}) \
                                    .get('mediakantaId')
        if mediakanta_id:
            return "6-" + mediakanta_id
        else:
            return super(ArkivetExtractor, self).program_media_id(program_info)

    def program_title(self, program_info, publish_timestamp, title_formatter):
        ea = program_info.get('data', {}).get('ea', {})
        return (ea.get('otsikko') or
                ea.get('title') or
                ea.get('originalTitle') or
                (super(ArkivetExtractor, self)
                 .program_title(program_info, publish_timestamp,
                                title_formatter)) or
                'yle-arkivet')

    def get_dataids(self, url):
        tree = self.httpclient.download_html_tree(url)
        if tree is None:
            return []

        dataids = tree.xpath("//article[@id='main-content']//div/@data-id")
        dataids = [str(d) for d in dataids]
        return [d if '-' in d else '1-' + d for d in dataids]


### News clips at the Yle news site ###


class YleUutisetExtractor(AreenaExtractor):
    def get_playlist(self, url):
        html = self.httpclient.download_page(url)
        if html is None:
            return None

        javascript_re = re.search(r'window.__INITIAL_STATE__=(.+)', html)
        if not javascript_re:
            return []

        state = json.loads(html_unescape(javascript_re.group(1)))
        medias = state.get('article', {}).get('mainMedia', [])
        data_ids = [m.get('id') for m in medias]

        logger.debug('Found Areena data IDs: {}'.format(','.join(data_ids)))

        return [self.id_to_areena_url(id) for id in data_ids]

    def extract_video_id(self, img):
        src = str(img.get('src'))
        m = re.search(r'/13-([-0-9]+)-\d+\.jpg$', src)
        if m:
            return m.group(1)
        else:
            return None

    def id_to_areena_url(self, data_id):
        if '-' in data_id:
            areena_id = data_id
        else:
            areena_id = '1-' + data_id
        return 'https://areena.yle.fi/' + areena_id
