"""Copy Compose file secrets into private tmpfs, then drop root before app code."""
import os
import sys
from pathlib import Path

UID = 10001
GID = 10001


def main() -> None:
    if os.geteuid() != 0:
        raise RuntimeError('Entrypoint must start as root to read mounted secrets')
    target = Path('/tmp/workforce-secrets')
    target.mkdir(mode=0o700, exist_ok=True)
    os.chown(target, UID, GID)
    for key in ('DB_PASSWORD_FILE', 'INITIAL_ADMIN_PASSWORD_FILE'):
        source = Path(os.environ[key])
        destination = target / source.name
        destination.write_bytes(source.read_bytes())
        os.chown(destination, UID, GID)
        destination.chmod(0o400)
        os.environ[key] = str(destination)
    os.setgroups([])
    os.setgid(GID)
    os.setuid(UID)
    if not sys.argv[1:]:
        raise ValueError('No application command supplied')
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == '__main__':
    main()
