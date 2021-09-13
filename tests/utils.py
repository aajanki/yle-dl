import sys
import json
from datetime import timedelta, tzinfo
from io import BytesIO
from yledl import execute_action, StreamFilters, IOContext, StreamAction, RD_SUCCESS
from yledl.io import random_elisa_ipv4
from yledl.http import HttpClient
from yledl.titleformatter import TitleFormatter


# Context manager for capturing stdout output. See
# https://stackoverflow.com/questions/16571150/how-to-capture-stdout-output-from-a-python-function-call
class Capturing(list):
    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._bytesio = BytesIO()
        return self

    def __exit__(self, *args):
        self.extend(self._bytesio.getvalue().decode('UTF-8').splitlines())
        del self._bytesio    # free up some memory
        sys.stdout = self._stdout


class FixedOffset(tzinfo):
    def __init__(self, offset_hours):
        self.__offset = timedelta(hours=offset_hours)

    def utcoffset(self, dt):
        return self.__offset

    def tzname(self, dt):
        return 'FixedOffset'

    def dst(self, dt):
        return timedelta(0)


def fetch_title(url, filters=StreamFilters()):
    return fetch(url, StreamAction.PRINT_STREAM_TITLE, filters)


def fetch_stream_url(url, filters=StreamFilters()):
    return fetch(url, StreamAction.PRINT_STREAM_URL, filters)


def fetch_episode_pages(url, filters=StreamFilters()):
    return fetch(url, StreamAction.PRINT_EPISODE_PAGES, filters)


def fetch_metadata(url, filters=StreamFilters(), meta_language=None):
    return json.loads('\n'.join(
        fetch(url, StreamAction.PRINT_METADATA, filters, meta_language)))


def fetch(url, action, filters, meta_language=None):
    io = IOContext(destdir='/tmp/', metadata_language=meta_language,
                   x_forwarded_for=random_elisa_ipv4())
    httpclient = HttpClient(io)
    title_formatter = TitleFormatter()

    with Capturing() as output:
        res = execute_action(url,
                             action,
                             io,
                             httpclient,
                             title_formatter,
                             stream_filters = filters)
        assert res == RD_SUCCESS

    return output
