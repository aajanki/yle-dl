Stream metadata
---------------

The `yle-dl --showmetadata` option will print title, available bitrates and other metadata about a stream. The output is a JSON list consisting of a metadata object for each stream that was detected on the input page.

Example output:
```json
[
  {
    "flavors": [
      {
        "media_type": "video",
        "bitrate": 464,
        "width": 640,
        "height": 360,
        "backends": [
          "ffmpeg",
          "wget"
        ]
      }
    ],
    "publish_timestamp": "2017-09-13T19:52:03+03:00",
    "duration_seconds": 356,
    "title": "Eurooppalainen keksint\u00f6palkinto 2016: S01E10-2017-09-13T19:52:03+03:00",
    "filename": "/video/Eurooppalainen keksint\u00f6palkinto 2016: S01E10-2017-09-13T19:52:03+03:00.mp4",
    "webpage": "https://areena.yle.fi/1-3813200",
    "region": "Finland",
    "expiration_timestamp": "2017-10-14T23:59:59+03:00",
    "embedded_subtitles": [
      {
        "language": "fin",
        "category": "k\u00e4\u00e4nn\u00f6stekstitys"
      }
    ]
  }
]
```

The following fields may be present in the metadata. Any of the fields may be missing if it can't be extracted or if it doesn't apply to the stream.
* `webpage`: The address of the webpage where the stream can be viewed.
* `title`: The title of the stream.
* `filename`: The proposed name of the output file when it it not overridden by the -o option
* `flavors`: A list of available bitrates and resolutions. Each flavor is described by the following keys:
  * `bitrate`: The bitrate (kilobits per second) of the flavor.
  * `width`: The horizontal resoluation in pixels.
  * `height`: The vertical resolution in pixels.
  * `media_type`: Either "video" or "audio".
  * `backends`: A list of downloader backends which can download this stream (--backend option)
* `embedded_subtitles`: A list of subtitles embedded on the video file. Each subtitle is described by the following keys:
  * `language`: Three-letter language code
  * `category`: "käännöstekstitys" or "ohjelmatekstitys"
* `duration_seconds`: The length of the stream in seconds.
* `region`: Is the stream available outside Finland? If "World", then yes. If "Finland", the stream can be accessed only in Finland.
* `publish_timestamp`: The instant when the stream was published in the web. May be in the future, if the stream is not yet available.
* `expiration_timestamp`: The instant when the stream will expire. May be in the past, if the stream has already expired.
