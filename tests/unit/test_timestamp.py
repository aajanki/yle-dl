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

from datetime import datetime, timedelta
from yledl.timestamp import parse_areena_timestamp


def test_timestamp():
    ts = parse_areena_timestamp('2018-01-02T18:30:00+02:00')

    assert ts.replace(tzinfo=None) == datetime(2018, 1, 2, 18, 30, 00)
    assert ts.utcoffset() == timedelta(hours=2)

    
def test_timestamp_strip():
    ts = parse_areena_timestamp('  2018-01-02T18:30:00+02:00  ')
    assert ts.replace(tzinfo=None) == datetime(2018, 1, 2, 18, 30, 00)

def test_invalid_timestamp():
    assert parse_areena_timestamp('xxx2018-01-02T18:30:00+02:00') is None
    assert parse_areena_timestamp('2018-01-02T18:30:00') is None
    assert parse_areena_timestamp('2018-01-999999T18:30:00+02:00') is None
    assert parse_areena_timestamp('2018-01-999999T22222') is None
