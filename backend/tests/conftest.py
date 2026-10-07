import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

assert 'workforce_test' in os.environ.get('APP_DATABASE_URL', ''), 'Tests require disposable workforce_test database'
os.environ['SESSION_COOKIE_SECURE'] = 'false'
os.environ['ALLOWED_ORIGIN'] = 'http://localhost:8080'
from workforce.config import get_settings  # noqa: E402
from workforce.db import Base, engine, session_factory  # noqa: E402
from workforce import models  # noqa: E402,F401
from workforce.main import app  # noqa: E402
from workforce.security import bootstrap_owner  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database(tmp_path: Path, monkeypatch):
    with engine().begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    secret = tmp_path / 'password'
    secret.write_text('synthetic-strong-password-123\n')
    monkeypatch.setenv('INITIAL_ADMIN_PASSWORD_FILE', str(secret))
    get_settings.cache_clear()
    with session_factory()() as db:
        bootstrap_owner(db, secret)
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    with TestClient(app, base_url='http://localhost:8080') as c:
        yield c


@pytest.fixture
def authenticated(client):
    response = client.post('/api/auth/login', json={'password': 'synthetic-strong-password-123'}, headers={'Origin': 'http://localhost:8080'})
    assert response.status_code == 200, response.text
    return client
