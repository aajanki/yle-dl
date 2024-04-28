# This file is part of yle-dl.
#
# Copyright 2010-2024 Antti Ajanki and others
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

import json
import logging
import requests


logger = logging.getLogger('yledl')


class AreenaGeoLocation:
    def __init__(self, httpclient):
        self.httpclient = httpclient

    def located_in_finland(self, referrer):
        endpoint = 'https://locations.api.yle.fi/v3/address/current?' \
            'app_id=areena-web-items&' \
            'app_key=wlTs5D9OjIdeS9krPzRQR4I1PYVzoazN'
        extra_headers = { 'Referer': referrer }
        try:
            r = self.httpclient.get(endpoint, extra_headers)
        except requests.RequestException:
            logger.warning('Failed to check geo restrictions.')
            logger.warning('Assuming that no restrictions apply. This may fail later.')
            return True

        response = r.json()
        logger.debug('Geo query response:')
        logger.debug(json.dumps(response))

        return response.get('country_code') == 'FI'
