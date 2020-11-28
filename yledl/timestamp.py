# -*- coding: utf-8 -*-

import logging
import re
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
    parsed = parse_areena_timestamp_py3(timestamp)
    if parsed is None:
        logger.warning('Failed to parse timestamp: {}'.format(timestamp))

    return parsed


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
