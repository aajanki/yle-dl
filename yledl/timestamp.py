# This file is part of yle-dl.
#
# Copyright 2010-2022 Antti Ajanki and others
#
# Yle-dl is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Yle-dl is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with yle-dl. If not, see <https://www.gnu.org/licenses/>.

import logging
import re
from datetime import datetime


logger = logging.getLogger('yledl')


def parse_areena_timestamp(timestamp):
    if timestamp is None:
        return None

    timestamp = timestamp.strip()
    parsed = parse_areena_timestamp_py3(timestamp)
    if parsed is None:
        logger.warning(f'Failed to parse timestamp: {timestamp}')

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


def format_finnish_short_weekday_and_date(d):
    """Format a datetime object as Finnish weekday and date ("pe 9.9.2022")."""
    short_weekday_names = {
        '1': 'ma',
        '2': 'ti',
        '3': 'ke',
        '4': 'to',
        '5': 'pe',
        '6': 'la',
        '7': 'su',
    }

    weekday_name = short_weekday_names[d.strftime('%u')]
    short_date = f'{d.strftime("%d").lstrip("0")}.{d.strftime("%m").lstrip("0")}.{d.strftime("%Y")}'
    return f'{weekday_name} {short_date}'
