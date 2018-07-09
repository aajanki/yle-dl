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
cached_requests_session = None

def yledl_headers():
    headers = requests.utils.default_headers()
    headers.update({'User-Agent': yledl_user_agent()})
    return headers


def yledl_user_agent():
    return 'yle-dl/' + version.split(' ')[0]


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
        cached_requests_session = _create_session()

    try:
        r = cached_requests_session.get(url, headers=headers, timeout=20)
        r.raise_for_status()
    except requests.exceptions.RequestException:
        logger.exception("Can't read {}".format(url))
        return None

    return r


def download_to_file(url, destination_filename):
    enc = sys.getfilesystemencoding()
    encoded_filename = destination_filename.encode(enc, 'replace')
    with open(encoded_filename, 'wb') as output:
        r = requests.get(url, headers=yledl_headers(), stream=True, timeout=20)
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=4096):
            output.write(chunk)


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


def _create_session():
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
