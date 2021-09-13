import json

def load_json(url, httpclient, headers=None):
    """Download and parse a JSON document at a given URL."""
    json_string = httpclient.download_page(url, headers)
    if not json_string:
        return None

    try:
        json_parsed = json.loads(json_string)
    except ValueError:
        return None

    return json_parsed
