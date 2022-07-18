class FfmpegNotFoundError(Exception):
    pass


class ExternalApplicationNotFoundError(Exception):
    """Downloader backend failed because of a missing external program"""
    pass


class TransientDownloadError(Exception):
    """Download process was interrupted by a potentially transient error.

    Raised on I/O errors and on similar errors where retrying might fix the
    situation.
    """
    def __init__(self, message):
        self.message = message
