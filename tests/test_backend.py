from yledl import IOContext, RD_SUCCESS
from yledl.backends import HLSBackend, WgetBackend


tv1_url = 'https://yletv-lh.akamaihd.net/i/yletv1hls_1@103188/master.m3u8'
io = IOContext(destdir='/tmp/')


class MockHLSBackend(HLSBackend):
    def __init__(self, url, long_probe=False, program_id=None, is_live=False):
        super().__init__(url, long_probe, program_id, is_live)

        self.executed_commands = None

    def external_downloader(self, commands, env=None):
        self.executed_commands = commands
        return RD_SUCCESS

    def full_stream_already_downloaded(self, filename, clip, io):
        return False


class MockWgetBackend(WgetBackend):
    def __init__(self, url, file_extension):
        super().__init__(url, file_extension)

        self.executed_commands = None

    def external_downloader(self, commands, env=None):
        self.executed_commands = commands
        return RD_SUCCESS

    def full_stream_already_downloaded(self, filename, clip, io):
        return False


def test_hls_backend_save_stream():
    backend = MockHLSBackend(tv1_url, program_id=0)

    res = backend.save_stream('test.mkv', clip=None, io=io)

    assert res == RD_SUCCESS
    assert len(backend.executed_commands) == 1
    assert tv1_url in backend.executed_commands[0]


def test_hls_backend_pipe():
    backend = MockHLSBackend(tv1_url, program_id=0)

    res = backend.pipe(io)

    assert res == RD_SUCCESS
    assert len(backend.executed_commands) == 1
    assert tv1_url in backend.executed_commands[0]


def test_wget_backend_save_stream():
    backend = MockWgetBackend(tv1_url, file_extension='.mkv')

    res = backend.save_stream('test.mkv', clip=None, io=io)

    assert res == RD_SUCCESS
    assert len(backend.executed_commands) == 1
    assert tv1_url in backend.executed_commands[0]


def test_wget_backend_pipe():
    backend = MockWgetBackend(tv1_url, file_extension='.mkv')

    res = backend.pipe(io)

    assert res == RD_SUCCESS
    assert len(backend.executed_commands) == 1
    assert tv1_url in backend.executed_commands[0]
