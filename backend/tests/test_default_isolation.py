"""R1 regression: the default test path must never touch an existing database.

The audit found that a pre-existing DATABASE_URL was honoured by default mode,
after which the session-scoped fixtures dropped its tables. These checks run the
real conftest through pytest in a subprocess (so import-time env handling and
the fixture lifecycle are exercised exactly as normal) and assert an unrelated
sentinel database is left intact.
"""

import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).resolve().parent

# A minimal test module that lets the real conftest build and tear down schema.
_CHILD_TEST = """
def test_noop():
    assert True
"""


def _prepare_sentinel(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sentinel (id INTEGER PRIMARY KEY, note TEXT)")
    conn.execute("INSERT INTO sentinel (note) VALUES ('do-not-drop')")
    conn.commit()
    conn.close()


def _sentinel_intact(path: Path) -> bool:
    conn = sqlite3.connect(path)
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        count = conn.execute("SELECT count(*) FROM sentinel").fetchone()[0]
    finally:
        conn.close()
    return "sentinel" in names and count == 1


def _run_suite(sentinel: Path, *, as_test_url: bool) -> subprocess.CompletedProcess:
    """Run the real suite on a temp child test, pointed at the sentinel DB."""
    child = TESTS_DIR / f"test_tmp_isolation_{uuid.uuid4().hex[:8]}.py"
    child.write_text(_CHILD_TEST, encoding="utf-8")
    database_url = "sqlite:///" + sentinel.as_posix()
    env = dict(os.environ)
    env.pop("TEST_DATABASE_URL", None)
    env.pop("TEST_SCHEMA_FROM_MIGRATIONS", None)
    env["PYTHONUTF8"] = "1"
    if as_test_url:
        env["TEST_DATABASE_URL"] = database_url
        env.pop("DATABASE_URL", None)
    else:
        env["DATABASE_URL"] = database_url  # an "ordinary" env var
    try:
        return subprocess.run(
            [
                sys.executable, "-m", "pytest", str(child), "-q", "-rA",
                "-p", "no:cacheprovider",
                "--basetemp", str(sentinel.parent / "basetemp"),
            ],
            cwd=ROOT, capture_output=True, text=True, env=env, timeout=300,
        )
    finally:
        child.unlink(missing_ok=True)


def test_default_mode_ignores_ordinary_database_url(tmp_path):
    """A leaked DATABASE_URL must not become the test target (R1)."""
    sentinel = tmp_path / "ordinary.db"
    _prepare_sentinel(sentinel)
    result = _run_suite(sentinel, as_test_url=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _sentinel_intact(sentinel), (
        "default test mode dropped tables in an ordinary DATABASE_URL"
    )
    # The run must have reported using its own temp SQLite, not the sentinel.
    assert sentinel.as_posix() not in (result.stdout + result.stderr)


def test_explicit_test_database_url_is_used(tmp_path):
    """An explicit TEST_DATABASE_URL is the one and only external target (R1)."""
    sentinel = tmp_path / "sentinel_test.db"
    _prepare_sentinel(sentinel)
    result = _run_suite(sentinel, as_test_url=True)
    assert result.returncode == 0, result.stdout + result.stderr
    # Proof of use: the conftest reports its own dialect line naming this file.
    assert sentinel.name in (result.stdout + result.stderr), (
        "explicit TEST_DATABASE_URL was not the database used"
    )


def test_unusable_test_database_url_fails_without_sqlite_fallback(tmp_path):
    """A requested-but-unreachable PostgreSQL must fail, not fall back."""
    env = dict(os.environ)
    env["TEST_DATABASE_URL"] = (
        "postgresql+psycopg://nobody:nopass@127.0.0.1:1/nonexistent_test"
    )
    env["PYTHONUTF8"] = "1"
    child = TESTS_DIR / f"test_tmp_isolation_{uuid.uuid4().hex[:8]}.py"
    child.write_text(_CHILD_TEST, encoding="utf-8")
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest", str(child), "-q",
                "-p", "no:cacheprovider",
                "--basetemp", str(tmp_path / "basetemp"),
            ],
            cwd=ROOT, capture_output=True, text=True, env=env, timeout=300,
        )
    finally:
        child.unlink(missing_ok=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "sqlite" not in result.stdout.lower() or "error" in result.stdout.lower()
