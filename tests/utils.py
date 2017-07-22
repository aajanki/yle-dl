import sys
from cStringIO import StringIO
from yledl.yledl import process_url, StreamFilters, BackendFactory, RD_SUCCESS

backends = [BackendFactory(BackendFactory.ADOBEHDSPHP)]
basic_filters = StreamFilters(
    latest_only=False,
    audiolang='',
    sublang='all',
    hardsubs=False,
    maxbitrate=0,
    ratelimit=None,
    duration=None)


# Context manager for capturing stdout output. See
# https://stackoverflow.com/questions/16571150/how-to-capture-stdout-output-from-a-python-function-call
class Capturing(list):
    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._stringio = StringIO()
        return self

    def __exit__(self, *args):
        self.extend(self._stringio.getvalue().splitlines())
        del self._stringio    # free up some memory
        sys.stdout = self._stdout


def fetch_title(url):
    return fetch_stream_title_or_url(url, True)


def fetch_stream_url(url):
    return fetch_stream_title_or_url(url, False)


def fetch_stream_title_or_url(url, get_title):
    with Capturing() as output:
        res = process_url(url,
                          destdir = '/tmp/',
                          url_only = not get_title,
                          title_only = get_title,
                          from_file = None,
                          print_episode_url = False,
                          pipe = False,
                          rtmpdumpargs = [],
                          stream_filters = basic_filters,
                          backends = backends,
                          postprocess_command = None)
        assert res == RD_SUCCESS

    return output
