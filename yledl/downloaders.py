# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import sys
import re
import subprocess
import os
import os.path
import platform
import signal
import json
import xml.dom.minidom
import time
import codecs
import base64
import ctypes
import ctypes.util
import logging
import lxml.html
import lxml.etree
import requests
from builtins import str
from future.moves.urllib.parse import urlparse, quote_plus, parse_qs
from future.moves.urllib.error import HTTPError
from future.utils import python_2_unicode_compatible
from requests.adapters import HTTPAdapter
from pkg_resources import resource_filename
from . import hds
from .version import version
from .utils import print_enc, which

try:
    # pycryptodome
    from Cryptodome.Cipher import AES
except ImportError:
    # fallback on the obsolete pycrypto
    from Crypto.Cipher import AES


# exit codes
RD_SUCCESS = 0
RD_FAILED = 1
RD_INCOMPLETE = 2

# Internal exit codes
#
# RD_SUBPROCESS_EXECUTE_FAILED: A subprocess threw an OSError, for example,
# because the executable was not found.
RD_SUBPROCESS_EXECUTE_FAILED = 0x1000 | RD_FAILED


logger = logging.getLogger('yledl')
cached_requests_session = None


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


def download_page(url, extra_headers=None):
    """Returns contents of a URL."""
    response = http_get(url, extra_headers)
    return response.text if response else None


def download_html_tree(url, extra_headers=None):
    """Downloads a HTML document and returns it parsed as an lxml tree."""
    response = http_get(url, extra_headers)
    if response is None:
        return None

    metacharset = html_meta_charset(response.content)
    if metacharset:
        response.encoding = metacharset

    try:
        page = response.text
        return lxml.html.fromstring(page)
    except lxml.etree.XMLSyntaxError:
        logger.warn('HTML syntax error')
        return None


def http_get(url, extra_headers=None):
    if url.find('://') == -1:
        url = 'http://' + url
    if '#' in url:
        url = url[:url.find('#')]

    headers = yledl_headers()
    if extra_headers:
        headers.update(extra_headers)

    global cached_requests_session
    if cached_requests_session is None:
        cached_requests_session = create_session()

    try:
        r = cached_requests_session.get(url, headers=headers, timeout=20)
        r.raise_for_status()
    except requests.exceptions.RequestException:
        logger.exception("Can't read {}".format(url))
        return None

    return r


def create_session():
    session = requests.Session()

    try:
        from requests.packages.urllib3.util.retry import Retry

        retry = Retry(total=3,
                      backoff_factor=0.5,
                      status_forcelist=[500, 502, 503, 504])
        session.mount('http://', HTTPAdapter(max_retries=retry))
        session.mount('https://', HTTPAdapter(max_retries=retry))
    except ImportError:
        logger.warn('Requests library is too old. Retrying not supported.')

    return session


def download_to_file(url, destination_filename):
    enc = sys.getfilesystemencoding()
    encoded_filename = destination_filename.encode(enc, 'replace')
    with open(encoded_filename, 'wb') as output:
        r = requests.get(url, headers=yledl_headers(), stream=True, timeout=20)
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=4096):
            output.write(chunk)


def yledl_headers():
    headers = requests.utils.default_headers()
    headers.update({'User-Agent': yledl_user_agent()})
    return headers


def yledl_user_agent():
    return 'yle-dl/' + version.split(' ')[0]


def html_meta_charset(html_bytes):
    metacharset = re.search(br'<meta [^>]*?charset="(.*?)"', html_bytes)
    if metacharset:
        return str(metacharset.group(1))
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


def sane_filename(name, excludechars):
    tr = dict((ord(c), ord('_')) for c in excludechars)
    x = name.strip(' .').translate(tr)
    return x or 'ylevideo'


def ignore_none_values(di):
    return {key: value for (key, value) in di if value is not None}


def to_external_rd_code(rdcode):
    """Map internal RD codes to the corresponding external ones."""
    if rdcode == RD_SUBPROCESS_EXECUTE_FAILED:
        return RD_FAILED
    else:
        return rdcode


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
            return YoutubeDLHDSDump
        else:
            return HDSDump


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

        return FallbackDump(downloaders)


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
            return RTMPDump(args)

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
        return WgetDump(self.url, self.ext)


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
            return FallbackDump([
                WgetDump(self.http_manifest_url, self.ext),
                HLSDump(self.hls_manifest_url, self.ext)
            ])
        else:
            return HLSDump(self.hls_manifest_url, self.ext)

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
        return HLSDumpAudio(self.url, self.ext)


class SportsStreamUrl(HTTPStreamUrl):
    def __init__(self, manifesturl):
        super(SportsStreamUrl, self).__init__(manifesturl)
        self.ext = '.mp4'

    def create_downloader(self, backends):
        return HLSDump(self.url, self.ext, long_probe=True)


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

    def to_external_rd_code(self, rdcode):
        if rdcode == RD_SUBPROCESS_EXECUTE_FAILED:
            return RD_FAILED
        else:
            return rdcode

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


### Download a stream to a local file ###


class IOCapability(object):
    RESUME = 'resume'
    PROXY = 'proxy'
    RATELIMIT = 'ratelimit'
    DURATION = 'duration'


class BaseDownloader(object):
    def __init__(self, output_extension):
        self.ext = output_extension
        self._cached_output_file = None
        self.io_capabilities = frozenset()

    def warn_on_unsupported_feature(self, io):
        if io.resume and IOCapability.RESUME not in self.io_capabilities:
            logger.warn('Resume not supported on this stream')
        if io.proxy and IOCapability.PROXY not in self.io_capabilities:
            logger.warn('Proxy not supported on this stream. '
                        'Trying to continue anyway')
        if io.download_limits.ratelimit and \
           IOCapability.RATELIMIT not in self.io_capabilities:
            logger.warn('Rate limiting not supported on this stream')
        if io.download_limits.duration and \
           IOCapability.DURATION not in self.io_capabilities:
            logger.warning('--duration will be ignored on this stream')

    def save_stream(self, clip_title, io):
        """Deriving classes override this to perform the download"""
        raise NotImplementedError('save_stream must be overridden')

    def pipe(self, io, subtitle_url):
        """Derived classes can override this to pipe to stdout"""
        return RD_FAILED

    def outputfile_from_clip_title(self, clip_title, io, resume):
        if self._cached_output_file:
            return self._cached_output_file

        ext = self.ext or '.flv'
        filename = sane_filename(clip_title, io.excludechars) + ext
        if io.destdir:
            filename = os.path.join(io.destdir, filename)
        if not resume:
            filename = self.next_available_filename(filename)
        self._cached_output_file = filename
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

    def append_ext_if_missing(self, filename, default_ext):
        if '.' in filename:
            return filename
        else:
            return filename + (default_ext or '.flv')

    def replace_extension(self, filename, ext):
        basename, old_ext = os.path.splitext(filename)
        if not old_ext or old_ext != ext:
            if old_ext:
                logger.warn('Unsupported extension {}. Replacing it with {}'.format(old_ext, ext))
            return basename + ext
        else:
            return filename

    def log_output_file(self, outputfile, done=False):
        if outputfile and outputfile != '-':
            if done:
                logger.info('Stream saved to ' + outputfile)
            else:
                logger.info('Output file: ' + outputfile)

    def output_filename(self, clip_title, io):
        return self._construct_output_filename(clip_title, io, True)

    def _construct_output_filename(self, clip_title, io, force_extension):
        if io.outputfilename:
            if force_extension:
                return self.replace_extension(io.outputfilename, self.ext)
            else:
                return self.append_ext_if_missing(
                    io.outputfilename, self.ext)
        else:
            resume_job = io.resume and IOCapability.RESUME in self.io_capabilities
            return self.outputfile_from_clip_title(clip_title, io, resume_job)


### Dumping a stream to a file using external programs ###


class ExternalDownloader(BaseDownloader):
    def save_stream(self, clip_title, io):
        args = self.build_args(clip_title, io)
        env = self.extra_environment(io)
        outputfile = self.output_filename(clip_title, io)
        self.log_output_file(outputfile)
        retcode = self.external_downloader([args], env)
        if retcode == RD_SUCCESS:
            self.log_output_file(outputfile, True)
        return retcode

    def pipe(self, io, subtitle_url):
        commands = [self.build_pipe_args(io)]
        env = self.extra_environment(io)
        subtitle_command = self._mux_subtitles_command(io.ffmpeg_binary,
                                                       subtitle_url)
        if subtitle_command:
            commands.append(subtitle_command)
        return self.external_downloader(commands, env)

    def build_args(self, clip_title, io):
        return []

    def build_pipe_args(self, io):
        return []

    def extra_environment(self, io):
        return None

    def external_downloader(self, commands, env=None):
        return Subprocess().execute(commands, env)

    def _mux_subtitles_command(self, ffmpeg_binary, subtitle_url):
        if not ffmpeg_binary or not subtitle_url:
            return None

        if which(ffmpeg_binary):
            return [ffmpeg_binary, '-y', '-i', 'pipe:0', '-i', subtitle_url,
                    '-c', 'copy', '-c:s', 'srt', '-f', 'matroska', 'pipe:1']
        else:
            logger.warning('{} not found. Subtitles disabled.'
                           .format(ffmpeg_binary))
            logger.warning('Set the path to ffmpeg using --ffmpeg')
            return None


class Subprocess(object):
    def execute(self, commands, extra_environment):
        """Start external processes connected with pipes and wait completion.

        commands is a list commands to execute. commands[i] is a list of shell
        command and arguments.

        extra_environment is a dict of environment variables that are combined
        with os.environ.
        """
        if not commands:
            return RD_SUCCESS

        logger.debug('Executing:')
        shell_command_string = ' | '.join(' '.join(args) for args in commands)
        logger.debug(shell_command_string)

        env = self.combine_envs(extra_environment)
        try:
            process = self.start_process(commands, env)
            return self.exit_code_to_rd(process.wait())
        except KeyboardInterrupt:
            try:
                os.kill(process.pid, signal.SIGINT)
                process.wait()
            except OSError:
                # The process died before we killed it.
                pass
            return RD_INCOMPLETE
        except OSError as exc:
            logger.error('Failed to execute ' + shell_command_string)
            logger.error(exc.strerror)
            return RD_SUBPROCESS_EXECUTE_FAILED

    def combine_envs(self, extra_environment):
        env = None
        if extra_environment:
            env = dict(os.environ)
            env.update(extra_environment)
        return env

    def start_process(self, commands, env):
        """Start all commands and setup pipes."""
        assert commands

        processes = []
        for i, args in enumerate(commands):
            if i == 0 and platform.system() != 'Windows':
                preexec_fn = self._sigterm_when_parent_dies
            else:
                preexec_fn = None

            stdin = processes[-1].stdout if processes else None
            stdout = None if i == len(commands) - 1 else subprocess.PIPE
            processes.append(subprocess.Popen(
                args, stdin=stdin, stdout=stdout,
                env=env, preexec_fn=preexec_fn))

        # Causes the first process to receive SIGPIPE if the seconds
        # process exists
        for p in processes[:-1]:
            p.stdout.close()

        return processes[0]

    def exit_code_to_rd(self, exit_code):
        return RD_SUCCESS if exit_code == 0 else RD_FAILED

    def _sigterm_when_parent_dies(self):
        PR_SET_PDEATHSIG = 1

        libcname = ctypes.util.find_library('c')
        libc = libcname and ctypes.CDLL(libcname)

        try:
            libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
        except AttributeError:
            # libc is None or libc does not contain prctl
            pass


### Download stream by delegating to rtmpdump ###


class RTMPDump(ExternalDownloader):
    def __init__(self, rtmpdump_args):
        ExternalDownloader.__init__(self, '.flv')
        self.args = rtmpdump_args
        self.io_capabilities = frozenset([
            IOCapability.RESUME,
            IOCapability.DURATION
        ])

    def save_stream(self, clip_title, io):
        # rtmpdump fails to resume if the file doesn't contain at
        # least one audio frame. Remove small files to force a restart
        # from the beginning.
        filename = self.output_filename(clip_title, io)
        if io.resume and self.is_small_file(filename):
            self.remove(filename)

        return super(RTMPDump, self).save_stream(clip_title, io)

    def build_args(self, clip_title, io):
        args = [io.rtmpdump_binary]
        args += self.args
        args += ['-o', self.output_filename(clip_title, io)]
        if io.resume:
            args.append('-e')
        if io.download_limits.duration:
            args.extend(['--stop', str(io.download_limits.duration)])
        return args

    def build_pipe_args(self, io):
        args = [io.rtmpdump_binary]
        args += self.args
        args += ['-o', '-']
        return args

    def is_small_file(self, filename):
        try:
            return os.path.getsize(filename) < 1024
        except OSError:
            return False

    def remove(self, filename):
        try:
            os.remove(filename)
        except OSError:
            pass


### Download a stream by delegating to AdobeHDS.php ###


class HDSDump(ExternalDownloader):
    def __init__(self, url, bitrate, flavor_id, output_extension):
        ExternalDownloader.__init__(self, output_extension)
        self.url = url
        self.bitrate = bitrate
        self.flavor_id = flavor_id
        self.io_capabilities = frozenset([
            IOCapability.RESUME,
            IOCapability.PROXY,
            IOCapability.DURATION,
            IOCapability.RATELIMIT
        ])

    def _bitrate_option(self, bitrate):
        return ['--quality', str(bitrate)] if bitrate else []

    def _limit_options(self, download_limits):
        options = []

        if download_limits.ratelimit:
            options.extend(['--maxspeed', str(download_limits.ratelimit)])

        if download_limits.duration:
            options.extend(['--duration', str(download_limits.duration)])

        return options

    def build_args(self, clip_title, io):
        args = [
            '--delete',
            '--outfile', self.output_filename(clip_title, io)
        ]
        return self.adobehds_command_line(io, args)

    def save_stream(self, clip_title, io):
        output_name = self.output_filename(clip_title, io)
        if (io.resume and output_name != '-' and
            os.path.isfile(output_name) and
            not self.fragments_exist(self.flavor_id)):
            logger.info('{} has already been downloaded.'.format(output_name))
            return RD_SUCCESS
        else:
            return super(HDSDump, self).save_stream(clip_title, io)

    def fragments_exist(self, flavor_id):
        pattern = r'.*_{}_Seg[0-9]+-Frag[0-9]+$'.format(re.escape(flavor_id))
        files = os.listdir('.')
        return any(re.match(pattern, x) is not None for x in files)

    def pipe(self, io, subtitle_url):
        res = super(HDSDump, self).pipe(io, subtitle_url)
        self.cleanup_cookies()
        return res

    def build_pipe_args(self, io):
        return self.adobehds_command_line(io, ['--play'])

    def adobehds_command_line(self, io, extra_args):
        args = list(io.hds_binary)
        args.append('--manifest')
        args.append(self.url)
        args.extend(self._bitrate_option(self.bitrate))
        args.extend(self._limit_options(io.download_limits))
        if io.proxy:
            args.append('--proxy')
            args.append(io.proxy)
            args.append('--fproxy')
        if logger.isEnabledFor(logging.DEBUG):
            args.append('--debug')
        if extra_args:
            args.extend(extra_args)
        return args

    def cleanup_cookies(self):
        try:
            os.remove('Cookies.txt')
        except OSError:
            pass


### Download a stream delegating to the youtube_dl HDS downloader ###


class YoutubeDLHDSDump(BaseDownloader):
    def __init__(self, url, bitrate, flavor_id, output_extension):
        BaseDownloader.__init__(self, output_extension)
        self.url = url
        self.bitrate = bitrate
        self.io_capabilities = frozenset([
            IOCapability.RESUME,
            IOCapability.PROXY,
            IOCapability.RATELIMIT
        ])

    def save_stream(self, clip_title, io):
        output_name = self.output_filename(clip_title, io)
        return self._execute_youtube_dl(output_name, io)

    def pipe(self, io, subtitle_url):
        # TODO: subtitles
        return self._execute_youtube_dl('-', io)

    def _execute_youtube_dl(self, outputfile, io):
        try:
            import youtube_dl
        except ImportError:
            logger.error('Failed to import youtube_dl')
            return RD_FAILED

        if outputfile != '-':
            self.log_output_file(outputfile)

        ydlopts = {
            'logtostderr': True,
            'proxy': io.proxy,
            'verbose': logger.isEnabledFor(logging.DEBUG)
        }

        dlopts = {
            'nopart': True,
            'continuedl': outputfile != '-' and io.resume
        }
        dlopts.update(self._ratelimit_parameter(io.download_limits.ratelimit))

        ydl = youtube_dl.YoutubeDL(ydlopts)
        f4mdl = youtube_dl.downloader.F4mFD(ydl, dlopts)
        info = {'url': self.url}
        info.update(self._bitrate_parameter(self.bitrate))
        try:
            if not f4mdl.download(outputfile, info):
                return RD_FAILED
        except HTTPError:
            logger.exception('HTTP request failed')
            return RD_FAILED

        if outputfile != '-':
            self.log_output_file(outputfile, True)
        return RD_SUCCESS

    def _bitrate_parameter(self, bitrate):
        return {'tbr': bitrate} if bitrate else {}

    def _ratelimit_parameter(self, ratelimit):
        return {'ratelimit': ratelimit*1024} if ratelimit else {}


### Download a HLS stream by delegating to ffmpeg ###


class HLSDump(ExternalDownloader):
    def __init__(self, url, output_extension, long_probe=False):
        ExternalDownloader.__init__(self, output_extension)
        self.url = url
        self.io_capabilities = frozenset([IOCapability.DURATION])
        self.long_probe = long_probe

    def output_filename(self, clip_title, io):
        return self._construct_output_filename(clip_title, io, False)

    def _duration_arg(self, download_limits):
        if download_limits.duration:
            return ['-t', str(download_limits.duration)]
        else:
            return []

    def _probe_args(self):
        if self.long_probe:
            return ['-probesize', '80000000']
        else:
            return []

    def build_args(self, clip_title, io):
        output_name = self.output_filename(clip_title, io)
        return self.ffmpeg_command_line(
            io,
            ['-bsf:a', 'aac_adtstoasc', '-vcodec', 'copy',
             '-acodec', 'copy', 'file:' + output_name])

    def build_pipe_args(self, io):
        return self.ffmpeg_command_line(
            io,
            ['-vcodec', 'copy', '-acodec', 'copy',
             '-f', 'mpegts', 'pipe:1'])

    def build_pipe_with_subtitles_args(self, io, subtitle_url):
        return self.ffmpeg_command_line(
            io,
            ['-thread_queue_size', '512', '-i', subtitle_url,
             '-vcodec', 'copy', '-acodec', 'aac', '-scodec', 'copy',
             '-f', 'matroska', 'pipe:1'])

    def pipe(self, io, subtitle_url):
        if subtitle_url:
            commands = [self.build_pipe_with_subtitles_args(io, subtitle_url)]
        else:
            commands = [self.build_pipe_args(io)]
        env = self.extra_environment(io)
        return self.external_downloader(commands, env)

    def ffmpeg_command_line(self, io, output_options):
        debug = logger.isEnabledFor(logging.DEBUG)
        loglevel = 'info' if debug else 'error'
        args = [io.ffmpeg_binary, '-y',
                '-loglevel', loglevel, '-stats',
                '-thread_queue_size', '512']
        args.extend(self._probe_args())
        args.extend(['-i', self.url])
        args.extend(self._duration_arg(io.download_limits))
        args.extend(output_options)
        return args


class HLSDumpAudio(HLSDump):
    def build_args(self, clip_title, io):
        output_name = self.output_filename(clip_title, io)
        return self.ffmpeg_command_line(
            io, ['-map', '0:4?', '-f', 'mp3', 'file:' + output_name])

    def build_pipe_args(self, io):
        return self.ffmpeg_command_line(
            io, ['-map', '0:4?', '-f', 'mp3', 'pipe:1'])


### Download a plain HTTP file ###


class WgetDump(ExternalDownloader):
    def __init__(self, url, output_extension):
        ExternalDownloader.__init__(self, output_extension)
        self.url = url
        self.io_capabilities = frozenset([
            IOCapability.RESUME,
            IOCapability.RATELIMIT,
            IOCapability.PROXY
        ])

    def build_args(self, clip_title, io):
        output_name = self.output_filename(clip_title, io)
        args = self.shared_wget_args(io.wget_binary, output_name)
        args.extend([
            '--progress=bar',
            '--tries=5',
            '--random-wait'
        ])
        if io.resume:
            args.append('-c')
        if io.download_limits.ratelimit:
            args.append('--limit-rate={}k'.format(io.download_limits.ratelimit))
        args.append(self.url)
        return args

    def build_pipe_args(self, io):
        return self.shared_wget_args(io.wget_binary, '-') + [self.url]

    def shared_wget_args(self, wget_binary, output_filename):
        return [
            wget_binary,
            '-O', output_filename,
            '--no-use-server-timestamps',
            '--user-agent=' + yledl_user_agent(),
            '--timeout=20'
        ]

    def extra_environment(self, io):
        env = None
        if io.proxy:
            if 'https_proxy' in os.environ:
                logger.warn('--proxy ignored because https_proxy environment variable exists')
            else:
                env = {'https_proxy': io.proxy}
        return env


### Try multiple downloaders until one succeeds ###


class FallbackDump(object):
    def __init__(self, downloaders):
        self.downloaders = downloaders

    def save_stream(self, clip_title, io):
        def save_stream_cleanup(downloader):
            def wrapped(clip_title, io):
                outputfile = downloader.output_filename(clip_title, io)
                res = downloader.save_stream(clip_title, io)
                if needs_retry(res) and os.path.isfile(outputfile):
                    logger.debug('Removing the partially downloaded file')
                    try:
                        os.remove(outputfile)
                    except OSError:
                        logger.warn('Failed to remove a partial output file')
                return res

            return wrapped

        def needs_retry(res):
            return res not in [RD_SUCCESS, RD_INCOMPLETE]
        
        return self._retry_call(save_stream_cleanup, needs_retry,
                                clip_title, io)

    def pipe(self, io, subtitle_url):
        def pipe_action(downloader):
            return downloader.pipe

        def needs_retry(res):
            return res == RD_SUBPROCESS_EXECUTE_FAILED

        self._retry_call(pipe_action, needs_retry, io, subtitle_url)
        return RD_SUCCESS

    def output_filename(self, clip_title, io):
        if self.downloaders:
            return self.downloaders[0].output_filename(clip_title, io)

    def warn_on_unsupported_feature(self, io):
        if self.downloaders:
            self.downloaders[0].warn_on_unsupported_feature(io)

    def _retry_call(self, get_action, needs_retry, *args, **kwargs):
        latest_result = RD_SUCCESS
        for downloader in self.downloaders:
            logger.debug('Now trying downloader {}'.format(
                type(downloader).__name__))
            method = get_action(downloader)
            latest_result = method(*args, **kwargs)
            if not needs_retry(latest_result):
                return latest_result

        return latest_result
