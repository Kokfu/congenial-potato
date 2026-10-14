"""Socket-file wrapper: each underlying receive shares one absolute deadline.

Wrapping the raw file underneath BufferedReader bounds HTTP status/header lines
and body reads even when a peer trickles bytes faster than a per-read timeout.
The socket's own makefile manages descriptor references; no private stdlib fields
or replacement HTTP parser are required.
"""
import io
import time


def remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise TimeoutError('Read transport deadline exceeded')
    return value


class _DeadlineRawReader(io.RawIOBase):
    def __init__(self, raw, sock, deadline):
        self.raw = raw
        self.sock = sock
        self.deadline = deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        self.sock.settimeout(remaining(self.deadline))
        return self.raw.readinto(buffer)

    def close(self):
        try:
            self.raw.close()
        finally:
            super().close()


class DeadlineSocket:
    def __init__(self, sock, deadline: float):
        self.socket = sock
        self.deadline = deadline

    def __getattr__(self, name):
        return getattr(self.socket, name)

    def sendall(self, data, *args):
        self.socket.settimeout(remaining(self.deadline))
        return self.socket.sendall(data, *args)

    def makefile(self, mode):
        if mode != 'rb':
            raise ValueError('Read transport accepts binary response files only')
        raw = self.socket.makefile(mode, buffering=0)
        return io.BufferedReader(_DeadlineRawReader(raw, self.socket, self.deadline))
