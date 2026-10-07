"""Initialize or migrate the DBOS system database before workers start."""
from dbos import run_dbos_database_migrations
from .config import get_settings


def main() -> None:
    run_dbos_database_migrations(get_settings().workflow_url)


if __name__ == '__main__':
    main()
