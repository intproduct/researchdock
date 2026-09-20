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
HEAD_REVISION = "c4d8e2f15a07"
# The T02 (pre-T03) revision: schema has projectrevision but no repository yet.
T02_REVISION = "b7f3a1c29e04"

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


def seed_t02_project_with_copy(database: Path) -> str:
    """Upgrade to the T02 schema, then add one project with one working copy.

    Returns the copy id. The copy has a sequence and an observation so the T03
    upgrade must preserve them while adding the binding columns.
    """
    alembic(database, "upgrade", T02_REVISION)
    device_id = uuid.uuid4().hex
    copy_id = uuid.uuid4().hex
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
        " VALUES (?, ?, 'p', '', 'active', '', '', 1, '2026-09-10 08:00:00',"
        " '2026-09-15 09:30:00')",
        (PROJECT_ID, OWNER_ID),
    )
    connection.execute(
        "INSERT INTO device (id, owner_id, name, platform, token_hash, revoked,"
        " created_at) VALUES (?, ?, 'dev', 'Windows', ?, 0, '2026-09-10 08:00:00')",
        (device_id, OWNER_ID, "x" * 64),
    )
    connection.execute(
        "INSERT INTO workingcopy (id, project_id, device_id, local_path, sequence,"
        " branch, head, dirty, changed_files, untracked_files, comparison, reason)"
        " VALUES (?, ?, ?, ?, 5, 'main', ?, 1, 2, 1, 'ahead', 'n')",
        (copy_id, PROJECT_ID, device_id, "C:/research/legacy", "a" * 40),
    )
    connection.commit()
    connection.close()
    return copy_id


def test_t03_upgrade_preserves_data_and_adds_empty_repository(tmp_path):
    """A10: upgrading a real-shaped T02 database keeps every old row intact."""
    database = tmp_path / "t02.db"
    copy_id = seed_t02_project_with_copy(database)
    alembic(database, "upgrade", "head")

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    # Repository table exists but starts empty: no auto-created repositories.
    assert connection.execute("SELECT COUNT(*) FROM repository").fetchone()[0] == 0
    row = connection.execute(
        "SELECT id, project_id, local_path, sequence, head, dirty,"
        " repository_id, binding_revision FROM workingcopy"
    ).fetchone()
    connection.close()
    # Old identity, sequence and observation survive; new columns default.
    assert row["id"] == copy_id
    assert row["sequence"] == 5
    assert row["head"] == "a" * 40
    assert row["dirty"] == 1
    assert row["repository_id"] is None
    assert row["binding_revision"] == 0


def test_t03_downgrade_drops_binding_but_keeps_copies_and_history(tmp_path):
    """A10/A12: downgrade removes only the new metadata; old data is preserved."""
    database = tmp_path / "roundtrip.db"
    seed_t02_project_with_copy(database)
    alembic(database, "upgrade", "head")
    alembic(database, "downgrade", T02_REVISION)

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    names = {
        r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "repository" not in names
    columns = {r[1] for r in connection.execute("PRAGMA table_info(workingcopy)")}
    assert "repository_id" not in columns and "binding_revision" not in columns
    # The copy and its observation survive the downgrade.
    row = connection.execute("SELECT sequence, head FROM workingcopy").fetchone()
    connection.close()
    assert row["sequence"] == 5 and row["head"] == "a" * 40

    # Re-upgrade restores the binding columns without inventing repositories.
    alembic(database, "upgrade", "head")
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT COUNT(*) FROM repository").fetchone()[0] == 0
    row = connection.execute(
        "SELECT repository_id, binding_revision FROM workingcopy"
    ).fetchone()
    connection.close()
    assert row == (None, 0)
