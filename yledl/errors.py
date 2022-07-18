class FfmpegNotFoundError(Exception):
    pass


class ExternalApplicationNotFoundError(Exception):
    pass


class TransientDownloadError(Exception):
    def __init__(self, filename):
        self.filename = filename
