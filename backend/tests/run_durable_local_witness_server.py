"""Run the local-only Unix-socket witness fixture from a mode-0600 config."""
import sys

from durable_local_witness_transport import serve_config


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: run_durable_local_witness_server.py PRIVATE_CONFIG')
    serve_config(sys.argv[1])
