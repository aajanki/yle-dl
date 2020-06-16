# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import, unicode_literals
import logging
import re
import sys
from datetime import datetime, timedelta, tzinfo


logger = logging.getLogger('yledl')


class FixedOffset(tzinfo):
    def __init__(self, offset_hours):
        self.__offset = timedelta(hours=offset_hours)

    def utcoffset(self, dt):
        return self.__offset

    def tzname(self, dt):
        return 'FixedOffset'

    def dst(self, dt):
        return timedelta(0)


def parse_areena_timestamp(timestamp):
    if timestamp is None:
        return None

    timestamp = timestamp.strip()
    if sys.version_info.major >= 3:
        parsed = parse_areena_timestamp_py3(timestamp)
    else:
        parsed = parse_areena_timestamp_py2(timestamp)

    if parsed is None:
        logger.warning('Failed to parse timestamp: {}'.format(timestamp))

    return parsed


def parse_areena_timestamp_py2(timestamp):
    # The %z timezone parsing is not supported by strptime in Python
    # 2.7. Perform a naive timezone parsing manually instead.
    dt = None
    m = re.search(r'\+(\d\d):00$', timestamp)
    if m:
        offset_hours = int(m.group(1))
        dt = (strptime_or_none(timestamp[:-6], '%Y-%m-%dT%H:%M:%S.%f') or
              strptime_or_none(timestamp[:-6], '%Y-%m-%dT%H:%M:%S'))
        if dt is not None:
            dt = dt.replace(tzinfo=FixedOffset(offset_hours))

    return dt


def parse_areena_timestamp_py3(timestamp):
    # Python prior to 3.7 doesn't support a colon in the timezone
    if re.search(r'\d\d:\d\d$', timestamp):
        timestamp = timestamp[:-3] + timestamp[-2:]

    return (strptime_or_none(timestamp, '%Y-%m-%dT%H:%M:%S.%f%z') or
            strptime_or_none(timestamp, '%Y-%m-%dT%H:%M:%S%z'))


def strptime_or_none(timestamp, format):
    try:
        return datetime.strptime(timestamp, format)
    except ValueError:
        return None
