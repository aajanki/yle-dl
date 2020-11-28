# -*- coding: utf-8 -*-

import json
import logging
import requests


logger = logging.getLogger('yledl')


class AreenaGeoLocation(object):
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
