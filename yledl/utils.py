# -*- coding: utf-8 -*-

import sys
from contextlib import contextmanager
from progress import Infinite
from progress.bar import Bar


def print_enc(msg, out=None, linefeed_and_flush=True):
    if out is None:
        out = sys.stdout

    if hasattr(out, 'encoding'):
        enc = out.encoding or 'UTF-8'
    else:
        enc = 'UTF-8'

    out.write(msg.encode(enc, 'backslashreplace'))
    if linefeed_and_flush:
        out.write('\n')
        out.flush()


class DownloadProgressBar(Bar):
    message = 'Downloading'
    suffix = '%(percent).1f%%'


class DisabledProgressBar(Infinite):
    pass


@contextmanager
def progress_bar(enabled, response_headers):
    try:
        total_length = int(response_headers.get('content-length'))
    except ValueError:
        total_length = 0

    if enabled and total_length:
        progress = DownloadProgressBar(max=total_length)
    else:
        progress = DisabledProgressBar()

    try:
        yield progress
    finally:
        progress.finish()
