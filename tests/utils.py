from __future__ import print_function, absolute_import, unicode_literals
import sys
import json
from io import BytesIO
from yledl import download, StreamFilters, IOContext, \
    DownloadLimits, StreamAction, RD_SUCCESS


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


def fetch_title(url):
    return fetch(url, StreamAction.PRINT_STREAM_TITLE)


def fetch_stream_url(url):
    return fetch(url, StreamAction.PRINT_STREAM_URL)


def fetch_episode_pages(url):
    return fetch(url, StreamAction.PRINT_EPISODE_PAGES)


def fetch_metadata(url):
    return json.loads('\n'.join(fetch(url, StreamAction.PRINT_METADATA)))


def fetch(url, action):
    basic_filters = StreamFilters()
    # Initialize rtmpdump_binary to avoid a file system lookup in tests
    io = IOContext(destdir='/tmp/', rtmpdump_binary='rtmpdump')

    with Capturing() as output:
        res = download(url,
                       action,
                       io,
                       stream_filters = basic_filters,
                       postprocess_command = None)
        assert res == RD_SUCCESS

    return output
