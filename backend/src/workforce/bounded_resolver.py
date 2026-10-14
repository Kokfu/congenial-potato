"""Deadline for OS resolution in the isolated read experiment, not product egress.

getaddrinfo has no Python deadline. A short-lived trusted interpreter permits
killing and reaping a stalled lookup instead of leaking a blocked resolver thread.
"""
import json
import socket
import subprocess
import sys
import time

from .local_read_experiment import ReadDenied

_WATCHDOG_PROGRAM = '''
import signal, sys
signal.signal(signal.SIGALRM, signal.SIG_DFL)
signal.setitimer(signal.ITIMER_REAL, float(sys.argv[3]))
'''

_RESOLVE_PROGRAM = '''
import json, socket, sys
try:
    answers = socket.getaddrinfo(sys.argv[1], int(sys.argv[2]), type=socket.SOCK_STREAM)
    if not 1 <= len(answers) <= 64:
        sys.exit(2)
    payload = json.dumps(answers)
    if len(payload) > 65536:
        sys.exit(2)
    print(payload)
except (OSError, ValueError):
    sys.exit(2)
'''


def resolve_with_deadline(host: str, port: int, *, type=socket.SOCK_STREAM,
                          timeout_seconds: float = 3) -> list[tuple]:
    if (type != socket.SOCK_STREAM or not 0 < timeout_seconds <= 5 or
            not isinstance(host, str) or not 1 <= len(host) <= 253 or
            not host.isascii() or not 1 <= port <= 65535):
        raise ReadDenied('DNS resolver input unavailable')
    deadline = time.monotonic() + timeout_seconds
    try:
        process = subprocess.Popen(
            [sys.executable, '-I', '-c', _WATCHDOG_PROGRAM + _RESOLVE_PROGRAM,
             host, str(port), str(timeout_seconds)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, close_fds=True)
    except OSError as exc:
        raise ReadDenied('DNS resolver unavailable') from exc
    try:
        output, _ = process.communicate(timeout=max(0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.communicate()  # reap the killed interpreter, including its pipes
        raise ReadDenied('DNS resolver deadline exceeded') from exc
    except BaseException:
        process.kill()
        process.communicate()
        raise
    if process.returncode != 0 or time.monotonic() >= deadline or len(output) > 65536:
        raise ReadDenied('DNS resolution failed or exceeded deadline')
    try:
        answers = json.loads(output)
        if not isinstance(answers, list) or not 1 <= len(answers) <= 64:
            raise ValueError('answer count')
        rows = []
        for row in answers:
            if (not isinstance(row, list) or len(row) != 5 or
                    row[0] not in (socket.AF_INET, socket.AF_INET6) or
                    row[1] != socket.SOCK_STREAM or
                    not isinstance(row[4], list) or len(row[4]) not in (2, 4) or
                    row[4][1] != port):
                raise ValueError('answer shape')
            rows.append((*row[:4], tuple(row[4])))
        return rows
    except (ValueError, TypeError, IndexError) as exc:
        raise ReadDenied('DNS resolver response unavailable') from exc
