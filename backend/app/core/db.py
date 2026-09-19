from sqlalchemy import event
from sqlmodel import Session, create_engine, select

from app import (
    crud,
    research_models,  # noqa: F401 -- register research tables
)
from app.core.config import settings
from app.models import User, UserCreate


def create_engine_for(database_url: str):
    """Build an engine for a given URL; SQLite gets thread/foreign-key tweaks.

    Keeping this a function lets tests and tools construct a PostgreSQL engine
    explicitly (TEST_DATABASE_URL) instead of relying on the import-time engine.
    """
    is_sqlite = database_url.startswith("sqlite")
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    return engine


engine = create_engine_for(str(settings.DATABASE_URL))


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # This works because the models are already imported and registered from app.models
    # SQLModel.metadata.create_all(engine)

    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = crud.create_user(session=session, user_create=user_in)
