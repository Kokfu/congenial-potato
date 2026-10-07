from .config import get_settings
from .db import session_factory
from .security import bootstrap_owner


def main() -> None:
    with session_factory()() as db:
        bootstrap_owner(db, get_settings().initial_admin_password_file)


if __name__ == '__main__':
    main()
