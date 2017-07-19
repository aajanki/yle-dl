#!/usr/bin/env python2
# -*- coding: utf-8 -*-

"""
yle-dl - download videos from Yle servers

Copyright (C) 2010-2017 Antti Ajanki <antti.ajanki@iki.fi>

This script downloads video and audio streams from Yle Areena
(https://areena.yle.fi) and Elävä Arkisto
(http://yle.fi/aihe/elava-arkisto).
"""

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function
import sys
import urllib
import urllib2
import re
import subprocess
import os
import os.path
import platform
import signal
import urlparse
import json
import xml.dom.minidom
import time
import codecs
import base64
import ctypes
import ctypes.util
from Crypto.Cipher import AES
from pkg_resources import resource_filename

version = '2.20'

AREENA_NG_SWF = ('https://areena.yle.fi/static/player/1.2.8/flowplayer/'
                 'flowplayer.commercial-3.2.7-encrypted.swf')
AREENA_NG_HTTP_HEADERS = {'User-Agent': 'yle-dl/' + version.split(' ')[0]}

RTMP_SCHEMES = ['rtmp', 'rtmpe', 'rtmps', 'rtmpt', 'rtmpte', 'rtmpts']

DEFAULT_HDS_BACKENDS = ['adobehdsphp', 'youtubedl']

# list of all options that require an argument
ARGOPTS = ('--rtmp', '-r', '--host', '-n', '--port', '-c', '--socks',
           '-S', '--swfUrl', '-s', '--tcUrl', '-t', '--pageUrl', '-p',
           '--app', '-a', '--swfhash', '-w', '--swfsize', '-x', '--swfVfy',
           '-W', '--swfAge', '-X', '--auth', '-u', '--conn', '-C',
           '--flashVer', '-f', '--subscribe', '-d', '--flv', '-o',
           '--timeout', '-m', '--start', '-A', '--stop', '-B', '--token',
           '-T', '--skip', '-k', '--buffer', '-b')

# rtmpdump exit codes
RD_SUCCESS = 0
RD_FAILED = 1
RD_INCOMPLETE = 2

debug = False
excludechars_linux = '*/|'
excludechars_windows = '\"*/:<>?|'
excludechars = excludechars_linux
rtmpdump_binary = None
hds_binary = ['php', resource_filename(__name__, 'AdobeHDS.php')]
ffmpeg_binary = 'ffmpeg'
stream_proxy = None

libcname = ctypes.util.find_library('c')
libc = libcname and ctypes.CDLL(libcname)


class YleDlURLopener(urllib.FancyURLopener):
    version = AREENA_NG_HTTP_HEADERS['User-Agent']


urllib._urlopener = YleDlURLopener()


def log(msg):
    enc = sys.stderr.encoding or 'UTF-8'
    sys.stderr.write(msg.encode(enc, 'backslashreplace'))
    sys.stderr.write('\n')
    sys.stderr.flush()


def splashscreen():
    log(u'yle-dl %s: Download media files from Yle Areena and Elävä Arkisto' %
        version)
    log(u'Copyright (C) 2009-2017 Antti Ajanki <antti.ajanki@iki.fi>, license: '
        u'GPLv3')


def usage():
    """Print the usage message to stderr"""
    splashscreen()
    log('')
    log(u'%s [options] URL' % sys.argv[0])
    log(u'%s [options] -i filename' % sys.argv[0])
    log('')
    log('options:')
    log('')
    log('-o filename             Save stream to the named file')
    log('-i filename             Read input URLs to process from the named '
                                'file,')
    log('                        one URL per line')
    log('--latestepisode         Download the latest episode')
    log("--showurl               Print URL, don't download")
    log("--showtitle             Print stream title, don't download")
    log('--showepisodepage       Print web page for each episode')
    log('--vfat                  Create Windows-compatible filenames')
    log('--audiolang lang        Select stream\'s audio language, lang = fin '
                                'or swe')
    log('--sublang lang          Download subtitles, lang = fin, swe, smi, '
                                'none or all')
    log('--hardsubs              Download stream with hard subs if available')
    log('--maxbitrate br         Maximum bitrate stream to download, integer '
                                'in kB/s')
    log('                        or "best" or "worst". Not exact on HDS '
                                'streams.')
    log('--ratelimit br          Maximum bandwidth consumption, interger in kB/s')
    log('--rtmpdump path         Set path to rtmpdump binary')
    log('--ffmpeg path           Set path to ffmpeg binary')
    log('--adobehds cmd          Set command for executing AdobeHDS.php '
                                'script')
    log('                        Default: "php '
                                '/usr/local/share/yle-dl/AdobeHDS.php"')
    log('--postprocess cmd       Execute a command cmd after a successful '
                                'download.')
    log('                        cmd is called with arguments: video, '
                                'subtitle files')
    log('--proxy uri             Proxy for downloading streams')
    log('                        Example: --proxy socks5://localhost:7777')
    log('--destdir dir           Save files to dir')
    log('--backend be            Downloaders that are tried until one of them')
    log('                        succeeds (a comma-separated list). Possible '
                                'values:')
    log('                          adobehdsphp - AdobeHDS.php')
    log('                          youtubedl - youtube-dl (HDS stream)')
    log('--pipe                  Dump stream to stdout for piping to media '
                                'player')
    log('                        E.g. "yle-dl --pipe URL | vlc -"')
    log('--resume                Resume a partial download')
    log('-V, --verbose           Show verbose debug output')


def download_page(url, headers=None):
    """Returns contents of a HTML page at url."""
    if url.find('://') == -1:
        url = 'http://' + url
    if '#' in url:
        url = url[:url.find('#')]

    combined_headers = dict(
        AREENA_NG_HTTP_HEADERS.items() +
        (headers or {}).items()
    )

    request = urllib2.Request(url, headers=combined_headers)
    try:
        urlreader = urllib2.urlopen(request)
        content = urlreader.read()

        charset = urlreader.info().getparam('charset')
        if not charset:
            metacharset = re.search(r'<meta [^>]*?charset="(.*?)"', content)
            if metacharset:
                charset = metacharset.group(1)
        if not charset:
            charset = 'iso-8859-1'

        return unicode(content, charset, 'replace')
    except urllib2.URLError as exc:
        log(u"Can't read %s: %s" % (url, exc))
        return None
    except ValueError:
        log(u'Invalid URL: ' + url)
        return None


def read_urls_from_file(f):
    return [x.strip() for x in codecs.open(f, 'r', 'utf-8').readlines()]


def encode_url_utf8(url):
    """Encode the path component of url to percent-encoded UTF8."""
    (scheme, netloc, path, params, query, fragment) = urlparse.urlparse(url)

    path = path.encode('UTF8')

    # Assume that the path is already encoded if there seems to be
    # percent encoded entities.
    if re.search(r'%[0-9A-Fa-f]{2}', path) is None:
        path = urllib.quote(path, '/+')

    return urlparse.urlunparse((scheme, netloc, path, params, query, fragment))


def int_or_else(x, default):
    try:
        return int(x)
    except ValueError:
        return default


def process_url(url, destdir, url_only, title_only, from_file, print_episode_url, pipe,
                rtmpdumpargs, stream_filters, backends, postprocess_command):
    dl = downloader_factory(url, backends)
    if not dl:
        log(u'Unsupported URL %s.' % url)
        log(u'Is this really a Yle video page?')
        return RD_FAILED

    if url_only:
        return dl.print_urls(url, print_episode_url, stream_filters)
    elif title_only:
        return dl.print_titles(url, stream_filters)
    elif pipe:
        return dl.pipe(url, stream_filters)
    else:
        if from_file:
            log('')
            log(u'Now downloading from URL %s:' % url)
        return dl.download_episodes(url, stream_filters, rtmpdumpargs, destdir,
                                    postprocess_command)


def downloader_factory(url, backends):
    if re.match(r'^https?://yle\.fi/aihe/', url) or \
            re.match(r'^https?://(areena|arenan)\.yle\.fi/26-', url):
        return RetryingDownloader(ElavaArkistoDownloader, backends)
    elif re.match(r'^https?://svenska\.yle\.fi/artikel/', url):
        return RetryingDownloader(ArkivetDownloader, backends)
    elif re.match(r'^https?://(www\.)?yle\.fi/radio/[a-zA-Z0-9]+/suora', url):
        return RetryingDownloader(AreenaLiveRadioDownloader, backends)
    elif re.match(r'^https?://(areena|arenan)\.yle\.fi/tv/suorat/', url):
        return RetryingDownloader(Areena2014LiveDownloader, backends)
    elif re.match(r'^https?://yle\.fi/(uutiset|urheilu|saa)/', url):
        return RetryingDownloader(YleUutisetDownloader, backends)
    elif re.match(r'^https?://(areena|arenan)\.yle\.fi/', url) or \
            re.match(r'^https?://yle\.fi/', url):
        return RetryingDownloader(Areena2014Downloader, backends)
    else:
        return None


def bitrate_from_arg(arg):
    if arg == 'best':
        return sys.maxint
    elif arg == 'worst':
        return 0
    else:
        try:
            return int(arg)
        except ValueError:
            log(u'Invalid bitrate %s, defaulting to best' % arg)
            arg = sys.maxint


def which(program):
    """Search for program on $PATH and return the full path if found."""
    # Adapted from http://stackoverflow.com/questions/377017
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

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


class StreamFilters(object):
    """Parameters for deciding which of potentially multiple available stream
    versions to download.
    """
    def __init__(self, latest_only, audiolang, sublang, hardsubs, maxbitrate, ratelimit):
        self.latest_only = latest_only
        self.audiolang = audiolang
        self.sublang = sublang
        self.hardsubs = hardsubs
        self.maxbitrate = maxbitrate
        self.ratelimit = ratelimit

    def sublang_matches(self, langcode, subtype):
        return self._lang_matches(self.sublang, langcode, subtype)

    def audiolang_matches(self, langcode):
        return self.audiolang != '' and \
            self._lang_matches(self.audiolang, langcode, '')

    def _lang_matches(self, langA, langB, subtype):
        return normalize_language_code(langA, '') == \
          normalize_language_code(langB, subtype)


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
                log(u'Invalid backend: ' + bn)
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
        ciphertext = ciphertext + '\0'*padlen

        decrypter = AES.new(aes_key, AES.MODE_CFB, iv, segment_size=16*8)
        return decrypter.decrypt(ciphertext)[:-padlen]

    def download_subtitles(self, subtitles, filters, videofilename):
        subtitlefiles = []
        if not filters.hardsubs:
            preferred_lang = filters.sublang
            basename = os.path.splitext(videofilename)[0]
            for sub in subtitles:
                lang = sub.language
                if (filters.sublang_matches(lang, '') or
                        preferred_lang == 'all'):
                    if sub.url:
                        try:
                            enc = sys.getfilesystemencoding()
                            filename = basename + '.' + lang + '.srt'
                            subtitlefile = filename.encode(enc, 'replace')
                            urllib.urlretrieve(sub.url, subtitlefile)
                            self.add_BOM(subtitlefile)
                            log(u'Subtitles saved to ' + filename)
                            subtitlefiles.append(filename)
                            if preferred_lang != 'all':
                                return subtitlefiles
                        except IOError as exc:
                            log(u'Failed to download subtitles at %s: %s' %
                                (sub.url, exc))
        return subtitlefiles

    def add_BOM(self, filename):
        """Add byte-order mark into a file.

        Assumes (but does not check!) that the file is UTF-8 encoded.
        """
        content = open(filename, 'r').read()
        if content.startswith(codecs.BOM_UTF8):
            return

        f = open(filename, 'w')
        f.write(codecs.BOM_UTF8)
        f.write(content)
        f.close()


class KalturaUtils(object):
    def select_kaltura_stream(self, media_id, program_id, referer, filters):
        mw = self.load_mwembed(media_id, program_id, referer)
        return self.stream_from_mw(mw, filters)

    def load_mwembed(self, media_id, program_id, referer):
        entryid = self.kaltura_entry_id(media_id)
        mwembed_url = ('http://cdnapi.kaltura.com/html5/html5lib/v2.56/'
                       'mwEmbedFrame.php?&wid=_1955031&uiconf_id=32431531'
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
                       '&urid=2.56'
                       '&protocol=http'
                       '&callback=mwi_kaltura1320086810'.format(
                           entry_id = urllib.quote_plus(entryid),
                           program_id = urllib.quote_plus(program_id)))
        mw = JSONP.load_jsonp(mwembed_url, {'Referer': referer})

        if debug and mw:
            log('mwembed:')
            log(json.dumps(mw))

        return (mw or {}).get('content', '')

    def kaltura_entry_id(self, mediaid):
        return mediaid.split('-', 1)[-1]

    def stream_from_mw(self, mw, filters):
        package_data = self.package_data_from_mwembed(mw)
        flavors = (package_data
                   .get('entryResult', {})
                   .get('contextData', {})
                   .get('flavorAssets', []))
        meta = package_data.get('entryResult', {}).get('meta', {})

        web_flavors = [fl for fl in flavors if fl.get('isWeb', True)]
        num_non_web = len(flavors) - len(web_flavors)

        if debug and num_non_web > 0:
            log(u'Ignored %d non-web flavors' % num_non_web)

        if debug:
            bitrates = [fl.get('bitrate', 0) for fl in web_flavors]
            log(u'Available bitrates: %s, maxbitrate = %s' %
                (bitrates, filters.maxbitrate))

        return self.select_matching_stream(web_flavors, meta, filters)

    def select_matching_stream(self, flavors, meta, filters):
        # See http://cdnapi.kaltura.com/html5/html5lib/v2.56/load.php
        # for the actual Areena stream selection logic

        if meta.get('duration', 0) < 10:
            stream_format = 'url'
        else:
            stream_format = 'applehttp'

        return self.select_stream(flavors, stream_format, filters)

    def select_stream(self, flavors, stream_format, filters):
        selected_flavor = self.filter_flavors_by_bitrate(flavors, filters)
        if not selected_flavor:
            return InvalidStreamUrl('No admissible streams')
        if 'entryId' not in selected_flavor:
            return InvalidStreamUrl('No entryId in the selected flavor')

        entry_id = selected_flavor.get('entryId')
        flavor_id = selected_flavor.get('id', '0_00000000')
        ext = '.' + selected_flavor.get('fileExt', 'mp4')
        return self.stream_factory(entry_id, flavor_id, stream_format, ext)

    def filter_flavors_by_bitrate(self, flavors, filters):
        valid_bitrates = [fl for fl in flavors
                          if fl.get('bitrate', 0) <= filters.maxbitrate]
        if not valid_bitrates and len(flavors) >= 1:
            valid_bitrates = [min(flavors,
                                  key=lambda fl: fl.get('bitrate', 0))]

        if not valid_bitrates:
            return {}

        selected = max(valid_bitrates, key=lambda fl: fl.get('bitrate', 0))
        if debug:
            log(u'Selected bitrate: %s' % selected.get('bitrate', 0))

        return selected

    def package_data_from_mwembed(self, mw):
        m = re.search('window.kalturaIframePackageData\s*=\s*', mw, re.DOTALL)
        if not m:
            return {}

        try:
            # The string contains extra stuff after the JSON object,
            # so let's use raw_decode()
            return json.JSONDecoder().raw_decode(mw[m.end():])[0]
        except ValueError:
            log('Failed to parse kalturaIframePackageData!')
            return {}

    def stream_factory(self, entry_id, flavor_id, stream_format, ext):
        if stream_format == 'applehttp':
            return KalturaHLSStreamUrl(entry_id, flavor_id, ext)
        else:
            return KalturaHTTPStreamUrl(entry_id, flavor_id, stream_format, ext)


class KalturaStreamUtils(object):
    def manifest_url(self, entry_id, flavor_id, stream_format, manifest_ext):
        return ('http://cdnapi.kaltura.com/p/1955031/sp/195503100/'
                'playManifest/entryId/{entry_id}/flavorId/{flavor_id}/'
                'format/{stream_format}/protocol/http/a{ext}?'
                'referrer=aHR0cDovL2FyZW5hbi55bGUuZmk='
                '&playSessionId=11111111-1111-1111-1111-111111111111'
                '&clientTag=html5:v2.56&preferredBitrate=600'
                '&uiConfId=37558971'.format(
                    entry_id=entry_id,
                    flavor_id=flavor_id,
                    stream_format=stream_format,
                    ext=manifest_ext))


### Areena stream URL ###


class AreenaStreamBase(AreenaUtils):
    def __init__(self, clip, pageurl):
        self.error = None
        self.episodeurl = self.create_pageurl(clip) or pageurl
        self.ext = '.flv'

    def is_valid(self):
        return not self.error

    def get_error_message(self):
        if self.is_valid():
            return None
        else:
            return self.error or 'Stream not valid'

    def to_url(self):
        return ''

    def to_episode_url(self):
        return self.episodeurl

    def to_rtmpdump_args(self):
        return None

    def create_pageurl(self, media):
        if not media or 'type' not in media or 'id' not in media:
            return ''

        if media['type'] == 'audio':
            urltype = 'radio'
        else:
            urltype = 'tv'

        return 'https://areena.yle.fi/%s/%s' % (urltype, media['id'])


class AreenaRTMPStreamUrl(AreenaStreamBase):
    # Extracted from
    # http://areena.yle.fi/static/player/1.2.8/flowplayer/flowplayer.commercial-3.2.7-encrypted.swf
    AES_KEY = 'hjsadf89hk123ghk'

    def __init__(self, clip, pageurl):
        AreenaStreamBase.__init__(self, clip, pageurl)
        self.rtmp_params = None

    def is_valid(self):
        return bool(self.rtmp_params)

    def to_url(self):
        return self.rtmp_parameters_to_url(self.rtmp_params)

    def to_rtmpdump_args(self):
        if self.rtmp_params:
            return self.rtmp_parameters_to_rtmpdump_args(self.rtmp_params)
        else:
            return []

    def create_downloader(self, clip_title, destdir, extra_argv):
        if not self.to_rtmpdump_args():
            return None
        else:
            return RTMPDump(self, clip_title, destdir, extra_argv)

    def stream_to_rtmp_parameters(self, stream, pageurl, islive):
        if not stream:
            return None

        rtmp_connect = stream.connect
        rtmp_stream = stream.stream
        if not rtmp_stream:
            log('No rtmp stream')
            return None

        try:
            scheme, edgefcs, rtmppath = self.rtmpurlparse(rtmp_connect)
        except ValueError as exc:
            log(unicode(exc.message, 'utf-8', 'ignore'))
            return None

        ident = download_page('http://%s/fcs/ident' % edgefcs)
        if ident is None:
            log('Failed to read ident')
            return None

        if debug:
            log(ident)

        try:
            identxml = xml.dom.minidom.parseString(ident)
        except Exception as exc:
            log(unicode(exc.message, 'utf-8', 'ignore'))
            return None

        nodelist = identxml.getElementsByTagName('ip')
        if len(nodelist) < 1 or len(nodelist[0].childNodes) < 1:
            log('No <ip> node!')
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

        rtmpparams = {'rtmp': rtmpbase,
                      'app': app,
                      'playpath': rtmp_stream,
                      'tcUrl': tcurl,
                      'pageUrl': pageurl,
                      'swfUrl': AREENA_NG_SWF}
        if islive:
            rtmpparams['live'] = '1'

        return rtmpparams

    def rtmpurlparse(self, url):
        if '://' not in url:
            raise ValueError("Invalid RTMP URL")

        scheme, rest = url.split('://', 1)
        if scheme not in RTMP_SCHEMES:
            raise ValueError("Invalid RTMP URL")

        if '/' not in rest:
            raise ValueError("Invalid RTMP URL")

        server, app_and_playpath = rest.split('/', 1)
        return (scheme, server, app_and_playpath)

    def rtmp_parameters_to_url(self, params):
        components = [params['rtmp']]
        for key, value in params.iteritems():
            if key != 'rtmp':
                components.append('%s=%s' % (key, value))
        return ' '.join(components)

    def rtmp_parameters_to_rtmpdump_args(self, params):
        args = []
        for key, value in params.iteritems():
            if key == 'live':
                args.append('--live')
            else:
                args.append('--%s=%s' % (key, value))
        return args


class Areena2014HDSStreamUrl(AreenaStreamBase):
    def __init__(self, pageurl, hdsurl, filters, backend):
        AreenaStreamBase.__init__(self, {}, pageurl)
        self.filters = filters
        self.downloader_class = backend.hds()

        self.episodeurl = pageurl
        if hdsurl:
            sep = '&' if '?' in hdsurl else '?'
            self.hds_url = hdsurl + sep + \
                'g=ABCDEFGHIJKL&hdcore=3.8.0&plugin=flowplayer-3.8.0.0'
        else:
            self.hds_url = None
        self.error = None

    def is_valid(self):
        return not self.error

    def get_error_message(self):
        if self.is_valid():
            return None
        else:
            return self.error or 'Stream not valid'

    def to_url(self):
        return self.hds_url

    def to_episode_url(self):
        return self.episodeurl

    def create_downloader(self, clip_title, destdir, extra_argv):
        return self.downloader_class(self, clip_title, destdir, extra_argv,
                                     self.filters)


class Areena2014RTMPStreamUrl(AreenaRTMPStreamUrl):
    def __init__(self, pageurl, streamurl, filters):
        AreenaRTMPStreamUrl.__init__(self, None, pageurl)
        rtmpstream = self.create_rtmpstream(streamurl)
        self.rtmp_params = self.stream_to_rtmp_parameters(rtmpstream, pageurl,
                                                          False)
        self.rtmp_params['app'] = self.rtmp_params['app'].split('/', 1)[0]

    def create_rtmpstream(self, streamurl):
        (rtmpurl, playpath, ext) = parse_rtmp_single_component_app(streamurl)
        playpath = playpath.split('?', 1)[0]
        return PAPIStream(streamurl, playpath, 0, 0, False)


class HTTPStreamUrl(object):
    def __init__(self, url):
        self.url = url
        path = urlparse.urlparse(url)[2]
        self.ext = os.path.splitext(path)[1] or None

    def is_valid(self):
        return True

    def get_error_message(self):
        return None

    def to_url(self):
        return self.url

    def create_downloader(self, clip_title, destdir, extra_argv):
        return HTTPDump(self, clip_title, destdir, extra_argv)


class KalturaHLSStreamUrl(HTTPStreamUrl, KalturaStreamUtils):
    def __init__(self, entryid, flavorid, ext='.mp4'):
        self.ext = ext
        self.url = self.manifest_url(entryid, flavorid, 'applehttp', '.m3u8')

    def create_downloader(self, clip_title, destdir, extra_argv):
        return HLSDump(self, clip_title, destdir, extra_argv)


class KalturaHTTPStreamUrl(HTTPStreamUrl, KalturaStreamUtils):
    def __init__(self, entryid, flavorid, stream_format, ext='.mp4'):
        self.ext = ext
        self.url = self.manifest_url(entryid, flavorid, stream_format, ext)


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
    def __init__(self, connect, stream, videoBitrate, audioBitrate,
                 hardSubtitles):
        self.connect = connect
        self.stream = stream
        self.videoBitrate = int_or_else(videoBitrate, 0)
        self.audioBitrate = int_or_else(audioBitrate, 0)
        self.hardSubtitles = hardSubtitles

    def __str__(self):
        return json.dumps({
            'connect': self.connect,
            'stream': self.stream,
            'videoBitrate': self.videoBitrate,
            'audioBitrate': self.audioBitrate,
            'hardSubtitles': self.hardSubtitles})

    def bitrate(self):
        return self.videoBitrate + self.audioBitrate


### Areena (the new version with beta introduced in 2014) ###

class Areena2014Downloader(AreenaUtils, KalturaUtils):
    # Extracted from
    # http://player.yle.fi/assets/flowplayer-1.4.0.3/flowplayer/flowplayer.commercial-3.2.16-encrypted.swf
    AES_KEY = 'yjuap4n5ok9wzg43'

    def __init__(self, backend_factory):
        self.backend = backend_factory

    def download_episodes(self, url, filters, extra_argv, destdir,
                          postprocess_command):
        def download_clip(clip):
            downloader = clip.streamurl.create_downloader(clip.title, destdir,
                                                          extra_argv)
            if not downloader:
                log(u'Downloading the stream at %s is not yet supported.' % url)
                log(u'Try --showurl')
                return RD_FAILED

            outputfile = downloader.output_filename()
            subtitlefiles = \
                self.download_subtitles(clip.subtitles, filters, outputfile)
            dl_result = downloader.save_stream()
            if dl_result == RD_SUCCESS:
                self.postprocess(postprocess_command, outputfile,
                                 subtitlefiles)

            return dl_result

        return self.process(download_clip, url, filters)

    def print_urls(self, url, print_episode_url, filters):
        def print_clip_url(clip):
            enc = sys.getfilesystemencoding()
            if print_episode_url:
                print_url = clip.streamurl.to_episode_url()
            else:
                print_url = clip.streamurl.to_url()
            print(print_url.encode(enc, 'replace'))
            return RD_SUCCESS

        return self.process(print_clip_url, url, filters)

    def pipe(self, url, filters):
        def pipe_clip(clip):
            dl = clip.streamurl.create_downloader(clip.title, '', [])
            outputfile = dl.output_filename()
            self.download_subtitles(clip.subtitles, filters, outputfile)
            return dl.pipe()

        return self.process(pipe_clip, url, filters)

    def print_titles(self, url, filters):
        def print_clip_title(clip):
            enc = sys.getfilesystemencoding()
            print(clip.title.encode(enc, 'replace'))
            return RD_SUCCESS

        return self.process(print_clip_title, url, filters)

    def process(self, clipfunc, url, filters):
        overall_status = RD_SUCCESS
        playlist = self.get_playlist(url, filters)
        for clipurl in playlist:
            res = self.process_single_episode(clipfunc, clipurl, filters)
            if res != RD_SUCCESS:
                overall_status = res
        return overall_status

    def get_playlist(self, url, filters):
        """If url is a series page, return a list of included episode pages."""
        program_list_re = '<ul class="program-list".*?>(.*?)</ul>'
        episode_re = r'<a itemprop="url" href="([^">]+)"'

        playlist = None
        html = download_page(url)
        if html and self.is_playlist_page(html):
            listmatch = re.search(program_list_re, html, re.DOTALL)
            if listmatch:
                programlist = listmatch.group(1)
                hrefs = (m.group(1) for m in
                         re.finditer(episode_re, programlist))
                playlist = [urlparse.urljoin(url, href) for href in hrefs]

        if debug:
            if playlist:
                log('playlist page with %d clips' % len(playlist))
            else:
                log('not a playlist')

        if not playlist:
            playlist = [url]

        if filters.latest_only:
            playlist = playlist[:1]

        return playlist

    def is_playlist_page(self, html):
        playlist_meta = '<meta property="og:type" content="video.tv_show">'
        player_class = 'class="yle_areena_player"'
        return playlist_meta in html or player_class not in html

    def process_single_episode(self, clipfunc, url, filters):
        clip = self.clip_for_url(url, filters)
        if clip.streamurl.is_valid():
            return clipfunc(clip)
        else:
            log(u'Unsupported stream: %s' %
                clip.streamurl.get_error_message())
            return RD_FAILED

    def clip_for_url(self, pageurl, filters):
        pid = self.program_id_from_url(pageurl)
        if not pid:
            return FailedClip(pageurl, 'Failed to parse a program ID')

        program_info = JSONP.load_jsonp(self.program_info_url(pid))
        if not program_info:
            return FailedClip(pageurl, 'Failed to download program data')

        if debug:
            log('program data:')
            log(json.dumps(program_info))

        unavailable = self.unavailable_clip(program_info, pageurl)
        return unavailable or \
            self.create_clip(program_info, pid, pageurl, filters)

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
        return 'http://player.yle.fi/api/v1/programs.jsonp?' \
            'id=%s&callback=yleEmbed.programJsonpCallback' % \
            (urllib.quote_plus(program_id))

    def create_clip(self, program_info, program_id, pageurl, filters):
        media_id = self.program_media_id(program_info, filters)
        if not media_id:
            return FailedClip(pageurl, 'Failed to parse media ID')

        if media_id.startswith('29-'):
            if debug:
                log('Detected an HTML5 video')

            streamurl = self.select_kaltura_stream(
                media_id, program_id, pageurl, filters)
            subtitle_media = self.select_yle_media(program_info, media_id,
                                                   program_id, 'HLS', filters)
            subtitles = self.media_subtitles(subtitle_media)
        else:
            selected_media = self.select_yle_media(program_info, media_id,
                                                   program_id, 'HDS', filters)
            if not selected_media:
                return FailedClip(pageurl, 'Media not found')

            streamurl = self.media_streamurl(selected_media, pageurl, filters)
            subtitles = self.media_subtitles(selected_media)

        return Clip(pageurl,
                    self.program_title(program_info),
                    streamurl,
                    subtitles)

    def select_yle_media(self, program_info, media_id, program_id,
                         default_video_proto, filters):
        proto = self.program_protocol(program_info, default_video_proto)
        medias = self.yle_media_descriptor(media_id, program_id, proto)
        if not medias:
            return {}

        return self.select_media(medias, filters)

    def yle_media_descriptor(self, media_id, program_id, protocol):
        media_jsonp_url = 'http://player.yle.fi/api/v1/media.jsonp?' \
                          'id=%s&callback=yleEmbed.startPlayerCallback&' \
                          'mediaId=%s&protocol=%s&client=areena-flash-player' \
                          '&instance=1' % \
            (urllib.quote_plus(media_id), urllib.quote_plus(program_id),
             urllib.quote_plus(protocol))
        media = JSONP.load_jsonp(media_jsonp_url)

        if debug and media:
            log('media:')
            log(json.dumps(media))

        return media

    def program_id_from_url(self, url):
        parsed = urlparse.urlparse(url)
        return parsed.path.split('/')[-1]

    def program_media_id(self, program_info, filters):
        event = self.publish_event(program_info)
        return event.get('media', {}).get('id')

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

        if itemTitle and not title.endswith(itemTitle):
            title += ': ' + itemTitle
        elif promotionTitle and not promotionTitle.startswith(title):
            title += ': ' + promotionTitle

        date = self.publish_date(program_info)
        if date:
            title += '-' + date.replace('/', '-').replace(' ', '-')

        return title

    def program_protocol(self, program_info, default_video_proto):
        event = self.publish_event(program_info)
        if event.get('media', {}).get('type') == 'AudioObject':
            return 'RTMPE'
        else:
            return default_video_proto

    def publish_date(self, program_info):
        event = self.publish_event(program_info)
        return event.get('startTime')

    def publish_event(self, program_info):
        events = program_info.get('data', {}) \
                             .get('program', {}) \
                             .get('publicationEvent', [])

        has_current = any(self.publish_event_is_current(e) for e in events)
        if has_current:
            events = [e for e in events if self.publish_event_is_current(e)]

        with_media = [e for e in events if e.get('media')]
        if with_media:
            return with_media[0]
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

    def select_media(self, media,  filters):
        protocol = media.get('meta', {}).get('protocol') or 'HDS'
        mediaobj = media.get('data', {}).get('media', {}).get(protocol, [])
        medias = self.filter_by_subtitles(mediaobj, filters)

        if medias:
            return medias[0]
        else:
            return {}

    def media_streamurl(self, media, pageurl, filters):
        url = media.get('url')
        if not url:
            return InvalidStreamUrl('No media URL')

        decodedurl = self.areena_decrypt(url, self.AES_KEY)
        if not decodedurl:
            return InvalidStreamUrl('Decrypting media URL failed')

        if media.get('protocol') == 'HDS':
            return Areena2014HDSStreamUrl(pageurl, decodedurl, filters,
                                          self.backend)
        else:
            return Areena2014RTMPStreamUrl(pageurl, decodedurl, filters)

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
            return Subprocess().execute(args)


class Areena2014LiveDownloader(Areena2014Downloader):
    def program_info_url(self, program_id):
        quoted_pid = urllib.quote_plus(program_id)
        return 'http://player.yle.fi/api/v1/services.jsonp?' \
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

    def program_title(self, program_info):
        service = program_info.get('data', {}).get('service', {})
        title = self.fi_or_sv_text(service.get('title')) or 'areena'
        title += time.strftime('-%Y-%m-%d-%H:%M:%S')
        return title


class YleUutisetDownloader(Areena2014Downloader):
    def download_episodes(self, url, filters, extra_argv, destdir,
                          postprocess_command):
        return self.delegate_to_areena_downloader(
            'download_episodes', url, filters=filters, extra_argv=extra_argv,
            destdir=destdir, postprocess_command=postprocess_command)

    def print_urls(self, url, print_episode_url, filters):
        return self.delegate_to_areena_downloader(
            'print_urls', url, print_episode_url=print_episode_url,
            filters=filters)

    def pipe(self, url, filters):
        return self.delegate_to_areena_downloader(
            'pipe', url, filters=filters)

    def print_titles(self, url, filters):
        return self.delegate_to_areena_downloader(
            'print_titles', url, filters=filters)

    def delegate_to_areena_downloader(self, method_name, url, *args, **kwargs):
        areena_urls = self.build_areena_urls(url)
        if areena_urls:
            log(u'Found areena URLs: ' + ', '.join(areena_urls))

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
            log(u'No video stream found at ' + url)
            return RD_FAILED

    def build_areena_urls(self, url):
        html = download_page(url)
        if not html:
            return None

        player_re = r'<div[^>]*class="[^>]*yle_areena_player[^>]*data-id="([0-9-]+)"[^>]*>'
        dataids = re.findall(player_re, html, re.DOTALL)
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
    def get_playlist(self, url, filters):
        return [url]

    def program_id_from_url(self, pageurl):
        html = download_page(pageurl)
        if not html:
            return None

        radioid = re.search(r'"id": *"/([0-9]+)"', html)
        if not radioid:
            return None

        # Extracted from http://player.yle.fi/assets/js/mainEmbed.js
        radioid_to_mediaid = {
            2: "ylex",
            100: "ylex-video",
            4: "yle-radio-vega",
            54: "radio-vega-huvudstadsregionen",
            59: "radio-vega-ostnyland",
            55: "radio-vega-aboland",
            57: "radio-vega-vastnyland",
            44: "yle-x3m",
            1: "yle-radio-1",
            48: "yle-puhe",
            17: "yle-klassinen",
            93: "yle-sami-radio",
            10: "ylen-aikainen",
            3: "yle-radio-suomi",
            50: "etela-karjalan-radio",
            61: "etela-savon-radio",
            81: "kainuun-radio",
            51: "kymenlaakson-radio",
            41: "lahden-radio",
            90: "lapin-radio",
            80: "oulu-radio",
            70: "pohjanmaan-radio",
            62: "pohjois-karjalan-radio",
            12: "radio-ita-uusimaa",
            42: "radio-hame",
            71: "radio-keski-pohjanmaa",
            30: "radio-keski-suomi",
            91: "radio-perameri",
            60: "radio-savo",
            21: "satakunnan-radio",
            40: "tampereen-radio",
            20: "turun-radio",
            11: "ylen-lantinen"}

        return radioid_to_mediaid[int(radioid.group(1))]


### Elava Arkisto ###


class ElavaArkistoDownloader(Areena2014Downloader):
    def get_playlist(self, url, filters):
        page = download_page(url)
        return re.findall(r' data-id="((?:1-|26-)[0-9]+)"', page or '')

    def program_info_url(self, program_id):
        if program_id.startswith('26-'):
            did = program_id.split('-')[-1]
            return ('http://yle.fi/elavaarkisto/embed/%s.jsonp'
                    '?callback=yleEmbed.eaJsonpCallback'
                    '&instance=1&id=%s&lang=fi' %
                    (urllib.quote_plus(did), urllib.quote_plus(did)))
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

    def program_id_from_url(self, program_id):
        return program_id

    def program_title(self, program_info):
        return program_info.get('title') or \
            program_info.get('originalTitle') or \
            super(ElavaArkistoDownloader, self).program_title(program_info) or \
            'elavaarkisto'


### Svenska Arkivet ###


class ArkivetDownloader(Areena2014Downloader):
    def get_playlist(self, url, filters):
        return self.get_dataids(url)

    def program_info_url(self, program_id):
        if program_id.startswith('26-'):
            plain_id = program_id.split('-')[-1]
            return 'https://player.yle.fi/api/v1/arkivet.jsonp?' \
                'id=%s&callback=yleEmbed.eaJsonpCallback&instance=1&lang=sv' % \
                (urllib.quote_plus(plain_id))
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

    def program_id_from_url(self, program_id):
        return program_id

    def program_title(self, program_info):
        ea = program_info.get('data', {}).get('ea', {})
        return (ea.get('otsikko') or
                ea.get('title') or
                ea.get('originalTitle') or
                super(ArkivetDownloader, self).program_title(program_info) or
                'yle-arkivet')

    def get_dataids(self, url):
        page = download_page(url)
        if not page:
            return []

        dataids = re.findall(r' data-id="((?:1-|26-)?[0-9]+)"', page)
        dataids = [d if '-' in d else '1-' + d for d in dataids]
        return dataids


### Downloader wrapper class that retries using different backends ###
### until the download succeeds ###


class RetryingDownloader(object):
    def __init__(self, wrapped_class, backend_factories):
        self.wrapped_class = wrapped_class
        self.backends = list(backend_factories)

    def _create_next_downloader(self):
        if self.backends:
            backend = self.backends.pop(0)
            if debug:
                log(str(backend))
            return self.wrapped_class(backend)
        else:
            return None

    def _retry_call(self, method_name, *args, **kwargs):
        downloader = self._create_next_downloader()
        if not downloader:
            return RD_FAILED

        method = getattr(downloader, method_name)
        res = method(*args, **kwargs)
        if res == RD_FAILED:
            return self._retry_call(method_name, *args, **kwargs)
        else:
            return res

    def print_urls(self, *args, **kwargs):
        return self._retry_call('print_urls', *args, **kwargs)

    def print_titles(self, *args, **kwargs):
        return self._retry_call('print_titles', *args, **kwargs)

    def download_episodes(self, *args, **kwargs):
        return self._retry_call('download_episodes', *args, **kwargs)

    def pipe(self, *args, **kwargs):
        return self._retry_call('pipe', *args, **kwargs)


### Download a stream to a local file ###


class BaseDownloader(object):
    def __init__(self, stream, clip_title, destdir, extra_argv):
        self.stream = stream
        self.clip_title = clip_title or 'ylestream'
        self.extra_argv = extra_argv or []
        self.destdir = destdir or ''
        self._cached_output_file = None

        if self.is_resume_job(extra_argv) and not self.resume_supported():
            log('Warning: Resume not supported on this stream')

    def save_stream(self):
        """Deriving classes override this to perform the download"""
        raise NotImplementedError('save_stream must be overridden')

    def pipe(self):
        """Derived classes can override this to pipe to stdout"""
        return RD_FAILED

    def outputfile_from_clip_title(self, resume=False):
        if self._cached_output_file:
            return self._cached_output_file

        ext = self.stream.ext or '.flv'
        filename = self.sane_filename(self.clip_title) + ext
        if self.destdir:
            filename = os.path.join(self.destdir, filename)
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
            log(u'%s exists, trying an alternative name' % filename)
            filename = basename + '-' + str(i) + ext
            i += 1

        return filename

    def outputfile_from_args(self, args_in):
        if not args_in:
            return None

        prev = None
        args = list(args_in)  # copy
        while args:
            opt = args.pop()
            if opt in ('-o', '--flv'):
                return self.append_ext_if_missing(prev, self.stream.ext)
            prev = opt
        return None

    def append_ext_if_missing(self, filename, default_ext):
        if '.' in filename:
            return filename
        else:
            return filename + (default_ext or '.flv')

    def log_output_file(self, outputfile, done=False):
        if outputfile and outputfile != '-':
            if done:
                log(u'Stream saved to ' + outputfile)
            else:
                log(u'Output file: ' + outputfile)

    def sane_filename(self, name):
        if isinstance(name, str):
            name = unicode(name, 'utf-8', 'ignore')
        tr = dict((ord(c), ord(u'_')) for c in excludechars)
        x = name.strip(' .').translate(tr)
        return x or u'ylevideo'

    def output_filename(self):
        resume_job = (self.is_resume_job(self.extra_argv) and
                      self.resume_supported())
        return (self.outputfile_from_args(self.extra_argv) or
                self.outputfile_from_clip_title(resume=resume_job))

    def resume_supported(self):
        return False

    def is_resume_job(self, args):
        return '--resume' in args or '-e' in args


### Dumping a stream to a file using external programs ###


class ExternalDownloader(BaseDownloader):
    def save_stream(self):
        args = self.build_args()
        outputfile = self.outputfile_from_external_args(args)
        self.log_output_file(outputfile)
        retcode = self.external_downloader(args)
        if retcode == RD_SUCCESS:
            self.log_output_file(outputfile, True)
        return retcode

    def build_args(self):
        return []

    def outputfile_from_external_args(self, args):
        return self.outputfile_from_args(args)

    def external_downloader(self, args):
        return Subprocess().execute(args)


class Subprocess(object):
    def execute(self, args):
        """Start an external process such as rtmpdump with argument list args
        and wait until completion.
        """
        if debug:
            log('Executing:')
            log(' '.join(args))

        enc = sys.getfilesystemencoding()
        encoded_args = [x.encode(enc, 'replace') for x in args]

        try:
            if platform.system() == 'Windows':
                process = subprocess.Popen(encoded_args)
            else:
                process = subprocess.Popen(
                    encoded_args, preexec_fn=self._sigterm_when_parent_dies)
            return process.wait()
        except KeyboardInterrupt:
            try:
                os.kill(process.pid, signal.SIGINT)
                process.wait()
            except OSError:
                # The process died before we killed it.
                pass
            return RD_INCOMPLETE
        except OSError as exc:
            log(u'Failed to execute ' + ' '.join(args))
            log(unicode(exc.strerror, 'UTF-8', 'replace'))
            return RD_FAILED

    def _sigterm_when_parent_dies(self):
        PR_SET_PDEATHSIG = 1

        try:
            libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
        except AttributeError:
            # libc is None or libc does not contain prctl
            pass


### Download stream by delegating to rtmpdump ###


class RTMPDump(ExternalDownloader):
    def resume_supported(self):
        return True

    def build_args(self):
        args = [rtmpdump_binary]
        args += self.stream.to_rtmpdump_args()
        args += self._outputparams_unless_defined_in_extra_argv()
        args += self.extra_argv
        return args

    def _outputparams_unless_defined_in_extra_argv(self):
        if self.outputfile_from_args(self.extra_argv):
            return []
        else:
            return ['-o', self.output_filename()]

    def pipe(self):
        args = [rtmpdump_binary]
        args += self.stream.to_rtmpdump_args()
        args += ['-o', '-']
        self.external_downloader(args)
        return RD_SUCCESS


### Download a stream by delegating to AdobeHDS.php ###


class HDSDump(ExternalDownloader):
    def __init__(self, stream, clip_title, destdir, extra_argv, filters):
        ExternalDownloader.__init__(self, stream, clip_title, destdir,
                                    extra_argv)
        self.quality_options = self._bitrate_to_quality(filters.maxbitrate)
        self.ratelimit_options = self._ratelimit(filters.ratelimit)

    def resume_supported(self):
        return True

    def _bitrate_to_quality(self, maxbitrate):
        # Approximate because there is no easy way to find out the
        # available bitrates in the HDS stream
        if maxbitrate < 1000:
            return ['--quality', 'low']
        elif maxbitrate < 2000:
            return ['--quality', 'medium']
        else:
            return []

    def _ratelimit(self, limit):
        if limit:
            return ['--maxspeed', str(limit)]
        else:
            return []

    def build_args(self):
        return self.adobehds_command_line([
            '--delete',
            '--outfile', self.output_filename()])

    def pipe(self):
        args = self.adobehds_command_line(['--play'])
        self.external_downloader(args)
        self.cleanup_cookies()
        return RD_SUCCESS

    def adobehds_command_line(self, extra_args):
        global hds_binary
        global stream_proxy

        args = list(hds_binary)
        args.append('--manifest')
        args.append(self.stream.to_url())
        args.extend(self.quality_options)
        args.extend(self.ratelimit_options)
        if stream_proxy:
            args.append('--proxy')
            args.append(stream_proxy)
            args.append('--fproxy')
        if debug:
            args.append('--debug')
        if extra_args:
            args.extend(extra_args)
        return args

    def outputfile_from_external_args(self, args_in):
        if not args_in:
            return None

        try:
            i = args_in.index('--outfile')
        except ValueError:
            i = -1

        if i >= 0 and i+1 < len(args_in):
            return args_in[i+1]
        else:
            return None

    def cleanup_cookies(self):
        try:
            os.remove('Cookies.txt')
        except OSError:
            pass


### Download a stream delegating to the youtube_dl HDS downloader ###


class YoutubeDLHDSDump(BaseDownloader):
    def __init__(self, stream, clip_title, destdir, extra_argv, filters):
        BaseDownloader.__init__(self, stream, clip_title, destdir, extra_argv)
        self.maxbitrate = filters.maxbitrate
        self.ratelimit = filters.ratelimit

    def resume_supported(self):
        return True

    def save_stream(self):
        return self._execute_youtube_dl(self.output_filename())

    def pipe(self):
        return self._execute_youtube_dl(u'-')

    def _execute_youtube_dl(self, outputfile):
        try:
            import youtube_dl
        except ImportError:
            log(u'Failed to import youtube_dl')
            return RD_FAILED

        if outputfile != '-':
            self.log_output_file(outputfile)

        proxy = None
        if stream_proxy:
            proxy = stream_proxy

        ydlopts = {
            'logtostderr': True,
            'proxy': proxy,
            'verbose': debug
        }

        dlopts = {
            'nopart': True,
            'continuedl': (outputfile != '-' and
                           self.is_resume_job(self.extra_argv))
        }
        dlopts.update(self._ratelimit_parameter())

        ydl = youtube_dl.YoutubeDL(ydlopts)
        f4mdl = youtube_dl.downloader.F4mFD(ydl, dlopts)
        info = {'url': self.stream.to_url()}
        info.update(self._bitrate_parameter())
        try:
            if not f4mdl.download(outputfile, info):
                return RD_FAILED
        except urllib2.HTTPError as exc:
            log(u'HTTP request failed: %s %s' % (exc.code, exc.reason))
            return RD_FAILED

        if outputfile != '-':
            self.log_output_file(outputfile, True)
        return RD_SUCCESS

    def _stream_bitrates(self):
        manifest = download_page(self.stream.to_url())
        if not manifest:
            return []

        try:
            manifest_xml = xml.dom.minidom.parseString(manifest)
        except Exception as exc:
            log(unicode(exc.message, 'utf-8', 'ignore'))
            return []

        medias = manifest_xml.getElementsByTagName('media')
        bitrates = (int_or_else(m.getAttribute('bitrate'), 0) for m in medias)
        return [br for br in bitrates if br > 0]

    def _bitrate_parameter(self):
        bitrates = self._stream_bitrates()
        if debug:
            log(u'Available bitrates: %s, maxbitrate = %s' %
                (bitrates, self.maxbitrate))

        if not bitrates:
            return {}

        acceptable_bitrates = [br for br in bitrates if br <= self.maxbitrate]
        if not acceptable_bitrates:
            selected_bitrate = min(bitrates)
        else:
            selected_bitrate = max(acceptable_bitrates)

        if debug:
            log(u'Selected bitrate: %s' % selected_bitrate)

        return {'tbr': selected_bitrate}

    def _ratelimit_parameter(self):
        if self.ratelimit:
            return {'ratelimit': self.ratelimit*1024}
        else:
            return {}


### Download a HLS stream by delegating to ffmpeg ###


class HLSDump(ExternalDownloader):
    def build_args(self):
        return self.ffmpeg_command_line(['file:' + self.output_filename()])

    def pipe(self):
        args = self.ffmpeg_command_line(['-f', 'matroska', 'pipe:1'])
        self.external_downloader(args)
        return RD_SUCCESS

    def ffmpeg_command_line(self, output_options):
        global ffmpeg_binary

        loglevel = 'info' if debug else 'error'
        args = [ffmpeg_binary, '-y',
                '-loglevel', loglevel, '-stats',
                '-i', self.stream.to_url(),
                '-bsf:a', 'aac_adtstoasc',
                '-vcodec', 'copy', '-acodec', 'copy']
        args.extend(output_options)
        return args

    def outputfile_from_external_args(self, args):
        return args[-1]


### Download a plain HTTP file ###


class HTTPDump(BaseDownloader):
    def save_stream(self):
        log('Downloading from HTTP server...')
        if debug:
            log('URL: %s' % self.stream.to_url())
        filename = self.output_filename()
        self.log_output_file(filename)

        enc = sys.getfilesystemencoding()
        try:
            urllib.urlretrieve(self.stream.to_url(), filename.encode(enc))
        except IOError as exc:
            log(u'Download failed: ' +
                unicode(exc.message, 'UTF-8', 'replace'))
            return RD_FAILED

        self.log_output_file(filename, True)
        return RD_SUCCESS

    def pipe(self):
        url = self.stream.to_url()
        if debug:
            log('URL: %s' % url)

        request = urllib2.Request(url, headers=AREENA_NG_HTTP_HEADERS)
        try:
            urlreader = urllib2.urlopen(request)
            while True:
                buf = urlreader.read(4196)
                if not buf:
                    break
                sys.stdout.write(buf)

            sys.stdout.flush()
            urlreader.close()
        except urllib2.URLError as exc:
            log(u"Can't read %s: %s" % (url, exc))
            return RD_FAILED
        except ValueError:
            log(u'Invalid URL: ' + url)
            return RD_FAILED

        return RD_SUCCESS


### main program ###


def main():
    global debug
    global rtmpdump_binary
    global ffmpeg_binary
    global hds_binary
    global stream_proxy
    latest_episode = False
    url_only = False
    title_only = False
    print_episode_url = False
    audiolang = ''
    sublang = ''
    hardsubs = False
    bitratearg = sys.maxint
    ratelimit = None
    show_usage = False
    urls = []
    destdir = None
    pipe = False
    backends = [BackendFactory(DEFAULT_HDS_BACKENDS)]
    postprocess = None
    from_file = False

    # Is sys.getfilesystemencoding() the correct encoding for
    # sys.argv?
    encoding = sys.getfilesystemencoding()
    argv = [unicode(x, encoding, 'ignore') for x in sys.argv[1:]]
    rtmpdumpargs = []
    while argv:
        arg = argv.pop(0)
        if not arg.startswith('-'):
            urls = [encode_url_utf8(arg)]
        elif arg == '-i':
            if argv:
                from_file = True
                urls = read_urls_from_file(argv.pop(0))
        elif arg in ['--verbose', '-V', '--debug', '-z']:
            debug = True
            rtmpdumpargs.append(arg)
        elif arg in ['--help', '-h']:
            show_usage = True
        elif arg in ['--latestepisode']:
            latest_episode = True
        elif arg == '--showurl':
            url_only = True
        elif arg == '--showtitle':
            title_only = True
        elif arg == '--showepisodepage':
            url_only = True
            print_episode_url = True
        elif arg == '--vfat':
            global excludechars
            global excludechars_windows
            excludechars = excludechars_windows
        elif arg == '--audiolang':
            if argv:
                audiolang = argv.pop(0)
        elif arg == '--sublang':
            if argv:
                sublang = argv.pop(0)
        elif arg == '--hardsubs':
            hardsubs = True
        elif arg == '--maxbitrate':
            if argv:
                bitratearg = argv.pop(0)
        elif arg == '--ratelimit':
            if argv:
                ratelimit = int_or_else(argv.pop(0), None)
        elif arg == '--rtmpdump':
            if argv:
                rtmpdump_binary = argv.pop(0)
        elif arg == '--adobehds':
            if argv:
                hds_binary = argv.pop(0).split(' ')
        elif arg == '--ffmpeg':
            if argv:
                ffmpeg_binary = argv.pop(0)
        elif arg == '--destdir':
            if argv:
                destdir = argv.pop(0)
        elif arg == '--backend':
            if argv:
                backends = BackendFactory.parse_backends(
                    argv.pop(0).split(','))
        elif arg == '--pipe':
            pipe = True
        elif arg == '-o':
            if argv:
                outputfile = argv.pop(0)
                rtmpdumpargs.extend([arg, outputfile])
                if outputfile == '-':
                    pipe = True
        elif arg == '--proxy':
            if argv:
                stream_proxy = argv.pop(0)
        elif arg == '--postprocess':
            if argv:
                postprocess = argv.pop(0)
        else:
            rtmpdumpargs.append(arg)
            if arg in ARGOPTS and argv:
                rtmpdumpargs.append(argv.pop(0))

    if not rtmpdump_binary:
        if sys.platform == 'win32':
            rtmpdump_binary = which('rtmpdump.exe')
        else:
            rtmpdump_binary = which('rtmpdump')
    if not rtmpdump_binary:
        rtmpdump_binary = 'rtmpdump'

    if show_usage or len(urls) == 0:
        usage()
        sys.exit(RD_SUCCESS)

    if len(backends) == 0:
        sys.exit(RD_FAILED)

    if debug or not (url_only or title_only):
        splashscreen()

    if sublang == '':
        sublang = 'none' if pipe else 'all'

    maxbitrate = bitrate_from_arg(bitratearg)
    stream_filters = StreamFilters(latest_episode, audiolang, sublang,
                                   hardsubs, maxbitrate, ratelimit)
    exit_status = RD_SUCCESS

    for url in urls:
        res = process_url(url, destdir, url_only, title_only, from_file,
                          print_episode_url, pipe, rtmpdumpargs,
                          stream_filters, backends, postprocess)

        if exit_status == RD_SUCCESS:
            exit_status = res

    return exit_status


if __name__ == '__main__':
    sys.exit(main())
