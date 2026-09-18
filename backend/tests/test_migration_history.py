"""Migration checks for the projectrevision table on isolated SQLite files.

These never touch the development database: each test builds a temporary
SQLite file, seeds it with the pre-T01 schema, then runs Alembic in a
subprocess with DATABASE_URL pointed at that file (env.py reads the URL from
settings, so an in-process Config override would hit the dev database).
"""

import json
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
BASE_REVISION = "d42026f707b5"
HEAD_REVISION = "b7f3a1c29e04"

OWNER_ID = uuid.uuid4().hex
PROJECT_ID = uuid.uuid4().hex


def alembic(database: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def seed_base_project(database: Path) -> None:
    """Upgrade to the pre-T01 revision, then add one project already at revision 3."""
    alembic(database, "upgrade", BASE_REVISION)
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        "INSERT INTO user (id, email, is_active, is_superuser, hashed_password)"
        " VALUES (?, ?, 1, 1, 'x')",
        (OWNER_ID, "owner@example.com"),
    )
    connection.execute(
        "INSERT INTO project (id, owner_id, name, description, stage,"
        " status_note, next_step, revision, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            PROJECT_ID,
            OWNER_ID,
            "迁移前项目",
            "已有描述",
            "active",
            "已有进展",
            "已有下一步",
            3,
            "2026-09-10 08:00:00",
            "2026-09-15 09:30:00",
        ),
    )
    connection.commit()
    connection.close()


def read_revisions(database: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT * FROM projectrevision ORDER BY revision DESC"
    ).fetchall()
    connection.close()
    return rows


def test_upgrade_backfills_single_baseline_and_is_idempotent(tmp_path):
    database = tmp_path / "migrate.db"
    seed_base_project(database)
    alembic(database, "upgrade", "head")

    rows = read_revisions(database)
    assert len(rows) == 1
    row = rows[0]
    assert row["project_id"] == PROJECT_ID
    assert row["revision"] == 3
    assert row["origin"] == "migrated_baseline"
    assert row["actor_id"] is None
    assert json.loads(row["snapshot"]) == {
        "name": "迁移前项目",
        "description": "已有描述",
        "stage": "active",
        "status_note": "已有进展",
        "next_step": "已有下一步",
    }
    # project_updated_at keeps the real last edit; recorded_at is migration time.
    assert row["project_updated_at"].startswith("2026-09-15 09:30")
    assert row["recorded_at"] != row["project_updated_at"]

    # Re-running upgrade head must not duplicate the baseline row.
    alembic(database, "upgrade", "head")
    assert len(read_revisions(database)) == 1


def test_downgrade_drops_history_and_reupgrade_restores_baseline(tmp_path):
    database = tmp_path / "roundtrip.db"
    seed_base_project(database)
    alembic(database, "upgrade", "head")
    assert len(read_revisions(database)) == 1

    alembic(database, "downgrade", BASE_REVISION)
    connection = sqlite3.connect(database)
    names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    connection.close()
    assert "projectrevision" not in names
    assert "project" in names

    alembic(database, "upgrade", "head")
    rows = read_revisions(database)
    assert len(rows) == 1
    assert rows[0]["revision"] == 3
    assert rows[0]["origin"] == "migrated_baseline"


def test_upgrade_on_empty_database_creates_empty_history(tmp_path):
    database = tmp_path / "empty.db"
    alembic(database, "upgrade", "head")
    assert read_revisions(database) == []
    result = alembic(database, "current")
    assert HEAD_REVISION in result.stdout


def test_head_revision_matches_model_metadata(tmp_path):
    """The migrated schema must match the SQLModel metadata for the new table."""
    from sqlalchemy import create_engine, inspect

    database = tmp_path / "schema.db"
    alembic(database, "upgrade", "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    columns = {
        column["name"]
        for column in inspect(engine).get_columns("projectrevision")
    }
    engine.dispose()
    assert columns == {
        "id",
        "project_id",
        "revision",
        "snapshot",
        "actor_id",
        "origin",
        "recorded_at",
        "project_updated_at",
    }
