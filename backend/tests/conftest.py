import os
import tempfile
from pathlib import Path

_TEST_DIR = tempfile.TemporaryDirectory(prefix="research-manager-test-")
os.environ.update({
    "DATABASE_URL": "sqlite:///" + (Path(_TEST_DIR.name) / "test.db").as_posix(),
    "SECRET_KEY": "test-only-secret-key-not-for-deployment-2026",
    "PROJECT_NAME": "Research Manager Test",
    "FIRST_SUPERUSER": "admin@example.com",
    "FIRST_SUPERUSER_PASSWORD": "Test-only-password-2026",
    "ENABLE_SIGNUP": "true",
    "EMAILS_FROM_EMAIL": "noreply@example.com",
    "FASTAPI_ENV": "development",
})

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.core.config import settings
from app.core.db import engine, init_db
from app.main import app
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session]:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        init_db(session)
        yield session
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )


@pytest.fixture(autouse=True)
def no_external_email(monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setattr("app.utils.emails.Message.send", Mock())
