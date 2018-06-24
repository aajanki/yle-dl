# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import sys
import re
import os.path
import json
import xml.dom.minidom
import time
import codecs
import base64
import logging
from builtins import str
from future.moves.urllib.parse import urlparse, quote_plus, parse_qs
from future.utils import python_2_unicode_compatible
from pkg_resources import resource_filename
from . import hds
from .utils import print_enc, sane_filename
from .http import yledl_headers, download_page, download_html_tree, \
    download_to_file
from .exitcodes import RD_SUCCESS, RD_FAILED, RD_INCOMPLETE, \
    RD_SUBPROCESS_EXECUTE_FAILED, to_external_rd_code
from .backends import RTMPBackend, HDSBackend, YoutubeDLHDSBackend, \
    HLSBackend, HLSAudioBackend, WgetBackend, FallbackBackend, Subprocess

try:
    # pycryptodome
    from Cryptodome.Cipher import AES
except ImportError:
    # fallback on the obsolete pycrypto
    from Crypto.Cipher import AES


logger = logging.getLogger('yledl')


def downloader_factory(url, backends):
    if re.match(r'^https?://yle\.fi/aihe/', url) or \
            re.match(r'^https?://(areena|arenan)\.yle\.fi/26-', url):
        return ElavaArkistoDownloader(backends)
    elif re.match(r'^https?://svenska\.yle\.fi/artikel/', url):
        return ArkivetDownloader(backends)
    elif (re.match(r'^https?://areena\.yle\.fi/radio/ohjelmat/[-a-zA-Z0-9]+', url) or
          re.match(r'^https?://areena\.yle\.fi/radio/suorat/[-a-zA-Z0-9]+', url)):
        return AreenaLiveRadioDownloader(backends)
    elif re.match(r'^https?://(areena|arenan)\.yle\.fi/tv/ohjelmat/30-901\?', url):
        # Football World Cup 2018
        return AreenaSportsDownloader(backends)
    elif (re.match(r'^https?://(areena|arenan)\.yle\.fi/tv/suorat/', url) or
          re.match(r'^https?://(areena|arenan)\.yle\.fi/tv/ohjelmat/[-0-9]+\?play=yle-[-a-z0-9]+', url)):
        return Areena2014LiveDownloader(backends)
    elif re.match(r'^https?://yle\.fi/(uutiset|urheilu|saa)/', url):
        return YleUutisetDownloader(backends)
    elif re.match(r'^https?://(areena|arenan)\.yle\.fi/', url) or \
            re.match(r'^https?://yle\.fi/', url):
        return Areena2014Downloader(backends)
    else:
        return None


def parse_rtmp_single_component_app(rtmpurl):
    """Extract single path-component app and playpath from rtmpurl."""
    # YLE server requires that app is the first path component
    # only. By default librtmp would take the first two
    # components (app/appInstance).
    #
    # This also means that we can't rely on librtmp's playpath
    # parser and have to duplicate the logic here.
    k = 0
    if rtmpurl.find('://') != -1:
        i = -1
        for i, x in enumerate(rtmpurl):
            if x == '/':
                k += 1
                if k == 4:
                    break

        playpath = rtmpurl[(i+1):]
        app_only_rtmpurl = rtmpurl[:i]
    else:
        playpath = rtmpurl
        app_only_rtmpurl = ''

    ext = os.path.splitext(playpath)[1]
    if ext == '.mp4':
        playpath = 'mp4:' + playpath
        ext = '.flv'
    elif ext == '.mp3':
        playpath = 'mp3:' + playpath[:-4]

    return (app_only_rtmpurl, playpath, ext)


def normalize_language_code(lang, subtype):
    if lang == 'all' or lang == 'none':
        return lang
    elif subtype == 'hearingimpaired':
        return lang + 'h'
    else:
        language_map = {'fi': 'fin', 'sv': 'swe'}
        return language_map.get(lang, lang)


def filter_flavors(flavors, max_height, max_bitrate):
    if not flavors:
        return {}

    def sort_max_bitrate(x):
        return x.get('bitrate', 0)

    def sort_max_resolution_min_bitrate(x):
        return (x.get('height', 0), -x.get('bitrate', 0))

    def sort_max_resolution_max_bitrate(x):
        return (x.get('height', 0), x.get('bitrate', 0))

    logger.debug('Available flavors: {}'.format([{
        'bitrate': fl.get('bitrate'),
        'height': fl.get('height'),
        'width': fl.get('width')
    } for fl in flavors]))
    logger.debug('max_height: {}, max_bitrate: {}'.format(
        max_height, max_bitrate))

    filtered = [
        fl for fl in flavors
        if (max_bitrate is None or fl.get('bitrate', 0) <= max_bitrate) and
        (max_height is None or fl.get('height', 0) <= max_height)
    ]
    if filtered:
        acceptable_flavors = filtered
        reverse = False
        if max_height is not None and max_bitrate is not None:
            keyfunc = sort_max_resolution_max_bitrate
        elif max_height is not None:
            keyfunc = sort_max_resolution_min_bitrate
        else:
            keyfunc = sort_max_bitrate
    else:
        acceptable_flavors = flavors
        reverse = max_height is not None or max_bitrate is not None
        keyfunc = sort_max_bitrate

    selected = sorted(acceptable_flavors, key=keyfunc, reverse=reverse)[-1]
    logger.debug('Selected flavor: {}'.format(selected))
    return selected


def ignore_none_values(di):
    return {key: value for (key, value) in di if value is not None}


class StreamFilters(object):
    """Parameters for deciding which of potentially multiple available stream
    versions to download.
    """
    def __init__(self, latest_only=False, audiolang='', sublang='all',
                 hardsubs=False, maxbitrate=None, maxheight=None):
        self.latest_only = latest_only
        self.audiolang = audiolang
        self.sublang = sublang
        self.hardsubs = hardsubs
        self.maxbitrate = maxbitrate
        self.maxheight = maxheight

    def sublang_matches(self, langcode, subtype):
        return self._lang_matches(self.sublang, langcode, subtype)

    def audiolang_matches(self, langcode):
        return self.audiolang != '' and \
            self._lang_matches(self.audiolang, langcode, '')

    def _lang_matches(self, langA, langB, subtype):
        return normalize_language_code(langA, '') == \
          normalize_language_code(langB, subtype)


class DownloadLimits(object):
    def __init__(self, duration=None, ratelimit=None):
        self.duration = duration
        self.ratelimit = ratelimit


class IOContext(object):
    def __init__(self, outputfilename=None, destdir=None, resume=False,
                 dl_limits=DownloadLimits(), excludechars='*/|',
                 proxy=None, rtmpdump_binary=None, hds_binary=None,
                 ffmpeg_binary='ffmpeg', ffprobe_binary='ffprobe',
                 wget_binary='wget'):
        self.outputfilename = outputfilename
        self.destdir = destdir
        self.resume = resume
        self.excludechars = excludechars
        self.proxy = proxy
        self.download_limits = dl_limits

        self.rtmpdump_binary = rtmpdump_binary
        self.ffmpeg_binary = ffmpeg_binary
        self.ffprobe_binary = ffprobe_binary
        self.wget_binary = wget_binary
        if hds_binary:
            self.hds_binary = hds_binary
        else:
            self.hds_binary = \
                ['php', resource_filename(__name__, 'AdobeHDS.php')]


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


@python_2_unicode_compatible
class BackendFactory(object):
    ADOBEHDSPHP = 'adobehdsphp'
    YOUTUBEDL = 'youtubedl'

    @staticmethod
    def is_valid_hds_backend(hds_backend):
        return (hds_backend == BackendFactory.ADOBEHDSPHP or
                hds_backend == BackendFactory.YOUTUBEDL)

    @staticmethod
    def parse_backends(backend_names):
        backends = []
        for bn in backend_names:
            if not BackendFactory.is_valid_hds_backend(bn):
                logger.warning('Invalid backend: ' + bn)
                continue

            backends.append(BackendFactory(bn))
        return backends

    def __init__(self, hds_backend):
        self.hds_backend = hds_backend

    def __str__(self):
        return 'HDS backend: %s' % self.hds_backend

    def hds(self):
        if self.hds_backend == self.YOUTUBEDL:
            return YoutubeDLHDSBackend
        else:
            return HDSBackend


# Areena

class AreenaUtils(object):
    def areena_decrypt(self, data, aes_key):
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

    def download_subtitles(self, subtitles, videofilename):
        basename = os.path.splitext(videofilename)[0]
        subtitlefiles = []
        for sub in subtitles:
            filename = basename + '.' + sub.language + '.srt'
            if os.path.isfile(filename):
                logger.debug('Subtitle file {} already exists, skipping'
                             .format(filename))
            else:
                try:
                    download_to_file(sub.url, filename)
                    self.add_BOM(filename)
                    logger.info('Subtitles saved to ' + filename)
                    subtitlefiles.append(filename)
                except IOError:
                    logger.exception('Failed to download subtitles '
                                     'at %s' % sub.url)
        return subtitlefiles

    def select_subtitles(self, subtitles, filters):
        if filters.hardsubs:
            return []

        selected = []
        for sub in subtitles:
            matching_lang = (filters.sublang_matches(sub.language, '') or
                             filters.sublang == 'all')
            if sub.url and matching_lang:
                selected.append(sub)

        if selected and filters.sublang != 'all':
            selected = selected[:1]

        return selected

    def add_BOM(self, filename):
        """Add byte-order mark into a file.

        Assumes (but does not check!) that the file is UTF-8 encoded.
        """
        enc = sys.getfilesystemencoding()
        encoded_filename = filename.encode(enc, 'replace')

        with open(encoded_filename, 'rb') as infile:
            content = infile.read()
            if content.startswith(codecs.BOM_UTF8):
                return

        with open(encoded_filename, 'wb') as outfile:
            outfile.write(codecs.BOM_UTF8)
            outfile.write(content)


class KalturaUtils(object):
    def kaltura_flavors_meta(self, media_id, program_id, referer):
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


class FlavorsMetadata(object):
    def metadata(self):
        return []

    def subtitles_metadata(self):
        return []

    def subtitle_meta_representation(self, subtitle):
        return {'lang': subtitle.language, 'uri': subtitle.url}


class SportsFlavors(FlavorsMetadata):
    def __init__(self, manifesturl, ondemand_data):
        self.stream = SportsStreamUrl(manifesturl)
        self.subtitles = []
        self._ondemand_data = ondemand_data

    def metadata(self):
        return [Flavors.single_flavor_meta(self._ondemand_data)]


class KalturaFlavors(FlavorsMetadata):
    def __init__(self, kaltura_flavors, stream_meta, subtitles, filters):
        self.kaltura_flavors = kaltura_flavors
        self.subtitles = subtitles
        self.stream = self._select_matching_stream(
            kaltura_flavors, stream_meta, filters)

    def metadata(self):
        return [Flavors.single_flavor_meta(fl) for fl in self.kaltura_flavors]

    def subtitles_metadata(self):
        return [self.subtitle_meta_representation(s) for s in self.subtitles]

    def _select_matching_stream(self, flavors, meta, filters):
        # See http://cdnapi.kaltura.com/html5/html5lib/v2.56/load.php
        # for the actual Areena stream selection logic
        h264flavors = [f for f in flavors if self._is_h264_flavor(f)]
        if h264flavors:
            # Prefer non-adaptive HTTP stream
            stream_format = 'url'
            filtered_flavors = h264flavors
        elif meta.get('duration', 0) < 10:
            # short and durationless streams are not available as HLS
            stream_format = 'url'
            filtered_flavors = flavors
        else:
            # fallback to HLS if nothing else is available
            stream_format = 'applehttp'
            filtered_flavors = flavors

        return self._select_stream(filtered_flavors, stream_format, filters)

    def _is_h264_flavor(self, flavor):
        tags = flavor.get('tags', '').split(',')
        ipad_h264 = 'ipad' in tags or 'iphone' in tags
        web_h264 = (('web' in tags or 'mbr' in tags) and
                    (flavor.get('fileExt') == 'mp4'))
        return ipad_h264 or web_h264

    def _select_stream(self, flavors, stream_format, filters):
        selected_flavor = filter_flavors(
            flavors, filters.maxheight, filters.maxbitrate)
        if not selected_flavor:
            return InvalidStreamUrl('No admissible streams')
        if 'entryId' not in selected_flavor:
            return InvalidStreamUrl('No entryId in the selected flavor')

        entry_id = selected_flavor.get('entryId')
        flavor_id = selected_flavor.get('id') or '0_00000000'
        ext = '.' + (selected_flavor.get('fileExt') or 'mp4')
        return KalturaStreamUrl(entry_id, flavor_id, stream_format, ext)


class KalturaLiveAudioFlavors(FlavorsMetadata):
    def __init__(self, hlsurl):
        self.stream = KalturaLiveAudioStreamUrl(hlsurl)
        self.subtitles = []

    def metadata(self):
        return [Flavors.single_flavor_meta({}, 'audio')]


class InvalidFlavors(FlavorsMetadata):
    def __init__(self, error_message):
        self.stream = InvalidStreamUrl('Error from server: {}'.format(error_message))
        self.subtitles = []


class AkamaiFlavors(FlavorsMetadata, AreenaUtils):
    def __init__(self, media, subtitles, pageurl, filters, aes_key):
        is_hds = media.get('protocol') == 'HDS'
        crypted_url = media.get('url')
        media_url = self._decrypt_url(crypted_url, is_hds, aes_key)
        logger.debug('Media URL: {}'.format(media_url))
        if is_hds:
            if media_url:
                manifest = hds.parse_manifest(download_page(media_url))
            else:
                manifest = None
            self._metadata = self._construct_hds_metadata(media, manifest)
            self.stream = self._fail_if_url_missing(crypted_url, media_url) or \
                          self._hds_streamurl(media_url, manifest, filters)
        else:
            self._metadata = self._construct_rtmp_metadata(media)
            self.stream = self._fail_if_url_missing(crypted_url, media_url) or \
                          self._rtmp_streamurl(media_url, pageurl)
        self.subtitles = subtitles

    def metadata(self):
        return self._metadata

    def subtitles_metadata(self):
        return [self.subtitle_meta_representation(s) for s in self.subtitles]

    def _construct_hds_metadata(self, media, manifest):
        media_type = Flavors.media_type(media)
        return [Flavors.single_flavor_meta(m, media_type) for m in manifest]

    def _construct_rtmp_metadata(self, media):
        return [Flavors.single_flavor_meta(media)]
        
    def _decrypt_url(self, crypted_url, is_hds, aes_key):
        if crypted_url:
            baseurl = self.areena_decrypt(crypted_url, aes_key)
            if is_hds:
                sep = '&' if '?' in baseurl else '?'
                return baseurl + sep + \
                    'g=ABCDEFGHIJKL&hdcore=3.8.0&plugin=flowplayer-3.8.0.0'
            else:
                return baseurl
        else:
            return None

    def _hds_streamurl(self, media_url, flavors, filters):
        selected_flavor = filter_flavors(
            flavors, filters.maxheight, filters.maxbitrate)
        selected_bitrate = selected_flavor.get('bitrate')
        flavor_id = selected_flavor.get('mediaurl')
        return Areena2014HDSStreamUrl(media_url, selected_bitrate, flavor_id)

    def _rtmp_streamurl(self, media_url, pageurl):
        return Areena2014RTMPStreamUrl(pageurl, media_url)
    
    def _fail_if_url_missing(self, crypted_url, media_url):
        if not crypted_url:
            return InvalidStreamUrl('Media URL missing')
        elif not media_url:
            return InvalidStreamUrl('Decrypting media URL failed')
        else:
            return None


### Areena stream URL ###


class AreenaStreamBase(AreenaUtils):
    def __init__(self):
        self.error = None
        self.ext = '.flv'
        self.bitrate = None

    def is_valid(self):
        return not self.error

    def get_error_message(self):
        if self.is_valid():
            return None
        else:
            return self.error or 'Stream not valid'

    def to_url(self):
        return ''


class Areena2014HDSStreamUrl(AreenaStreamBase):
    def __init__(self, hds_url, bitrate, flavor_id):
        AreenaStreamBase.__init__(self)

        self.hds_url = hds_url
        self.bitrate = bitrate
        self.flavor_id = flavor_id

    def to_url(self):
        return self.hds_url

    def create_downloader(self, backends):
        downloaders = []
        for backend in backends:
            dl_constructor = backend.hds()
            downloaders.append(dl_constructor(self.hds_url, self.bitrate,
                                              self.flavor_id, self.ext))

        return FallbackBackend(downloaders)


class Areena2014RTMPStreamUrl(AreenaStreamBase):
    # Extracted from
    # http://areena.yle.fi/static/player/1.2.8/flowplayer/flowplayer.commercial-3.2.7-encrypted.swf
    AES_KEY = b'hjsadf89hk123ghk'

    def __init__(self, pageurl, streamurl):
        AreenaStreamBase.__init__(self)
        rtmpstream = self.create_rtmpstream(streamurl)
        self.rtmp_params = self.stream_to_rtmp_parameters(rtmpstream, pageurl,
                                                          False)
        if self.rtmp_params is not None:
            self.rtmp_params['app'] = self.rtmp_params['app'].split('/', 1)[0]

    def create_rtmpstream(self, streamurl):
        (rtmpurl, playpath, ext) = parse_rtmp_single_component_app(streamurl)
        playpath = playpath.split('?', 1)[0]
        return PAPIStream(streamurl, playpath)

    def is_valid(self):
        return bool(self.rtmp_params)

    def to_url(self):
        return self.rtmp_parameters_to_url(self.rtmp_params)

    def to_rtmpdump_args(self):
        if self.rtmp_params:
            return self.rtmp_parameters_to_rtmpdump_args(self.rtmp_params)
        else:
            return []

    def create_downloader(self, backends):
        args = self.to_rtmpdump_args()
        if not args:
            return None
        else:
            return RTMPBackend(args)

    def stream_to_rtmp_parameters(self, stream, pageurl, islive):
        if not stream:
            return None

        rtmp_connect = stream.connect
        rtmp_stream = stream.stream
        if not rtmp_stream:
            logger.error('No rtmp stream')
            return None

        try:
            scheme, edgefcs, rtmppath = self.rtmpurlparse(rtmp_connect)
        except ValueError:
            logger.exception('Failed to parse RTMP URL')
            return None

        ident = download_page('http://%s/fcs/ident' % edgefcs)
        if ident is None:
            logger.exception('Failed to read ident')
            return None

        logger.debug(ident)

        try:
            identxml = xml.dom.minidom.parseString(ident)
        except Exception:
            logger.exception('Invalid ident response')
            return None

        nodelist = identxml.getElementsByTagName('ip')
        if len(nodelist) < 1 or len(nodelist[0].childNodes) < 1:
            logger.error('No <ip> node!')
            return None
        rtmp_ip = nodelist[0].firstChild.nodeValue

        app_without_fcsvhost = rtmppath.lstrip('/')
        app_fields = app_without_fcsvhost.split('?', 1)
        baseapp = app_fields[0]
        if len(app_fields) > 1:
            auth = app_fields[1]
        else:
            auth = ''
        app = '%s?_fcs_vhost=%s&%s' % (baseapp, edgefcs, auth)
        rtmpbase = '%s://%s/%s' % (scheme, edgefcs, baseapp)
        tcurl = '%s://%s/%s' % (scheme, rtmp_ip, app)

        areena_swf = ('https://areena.yle.fi/static/player/1.2.8/flowplayer/'
                      'flowplayer.commercial-3.2.7-encrypted.swf')
        rtmpparams = {'rtmp': rtmpbase,
                      'app': app,
                      'playpath': rtmp_stream,
                      'tcUrl': tcurl,
                      'pageUrl': pageurl,
                      'swfUrl': areena_swf}
        if islive:
            rtmpparams['live'] = '1'

        return rtmpparams

    def rtmpurlparse(self, url):
        if '://' not in url:
            raise ValueError("Invalid RTMP URL")

        scheme, rest = url.split('://', 1)
        rtmp_scemes = ['rtmp', 'rtmpe', 'rtmps', 'rtmpt', 'rtmpte', 'rtmpts']
        if scheme not in rtmp_scemes:
            raise ValueError("Invalid scheme in RTMP URL")

        if '/' not in rest:
            raise ValueError("No separator in RTMP URL")

        server, app_and_playpath = rest.split('/', 1)
        return (scheme, server, app_and_playpath)

    def rtmp_parameters_to_url(self, params):
        components = [params['rtmp']]
        for key, value in params.items():
            if key != 'rtmp':
                components.append('%s=%s' % (key, value))
        return ' '.join(components)

    def rtmp_parameters_to_rtmpdump_args(self, params):
        args = []
        for key, value in params.items():
            if key == 'live':
                args.append('--live')
            else:
                args.append('--%s=%s' % (key, value))
        return args


class HTTPStreamUrl(object):
    def __init__(self, url):
        self.url = url
        path = urlparse(url)[2]
        self.ext = os.path.splitext(path)[1] or None
        self.bitrate = None

    def is_valid(self):
        return True

    def get_error_message(self):
        return None

    def to_url(self):
        return self.url

    def create_downloader(self, backends):
        return WgetBackend(self.url, self.ext)


class KalturaStreamUrl(HTTPStreamUrl):
    def __init__(self, entryid, flavorid, stream_format, ext='.mp4'):
        self.ext = ext
        self.stream_format = stream_format
        self.http_manifest_url = self._manifest_url(
            entryid, flavorid, 'url', ext)
        self.hls_manifest_url = self._manifest_url(
            entryid, flavorid, 'applehttp', '.m3u8')

    def to_url(self):
        if self.stream_format == 'applehttp':
            return self.hls_manifest_url
        else:
            return self.http_manifest_url

    def create_downloader(self, backends):
        if self.stream_format == 'url':
            return FallbackBackend([
                WgetBackend(self.http_manifest_url, self.ext),
                HLSBackend(self.hls_manifest_url, self.ext)
            ])
        else:
            return HLSBackend(self.hls_manifest_url, self.ext)

    def _manifest_url(self, entry_id, flavor_id, stream_format, manifest_ext):
        return ('https://cdnapisec.kaltura.com/p/1955031/sp/195503100/'
                'playManifest/entryId/{entry_id}/flavorId/{flavor_id}/'
                'format/{stream_format}/protocol/https/a{ext}?'
                'referrer=aHR0cHM6Ly9hcmVlbmEueWxlLmZp'
                '&playSessionId=11111111-1111-1111-1111-111111111111'
                '&clientTag=html5:v2.56&preferredBitrate=600'
                '&uiConfId=37558971'.format(
                    entry_id=entry_id,
                    flavor_id=flavor_id,
                    stream_format=stream_format,
                    ext=manifest_ext))


class KalturaLiveAudioStreamUrl(HTTPStreamUrl):
    def __init__(self, hlsurl):
        super(KalturaLiveAudioStreamUrl, self).__init__(hlsurl)
        self.ext = '.mp3'

    def create_downloader(self, backends):
        return HLSAudioBackend(self.url, self.ext)


class SportsStreamUrl(HTTPStreamUrl):
    def __init__(self, manifesturl):
        super(SportsStreamUrl, self).__init__(manifesturl)
        self.ext = '.mp4'

    def create_downloader(self, backends):
        return HLSBackend(self.url, self.ext, long_probe=True)


class InvalidStreamUrl(object):
    def __init__(self, error_message):
        self.error = error_message
        self.ext = None

    def is_valid(self):
        return False

    def get_error_message(self):
        return self.error

    def to_url(self):
        return ''


class PAPIStream(object):
    def __init__(self, connect, stream):
        self.connect = connect
        self.stream = stream


### Areena (the new version with beta introduced in 2014) ###

class Areena2014Downloader(AreenaUtils, KalturaUtils):
    # Extracted from
    # http://player.yle.fi/assets/flowplayer-1.4.0.3/flowplayer/flowplayer.commercial-3.2.16-encrypted.swf
    AES_KEY = b'yjuap4n5ok9wzg43'

    def __init__(self, backends):
        self.backends = backends

    def download_episodes(self, url, io, filters, postprocess_command):
        def download_clip(clip):
            downloader = clip.streamurl.create_downloader(self.backends)
            if not downloader:
                logger.error('Downloading the stream at %s is not yet '
                             'supported.' % url)
                logger.error('Try --showurl')
                return RD_FAILED

            clip_title = clip.title or 'ylestream'
            outputfile = downloader.output_filename(clip_title, io)
            downloader.warn_on_unsupported_feature(io)
            selected_subtitles = self.select_subtitles(clip.subtitles, filters)
            subtitlefiles = \
                self.download_subtitles(selected_subtitles, outputfile)
            dl_result = downloader.save_stream(clip_title, io)
            if dl_result == RD_SUCCESS:
                self.postprocess(postprocess_command, outputfile,
                                 subtitlefiles)

            return dl_result

        return self.process(download_clip, url, filters)

    def print_urls(self, url, filters):
        def print_clip_url(clip):
            print_enc(clip.streamurl.to_url())
            return RD_SUCCESS

        return self.process(print_clip_url, url, filters)

    def print_episode_pages(self, url, filters):
        for clipurl in self.get_playlist(url, filters.latest_only):
            print_enc(clipurl)

        return RD_SUCCESS

    def pipe(self, url, io, filters):
        def pipe_clip(clip):
            dl = clip.streamurl.create_downloader(self.backends)
            if not dl:
                logger.error('Downloading the stream at %s is not yet '
                             'supported.' % url)
                return RD_FAILED
            dl.warn_on_unsupported_feature(io)
            subtitles = self.select_subtitles(clip.subtitles, filters)
            subtitle_url = subtitles[0].url if subtitles else None
            return dl.pipe(io, subtitle_url)

        return self.process(pipe_clip, url, filters)

    def print_titles(self, url, io, filters):
        def print_clip_title(clip):
            print_enc(sane_filename(clip.title, io.excludechars))
            return RD_SUCCESS

        return self.process(print_clip_title, url, filters)

    def print_metadata(self, url, filters):
        playlist = self.get_playlist(url, filters.latest_only)
        playlist_meta = [self.meta_for_clip_url(clip, filters)
                         for clip in playlist]
        print_enc(json.dumps(playlist_meta, indent=2))
        return RD_SUCCESS

    def process(self, clipfunc, url, filters):
        overall_status = RD_SUCCESS
        playlist = self.get_playlist(url, filters.latest_only)
        for clipurl in playlist:
            res = self.process_single_episode(clipfunc, clipurl, filters)
            if res != RD_SUCCESS:
                overall_status = res
        return overall_status

    def get_playlist(self, url, latest_only):
        """If url is a series page, return a list of included episode pages."""
        playlist = []
        if not self.is_tv_ohjelmat_url(url):
            playlist = self.get_playlist_old_style_url(url)

        if playlist is None:
            logger.error('Failed to parse a playlist')
            return []
        elif playlist:
            logger.debug('playlist page with %d clips' % len(playlist))
        else:
            logger.debug('not a playlist')
            playlist = [url]

        if latest_only:
            playlist = playlist[:1]

        return playlist

    def is_tv_ohjelmat_url(self, url):
        return urlparse(url).path.startswith('/tv/ohjelmat/')

    def get_playlist_old_style_url(self, url):
        playlist = []
        html = download_html_tree(url)
        if html is not None and self.is_playlist_page(html):
            series_id = self.program_id_from_url(url)
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

    def process_single_episode(self, clipfunc, url, filters):
        pid = self.program_id_from_url(url)
        program_info = self.program_info_for_pid(pid)
        clip = self.create_clip_or_failure(pid, program_info, url, filters)
        if clip.streamurl.is_valid():
            res = clipfunc(clip)
            if res not in [RD_SUCCESS, RD_INCOMPLETE,
                           RD_SUBPROCESS_EXECUTE_FAILED]:
                self.print_geo_warning(program_info)
            return to_external_rd_code(res)
        else:
            logger.error('Unsupported stream: %s' %
                         clip.streamurl.get_error_message())
            self.print_geo_warning(program_info)
            return RD_FAILED

    def print_geo_warning(self, program_info):
        region = self.available_at_region(program_info)
        if region == 'Finland':
            logger.warning('Failed! If there is no clear reason '
                           'above the reason might')
            logger.warning('be a geo restriction. This stream is available '
                           'only in Finland.')

    def create_clip_or_failure(self, pid, program_info, url, filters):
        if not pid:
            return FailedClip(url, 'Failed to parse a program ID')

        if not program_info:
            return FailedClip(url, 'Failed to download program data')

        unavailable = self.unavailable_clip(program_info, url)
        return unavailable or \
            self.create_clip(program_info, pid, url, filters)

    def program_info_for_pid(self, pid):
        if not pid:
            return None

        program_info = JSONP.load_jsonp(self.program_info_url(pid))
        if not program_info:
            return None

        logger.debug('program data:')
        logger.debug(json.dumps(program_info))

        return program_info

    def unavailable_clip(self, program_info, pageurl):
        event = self.publish_event(program_info)
        expired_timestamp = self.event_expired_timestamp(event)
        if expired_timestamp:
            return FailedClip(pageurl, 'The clip has expired on %s' %
                              expired_timestamp)

        future_timestamp = self.event_in_future_timestamp(event)
        if future_timestamp:
            return FailedClip(pageurl, 'The clip will be published at %s' %
                              future_timestamp)

        return None

    def program_info_url(self, program_id):
        return 'https://player.yle.fi/api/v1/programs.jsonp?' \
            'id=%s&callback=yleEmbed.programJsonpCallback' % \
            (quote_plus(program_id))

    def create_clip(self, program_info, program_id, pageurl, filters):
        flavors = self.flavors_by_program_info(
            program_info, program_id, pageurl, filters)
        if flavors:
            return Clip(pageurl,
                        self.program_title(program_info),
                        flavors.stream,
                        flavors.subtitles)
        else:
            return FailedClip(pageurl, 'Media not found')

    def flavors_by_program_info(self, program_info, program_id,
                                  pageurl, filters):
        media_id = self.program_media_id(program_info, filters)
        if media_id:
            return self.flavors_by_media_id(
                program_info, media_id, program_id, pageurl, filters)
        else:
            return None

    def flavors_by_media_id(self, program_info, media_id, program_id,
                            pageurl, filters):
        is_html5 = media_id.startswith('29-')
        proto = 'HLS' if is_html5 else 'HDS'
        medias = self.get_akamai_medias(
            program_info, media_id, program_id, proto)
        subtitle_medias = self.filter_by_subtitles(medias, filters)
        subtitle_media = subtitle_medias[0] if subtitle_medias else {}

        if is_html5:
            logger.debug('Detected an HTML5 video')

            flavors_data, meta, error = self.kaltura_flavors_meta(
                media_id, program_id, pageurl)
            subtitles = self.media_subtitles(subtitle_media)

            if error:
                return InvalidFlavors(error)
            else:
                return KalturaFlavors(flavors_data, meta, subtitles, filters)
        else:
            if not subtitle_media:
                return None

            subtitles = self.media_subtitles(subtitle_media)
            return AkamaiFlavors(subtitle_media, subtitles, pageurl, filters,
                                 self.AES_KEY)

    def get_akamai_medias(self, program_info, media_id, program_id,
                          default_video_proto):
        proto = self.program_protocol(program_info, default_video_proto)
        descriptor = self.yle_media_descriptor(media_id, program_id, proto)
        protocol = descriptor.get('meta', {}).get('protocol') or 'HDS'
        return descriptor.get('data', {}).get('media', {}).get(protocol, [])

    def yle_media_descriptor(self, media_id, program_id, protocol):
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

    def program_id_from_url(self, url):
        parsed = urlparse(url)
        query_dict = parse_qs(parsed.query)
        play = query_dict.get('play')
        if parsed.path.startswith('/tv/ohjelmat/') and play:
            return play[0]
        else:
            return parsed.path.split('/')[-1]

    def program_media_id(self, program_info, filters):
        event = self.publish_event(program_info)
        return event.get('media', {}).get('id')

    def available_at_region(self, program_info):
        return self.publish_event(program_info).get('region')

    def publish_timestamp(self, program_info):
        return self.publish_event(program_info).get('startTime')

    def expiration_timestamp(self, program_info):
        return self.publish_event(program_info).get('endTime')

    def event_expired_timestamp(self, event):
        if event.get('temporalStatus') == 'in-past':
            return event.get('endTime')
        else:
            return None

    def event_in_future_timestamp(self, event):
        if event.get('temporalStatus') == 'in-future':
            return event.get('startTime')
        else:
            return None

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

    def program_protocol(self, program_info, default_video_proto):
        event = self.publish_event(program_info)
        if (event.get('media', {}).get('type') == 'AudioObject' or
            program_info.get('mediaFormat') == 'audio'):
            return 'RTMPE'
        else:
            return default_video_proto

    def publish_date(self, program_info):
        event = self.publish_event(program_info)
        start_time = event.get('startTime')
        short = re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', start_time or '')
        if short:
            return short.group(0)
        else:
            return start_time

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

    def publish_event_is_current(self, event):
        return event.get('temporalStatus') == 'currently'

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

    def filter_by_subtitles(self, streams, filters):
        if filters.hardsubs:
            substreams = [s for s in streams if 'hardsubtitle' in s]
        else:
            substreams = [s for s in streams if 'hardsubtitle' not in s]

        if filters.sublang == 'all':
            filtered = substreams
        else:
            filtered = [s for s in substreams
                        if self.media_matches_sublang_filter(s, filters)]

        return filtered or streams

    def media_matches_sublang_filter(self, media, filters):
        if filters.hardsubs:
            subtitle = media.get('hardsubtitle', {})
            sublang = subtitle.get('lang', '')
            subtype = subtitle.get('type', '')
            return filters.sublang_matches(sublang, subtype)
        else:
            for subtitle in media.get('subtitles', []):
                sublang = subtitle.get('lang', '')
                subtype = subtitle.get('type', '')
                if filters.sublang_matches(sublang, subtype):
                    return True
            return False

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

    def postprocess(self, postprocess_command, videofile, subtitlefiles):
        if postprocess_command:
            args = [postprocess_command, videofile]
            args.extend(subtitlefiles)
            return Subprocess().execute(args, None)

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

    def meta_for_clip_url(self, clipurl, filters):
        pid = self.program_id_from_url(clipurl)
        program_info = self.program_info_for_pid(pid)
        if not program_info:
            return {}

        return self.clip_meta(clipurl, program_info, pid, filters)

    def clip_meta(self, pageurl, program_info, program_id, filters):
        duration_seconds = self.program_info_duration_seconds(program_info)
        flavors = self.flavors_by_program_info(
            program_info, program_id, pageurl, filters)
        if flavors:
            flavors_meta = flavors.metadata()
            subtitles = flavors.subtitles_metadata()
        else:
            flavors_meta = None
            subtitles = []

        meta = [
            ('webpage', pageurl),
            ('title', self.program_title(program_info)),
            ('flavors', flavors_meta),
            ('duration_seconds', duration_seconds),
            ('subtitles', subtitles),
            ('region', self.available_at_region(program_info)),
            ('publish_timestamp', self.publish_timestamp(program_info)),
            ('expiration_timestamp', self.expiration_timestamp(program_info))
        ]
        return ignore_none_values(meta)


### Areena, full HD, 50 Hz ###


class AreenaSportsDownloader(Areena2014Downloader):
    def program_info_url(self, pid):
        return 'https://player.api.yle.fi/v1/preview/{}.json?' \
            'language=fin&ssl=true&countryCode=FI&app_id=player_static_prod' \
            '&app_key=8930d72170e48303cf5f3867780d549b'.format(quote_plus(pid))

    def program_media_id(self, program_info, filters):
        return self._event_data(program_info).get('media_id')

    def flavors_by_media_id(self, program_info, media_id, program_id,
                            pageurl, filters):
        if media_id.startswith('55-'):
            return self.full_hd_flavors(program_info)
        else:
            return super(AreenaSportsDownloader, self) \
                .flavors_by_media_id(program_info, media_id,
                                     program_id, pageurl, filters)

    def full_hd_flavors(self, program_info):
        ondemand = self._event_data(program_info)
        manifesturl = ondemand.get('manifest_url')
        if manifesturl:
            return SportsFlavors(manifesturl, ondemand)
        else:
            return InvalidFlavors('Manifest URL is missing')

    def _event_data(self, program_info):
        data = program_info.get('data', {})
        return data.get('ongoing_ondemand') or data.get('ongoing_event', {})

    def program_info_duration_seconds(self, program_info):
        event = self._event_data(program_info)
        return event.get('duration', {}).get('duration_in_seconds')

    def program_title(self, program_info):
        ondemand = self._event_data(program_info)
        titleObject = ondemand.get('title')
        return (self.fin_or_swe_text(titleObject) or 'areena').strip()


class Areena2014LiveDownloader(Areena2014Downloader):
    def program_info_url(self, program_id):
        quoted_pid = quote_plus(program_id)
        return 'https://player.yle.fi/api/v1/services.jsonp?' \
            'id=%s&callback=yleEmbed.simulcastJsonpCallback&' \
            'region=fi&instance=1&dataId=%s' % \
            (quoted_pid, quoted_pid)

    def program_media_id(self, program_info, filters):
        key_func = self.create_outlet_sort_key(filters)
        outlets = program_info.get('data', {}).get('outlets', [{}])
        sorted_outlets = sorted(outlets, key=key_func)
        selected_outlet = sorted_outlets[0]
        return selected_outlet.get('outlet', {}).get('media', {}).get('id')

    def create_outlet_sort_key(self, filters):
        preferred_ordering = {"fi": 1, None: 2, "sv": 3}

        def key_func(outlet):
            language = outlet.get("outlet", {}).get("language", [None])[0]
            if filters.audiolang_matches(language):
                return 0  # Prefer the language selected by the user
            else:
                return preferred_ordering.get(language) or 99

        return key_func

    def service_info(self, program_info):
        return program_info.get('data', {}).get('service', {})
    
    def program_title(self, program_info):
        service = self.service_info(program_info)
        title = self.fi_or_sv_text(service.get('title')) or 'areena'
        title += time.strftime('-%Y-%m-%d-%H:%M:%S')
        return title

    def available_at_region(self, program_info):
        return self.service_info(program_info).get('region')


class YleUutisetDownloader(Areena2014Downloader):
    def download_episodes(self, url, io, filters, postprocess_command):
        return self.delegate_to_areena_downloader(
            'download_episodes', url, io=io, filters=filters,
            postprocess_command=postprocess_command)

    def print_urls(self, url, filters):
        return self.delegate_to_areena_downloader(
            'print_urls', url, filters=filters)

    def print_episode_pages(self, url, filters):
        return self.delegate_to_areena_downloader(
            'print_episode_pages', url, filters=filters)

    def pipe(self, url, io, filters):
        return self.delegate_to_areena_downloader(
            'pipe', url, io, filters=filters)

    def print_titles(self, url, io, filters):
        return self.delegate_to_areena_downloader(
            'print_titles', url, io, filters)

    def print_metadata(self, url, filters):
        return self.delegate_to_areena_downloader(
            'print_metadata', url, filters=filters)

    def delegate_to_areena_downloader(self, method_name, url, *args, **kwargs):
        areena_urls = self.build_areena_urls(url)
        if areena_urls:
            logger.debug('Found areena URLs: ' + ', '.join(areena_urls))

            overall_status = RD_SUCCESS
            for url in areena_urls:
                kwcopy = dict(kwargs)
                kwcopy['url'] = url
                method = getattr(super(YleUutisetDownloader, self),
                                 method_name)
                res = method(*args, **kwcopy)
                if res != RD_SUCCESS:
                    overall_status = res

            return overall_status
        else:
            logger.error('No video stream found at ' + url)
            return RD_FAILED

    def build_areena_urls(self, url):
        html = download_html_tree(url)
        if html is None:
            return None

        divs = html.xpath('//div[contains(@class, "yle_areena_player") and @data-id]')
        dataids = [x.get('data-id') for x in divs]
        return [self.id_to_areena_url(id) for id in dataids]

    def id_to_areena_url(self, data_id):
        if '-' in data_id:
            areena_id = data_id
        else:
            areena_id = '1-' + data_id
        return 'https://areena.yle.fi/' + areena_id


class Clip(object):
    def __init__(self, pageurl, title, streamurl, subtitles):
        self.pageurl = pageurl
        self.title = title
        self.streamurl = streamurl
        self.subtitles = subtitles


class FailedClip(Clip):
    def __init__(self, pageurl, errormessage):
        Clip.__init__(self, pageurl, None, InvalidStreamUrl(errormessage),
                      None)


class Subtitle(object):
    def __init__(self, url, language):
        self.url = url
        self.language = language


### Areena live radio ###


class AreenaLiveRadioDownloader(Areena2014LiveDownloader):
    def get_playlist(self, url, latest_only):
        return [url]

    def program_id_from_url(self, pageurl):
        parsed = urlparse(pageurl)
        query_dict = parse_qs(parsed.query)
        if query_dict.get('_c'):
            return query_dict.get('_c')[0]
        else:
            return parsed.path.split('/')[-1]

    def program_info_url(self, pid):
        return 'https://player.api.yle.fi/v1/preview/{}.json?' \
            'ssl=true&countryCode=FI&app_id=player_static_prod' \
            '&app_key=8930d72170e48303cf5f3867780d549b'.format(quote_plus(pid))

    def channel_data(self, program_info):
        return program_info.get('data', {}).get('ongoing_channel', {})

    def program_media_id(self, program_info, filters):
        return self.channel_data(program_info).get('media_id')

    def flavors_by_media_id(self, program_info, media_id, program_id,
                            pageurl, filters):
        mw = self.load_mwembed(media_id, program_id, pageurl)
        package_data = self.package_data_from_mwembed(mw)
        streams = package_data.get('entryResult', {}) \
                              .get('meta', {}) \
                              .get('liveStreamConfigurations', [])
        if streams and 'url' in streams[0]:
            return KalturaLiveAudioFlavors(streams[0].get('url'))
        else:
            return None

    def program_title(self, program_info):
        titles = self.channel_data(program_info).get('title', {})
        title = self.fin_or_swe_text(titles) or 'areena'
        title += time.strftime('-%Y-%m-%d-%H:%M:%S')
        return title


### Elava Arkisto ###


class ElavaArkistoDownloader(Areena2014Downloader):
    def get_playlist(self, url, latest_only):
        tree = download_html_tree(url)
        if tree is None:
            return []

        ids = tree.xpath("//article[@id='main-content']//div/@data-id")

        # TODO: The 26- IDs will point to non-existing pages. This
        # only shows up on --showepisodepage, everything else works.
        return ['https://areena.yle.fi/' + x for x in ids]

    def program_info_url(self, program_id):
        if program_id.startswith('26-'):
            did = program_id.split('-')[-1]
            return ('https://yle.fi/elavaarkisto/embed/%s.jsonp'
                    '?callback=yleEmbed.eaJsonpCallback'
                    '&instance=1&id=%s&lang=fi' %
                    (quote_plus(did), quote_plus(did)))
        else:
            return super(ElavaArkistoDownloader, self).program_info_url(
                program_id)

    def create_clip(self, program_info, program_id, pageurl, filters):
        download_url = program_info.get('downloadUrl')
        if download_url:
            title = self.program_title(program_info)
            return Clip(pageurl, title, HTTPStreamUrl(download_url), [])
        else:
            return super(ElavaArkistoDownloader, self).create_clip(
                program_info, program_id, pageurl, filters)

    def program_media_id(self, program_info, filters):
        mediakanta_id = program_info.get('mediakantaId')
        if mediakanta_id:
            return '6-' + mediakanta_id
        else:
            return super(ElavaArkistoDownloader, self).program_media_id(
                program_info, filters)

    def program_title(self, program_info):
        return program_info.get('otsikko') or \
            program_info.get('title') or \
            program_info.get('originalTitle') or \
            super(ElavaArkistoDownloader, self).program_title(program_info) or \
            'elavaarkisto'


### Svenska Arkivet ###


class ArkivetDownloader(Areena2014Downloader):
    def get_playlist(self, url, latest_only):
        # The note about '26-' in ElavaArkistoDownloader applies here
        # as well
        ids = self.get_dataids(url)
        return ['https://areena.yle.fi/' + x for x in ids]

    def program_info_url(self, program_id):
        if program_id.startswith('26-'):
            plain_id = program_id.split('-')[-1]
            return 'https://player.yle.fi/api/v1/arkivet.jsonp?' \
                'id=%s&callback=yleEmbed.eaJsonpCallback&instance=1&lang=sv' % \
                (quote_plus(plain_id))
        else:
            return super(ArkivetDownloader, self).program_info_url(program_id)

    def program_media_id(self, program_info, filters):
        mediakanta_id = program_info.get('data', {}) \
                                    .get('ea', {}) \
                                    .get('mediakantaId')
        if mediakanta_id:
            return "6-" + mediakanta_id
        else:
            return super(ArkivetDownloader, self).program_media_id(
                program_info, filters)

    def program_title(self, program_info):
        ea = program_info.get('data', {}).get('ea', {})
        return (ea.get('otsikko') or
                ea.get('title') or
                ea.get('originalTitle') or
                super(ArkivetDownloader, self).program_title(program_info) or
                'yle-arkivet')

    def get_dataids(self, url):
        tree = download_html_tree(url)
        if tree is None:
            return []

        dataids = tree.xpath("//article[@id='main-content']//div/@data-id")
        dataids = [str(d) for d in dataids]
        return [d if '-' in d else '1-' + d for d in dataids]
