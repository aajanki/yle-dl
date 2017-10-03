# -*- coding: utf-8 -*-

import sys


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
