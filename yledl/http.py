# -*- coding: utf-8 -*-

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
    def __init__(self, io):
        self._session = self._create_session(io.proxy)
        self.x_forwarded_for = io.x_forwarded_for

    def _create_session(self, proxy):
        session = requests.Session()
        session.timeout = 20

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
            logger.warning('Requests library is too old. Retrying not supported.')

        return session

    def download_page(self, url, extra_headers=None):
        """Returns contents of a URL."""
        response = self.get(url, extra_headers)
        return response.text if response else None

    def download_html_tree(self, url, extra_headers=None):
        """Downloads a HTML document and returns it parsed as an lxml tree."""
        response = self.get(url, extra_headers)
        metacharset = html_meta_charset(response.content)
        if metacharset:
            logger.debug('HTML meta charset: {}'.format(metacharset))
            response.encoding = metacharset

        try:
            page = response.text
            return lxml.html.fromstring(page)
        except lxml.etree.XMLSyntaxError as ex:
            logger.warning('HTML syntax error: {}'.format(str(ex)))
            return None
        except lxml.etree.ParserError as ex:
            logger.warning('HTML parsing error: {}'.format(str(ex)))
            return None

    def download_to_file(self, url, destination_filename):
        enc = sys.getfilesystemencoding()
        encoded_filename = destination_filename.encode(enc, 'replace')
        logger.debug('HTTP GET {}'.format(url))
        with open(encoded_filename, 'wb') as output:
            r = requests.get(url, headers=self.yledl_headers(), stream=True, timeout=20)
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=4096):
                output.write(chunk)

    def get(self, url, extra_headers=None):
        if url.find('://') == -1:
            url = 'http://' + url
        if '#' in url:
            url = url[:url.find('#')]

        headers = self.yledl_headers()
        if extra_headers:
            headers.update(extra_headers)

        logger.debug('HTTP GET {}'.format(url))
        r = self._session.get(url, headers=headers)
        logger.debug('HTTP status code: {}'.format(r.status_code))
        logger.debug('HTTP response headers:')
        for name, value in r.headers.items():
            logger.debug('{}: {}'.format(name, value))
        r.raise_for_status()

        return r

    def post(self, url, json_data, extra_headers=None):
        headers = self.yledl_headers()
        if extra_headers:
            headers.update(extra_headers)

        logger.debug('HTTP POST {}'.format(url))
        r = self._session.post(url, json=json_data, headers=headers)
        logger.debug('HTTP status code: {}'.format(r.status_code))
        logger.debug('HTTP response headers:')
        for name, value in r.headers.items():
            logger.debug('{}: {}'.format(name, value))
        r.raise_for_status()

        return r

    def yledl_headers(self):
        headers = requests.utils.default_headers()
        headers.update({'User-Agent': yledl_user_agent()})
        if self.x_forwarded_for:
            headers.update({'X-Forwarded-For': self.x_forwarded_for})
        return headers


def yledl_user_agent():
    return 'yle-dl/' + version.split(' ')[0]


def html_meta_charset(html_bytes):
    metacharset = re.search(br'<meta [^>]*?charset="(.*?)"', html_bytes)
    if metacharset:
        return metacharset.group(1).decode('ASCII')
    else:
        return None
