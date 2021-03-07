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


def parse_json_object(text, start_pos):
    """Extract a JSON document from a text string starting at start_pos."""
    return json.JSONDecoder().raw_decode(text[start_pos:])[0]
