"""Test configuration.

Two modes, selected by TEST_DATABASE_URL:

- unset        -> SQLite in a temporary file (the default local/dev workflow).
- postgres URL -> that PostgreSQL database, schema built by Alembic migrations
                  when TEST_SCHEMA_FROM_MIGRATIONS=1, otherwise by create_all.

Safety: a PostgreSQL test URL must look like a dedicated test database, and the
destructive fixtures never touch any other database. There is no silent
fallback: if a PostgreSQL URL is requested but unusable, collection fails.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "")
_SCHEMA_FROM_MIGRATIONS = os.environ.get("TEST_SCHEMA_FROM_MIGRATIONS") == "1"

if _TEST_DB_URL:
    os.environ["DATABASE_URL"] = _TEST_DB_URL
else:
    # mkdtemp (not TemporaryDirectory) so cleanup cannot raise at interpreter
    # shutdown on Windows while SQLite still holds the file handle.
    _TEST_DIR = tempfile.mkdtemp(prefix="research-manager-test-")
    atexit.register(shutil.rmtree, _TEST_DIR, True)
    os.environ.setdefault(
        "DATABASE_URL", "sqlite:///" + (Path(_TEST_DIR) / "test.db").as_posix()
    )

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-deployment-2026")
os.environ.setdefault("PROJECT_NAME", "Research Manager Test")
os.environ.setdefault("FIRST_SUPERUSER", "admin@example.com")
os.environ.setdefault("FIRST_SUPERUSER_PASSWORD", "Test-only-password-2026")
os.environ.setdefault("ENABLE_SIGNUP", "true")
os.environ.setdefault("EMAILS_FROM_EMAIL", "noreply@example.com")
os.environ.setdefault("FASTAPI_ENV", "development")

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel

from app.core.config import settings
from app.core.db import create_engine_for
from app.main import app
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers

DATABASE_URL = str(settings.DATABASE_URL)


def _require_test_database(url: str) -> None:
    """Refuse to run destructive fixtures against anything but a test DB."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        return
    name = parsed.database or ""
    if not (name.endswith("_test") or name.startswith("test_") or name == "test"):
        raise RuntimeError(
            "Refusing to drop/recreate a PostgreSQL database that is not clearly "
            f"a test target (name={name!r}); use a name ending in '_test'."
        )


_require_test_database(DATABASE_URL)

engine = create_engine_for(DATABASE_URL)
IS_POSTGRESQL = engine.dialect.name == "postgresql"


def _print_dialect_evidence() -> None:
    """Secret-free proof of which dialect/DB the suite actually used."""
    parsed = make_url(DATABASE_URL)
    detail = parsed.host or "local-file"
    print(
        f"\n[test-db] dialect={engine.dialect.name} driver={engine.dialect.driver} "
        f"database={parsed.database!r} host={detail!r} "
        f"schema_from_migrations={_SCHEMA_FROM_MIGRATIONS}"
    )


def _build_schema() -> None:
    if _SCHEMA_FROM_MIGRATIONS and IS_POSTGRESQL:
        from alembic import command
        from alembic.config import Config

        backend_dir = Path(__file__).resolve().parents[1]
        config = Config(str(backend_dir / "alembic.ini"))
        # Absolute script_location: alembic.ini's "app/alembic" is relative to
        # the backend dir, which is not the test runner's cwd.
        config.set_main_option(
            "script_location", str(backend_dir / "app" / "alembic")
        )
        # Pass the URL out-of-band: ConfigParser would try to interpolate the
        # '%' in a percent-encoded password. env.py prefers this override.
        config.attributes["override_url"] = DATABASE_URL
        command.upgrade(config, "head")
    else:
        SQLModel.metadata.create_all(engine)


def _drop_schema() -> None:
    if _SCHEMA_FROM_MIGRATIONS and IS_POSTGRESQL and engine.dialect.name == "postgresql":
        from sqlalchemy import text

        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    else:
        SQLModel.metadata.drop_all(engine)


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session]:
    _print_dialect_evidence()
    _build_schema()
    with Session(engine) as session:
        from app.core.db import init_db

        init_db(session)
        yield session
    _drop_schema()
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
