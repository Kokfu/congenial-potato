from functools import lru_cache
from pathlib import Path
from decimal import Decimal
from urllib.parse import quote
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_database_url: str | None = None
    dbos_system_database_url: str | None = None
    db_host: str = 'db'
    db_user: str = 'postgres'
    db_password_file: Path | None = None
    app_db_name: str = 'workforce'
    dbos_db_name: str = 'workforce_dbos'
    initial_admin_password_file: Path = Path('/run/secrets/initial_admin_password')
    session_cookie_secure: bool = True
    allowed_origin: str = 'http://localhost:8080'
    session_hours: int = 24
    artifact_dir: Path = Path('/var/lib/workforce/artifacts')
    daily_cap_usd: Decimal | None = None
    model_call_timeout_seconds: int = Field(default=20, gt=0, le=120)

    def database_url(self, name: str) -> str:
        if not self.db_password_file:
            raise ValueError('DB_PASSWORD_FILE is required when a database URL is not provided')
        password = quote(self.db_password_file.read_text().rstrip('\n'), safe='')
        return f'postgresql+psycopg://{self.db_user}:{password}@{self.db_host}:5432/{name}'

    @property
    def app_url(self) -> str:
        return self.app_database_url or self.database_url(self.app_db_name)

    @property
    def workflow_url(self) -> str:
        return self.dbos_system_database_url or self.database_url(self.dbos_db_name)


@lru_cache
def get_settings() -> Settings:
    return Settings()
