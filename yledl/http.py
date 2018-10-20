# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import logging
import lxml.html
import lxml.etree
import re
import requests
import sys
from requests.adapters import HTTPAdapter
from .version import version

logger = logging.getLogger('yledl')


class HttpClient(object):
    def __init__(self, proxy=None):
        self._session = self._create_session(proxy)

    def _create_session(self, proxy):
        session = requests.Session()
        session.timeout=20

        if proxy:
            session.proxies = {
                'http': proxy,
                'https': proxy
            }

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

    def download_page(self, url, extra_headers=None):
        """Returns contents of a URL."""
        response = self.get(url, extra_headers)
        return response.text if response else None

    def download_html_tree(self, url, extra_headers=None):
        """Downloads a HTML document and returns it parsed as an lxml tree."""
        response = self.get(url, extra_headers)
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

    def download_to_file(self, url, destination_filename):
        enc = sys.getfilesystemencoding()
        encoded_filename = destination_filename.encode(enc, 'replace')
        with open(encoded_filename, 'wb') as output:
            r = requests.get(url, headers=yledl_headers(), stream=True, timeout=20)
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=4096):
                output.write(chunk)

    def get(self, url, extra_headers=None):
        if url.find('://') == -1:
            url = 'http://' + url
        if '#' in url:
            url = url[:url.find('#')]

        headers = yledl_headers()
        if extra_headers:
            headers.update(extra_headers)

        try:
            r = self._session.get(url, headers=headers)
            r.raise_for_status()
        except requests.exceptions.RequestException:
            logger.exception("Can't read {}".format(url))
            return None

        return r


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


def html_unescape(escaped_html):
    s = escaped_html.replace("&lt;", "<")
    s = s.replace("&gt;", ">")
    s = s.replace("&quot;", '"')
    s = s.replace("&amp;", "&")
    return s
