from __future__ import print_function, absolute_import, unicode_literals
import sys


def print_enc(msg, out=None, linefeed_and_flush=True):
    if out is None:
        out = sys.stdout

    if hasattr(out, 'buffer'):
        bytes_out = out.buffer
    else:
        bytes_out = out

    if hasattr(out, 'encoding'):
        enc = out.encoding or 'UTF-8'
    else:
        enc = 'UTF-8'

    bytes_out.write(bytes(msg.encode(enc, 'ignore')))
    if linefeed_and_flush:
        bytes_out.write(b'\n')
        bytes_out.flush()


def sane_filename(name, excludechars):
    tr = dict((ord(c), ord('_')) for c in excludechars)
    x = name.strip(' .').translate(tr)
    return x or 'ylevideo'
