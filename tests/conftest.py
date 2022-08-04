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

import pytest


def pytest_addoption(parser):
    parser.addoption('--geoblocked', action='store_true',
                     help='Enable get-blocked tests that work only in Finland')


def pytest_configure(config):
    config.addinivalue_line("markers", "geoblocked: get-blocked test that work only in Finland")


def pytest_collection_modifyitems(config, items):
    if not config.option.geoblocked:
        # Skip tests marked as geoblocked
        skip_geoblocked = pytest.mark.skip(reason="need --geoblocked option to run")
        for item in items:
            if "geoblocked" in item.keywords:
                item.add_marker(skip_geoblocked)
