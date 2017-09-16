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
        "height": 360
      }
    ],
    "publish_timestamp": "2017-09-13T19:52:03+03:00",
    "duration_seconds": 356,
    "title": "Eurooppalainen keksint\u00f6palkinto 2016: S01E10: Eurooppalainen keksint\u00f6palkinto 2016-2017-09-13T19:52:03+03:00",
    "webpage": "https://areena.yle.fi/1-3813200",
    "region": "Finland",
    "expiration_timestamp": "2017-10-14T23:59:59+03:00",
    "subtitles": [
      {
        "lang": "fin",
        "uri": "https://cdnsecakmi.kaltura.com/api_v3/index.php/service/caption_captionAsset/action/serve/captionAssetId/1_yg254xmo/ks/djJ8MTk1NTAzMXzFSuyeX4lunGYUIWvmbdrsZxOQRoWt4CjPim5GMRtOymPyz5pM7vEMY4dMxQd1qf8IncPdAbcwG9uYRAq2zej75Cys7V_RSYopa5tc7NvwtqCJ7Y8rEtkYLIovXRN-5YSlGLelw1nTEmPYjSEMWrZruY5EbNzd6Jn9Riywmt3E_Sw-M3ba00yDMttJ6xb0rjeG55ZsSU5GNmhll6kdSc5T"
      }
    ]
  }
]
```

The following fields may be present in the metadata. Any of the fields may be missing if it can't be extracted or if it doesn't apply to the stream.
* `webpage`: The address of the webpage where the stream can be viewed.
* `title`: The title of the stream.
* `flavors`: A list of available bitrates and resolutions. Each flavor is described by the following keys:
  * `bitrate`: The bitrate (kilobits per second) of the flavor.
  * `width`: The horizontal resoluation in pixels.
  * `height`: The vertical resolution in pixels.
  * `media_type`: Either "video" or "audio".
* `subtitles`: A list of available subtitles. Each subtitle is described by the following keys:
  * `lang`: The subtitle language code.
  * `uri`: The URI of the subtitle.
* `duration_seconds`: The length of the stream in seconds.
* `region`: Is the stream available outside Finland? If "World", then yes. If "Finland", the stream can be accessed only in Finland.
* `publish_timestamp`: The instant when the stream was published in the web. May be in the future, if the stream is not yet available.
* `expiration_timestamp`: The instant when the stream will expire. May be in the past, if the stream has already expired.
