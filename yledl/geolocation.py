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

import json
import logging
import requests


logger = logging.getLogger('yledl')


class AreenaGeoLocation:
    def __init__(self, httpclient):
        self.httpclient = httpclient

    def located_in_finland(self, referrer):
        endpoint = 'https://locations.api.yle.fi/v1/address/current?'\
            'app_id=player_static_prod&'\
            'app_key=8930d72170e48303cf5f3867780d549b'
        extra_headers = {
            'Referer': referrer,
            'TE': 'Trailers',
        }
        try:
            r = self.httpclient.get(endpoint, extra_headers)
        except requests.RequestException:
            logger.warning('Failed to check geo restrictions.')
            logger.warning('Continuing as if no restrictions apply. '
                           'This may fail later.')
            return True

        response = r.json()
        logger.debug('Geo query response:')
        logger.debug(json.dumps(response))

        return response.get('country_code') == 'FI'
