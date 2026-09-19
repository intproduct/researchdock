"""Backup and restore the Research Manager PostgreSQL database.

Uses the running compose ``db`` service, so no local PostgreSQL client is
needed. Backups are written under ``runtime/backups/`` (git-ignored).

Safety:
- ``restore`` only accepts a target whose name is clearly a test database
  (``*_test`` / ``test_*`` / ``test``) and refuses a non-empty target unless
  ``--force-empty`` is passed, so it cannot silently overwrite a business DB.
- No password is passed on the command line or printed; credentials are
  injected by compose into the container environment.

Examples (note the isolated project name and env file; both argument orders
work -- shared flags may come before or after the subcommand):
  python scripts/postgres_backup.py --project rm-t02 --compose-env runtime/env/t02.env backup
  python scripts/postgres_backup.py backup --project rm-t02 --compose-env runtime/env/t02.env
  python scripts/postgres_backup.py --project rm-t02 --compose-env runtime/env/t02.env restore \
      --file runtime/backups/research-<stamp>.dump \
      --target-db research_restore_test
"""

import argparse
import re
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / "runtime" / "backups"
TEST_DB = re.compile(r"^test(_|$)|_test$")


def read_env(compose_env: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in compose_env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class Compose:
    def __init__(self, project: str, compose_env: Path):
        self.project = project
        self.compose_env = compose_env
        self.env = read_env(compose_env)
        self.user = self.env.get("POSTGRES_USER", "research")
        self.db = self.env.get("POSTGRES_DB", "research")

    def run(self, *args: str, capture: bool = False) -> subprocess.CompletedProcess:
        cmd = [
            "docker", "compose",
            "-p", self.project,
            "--env-file", str(self.compose_env),
            *args,
        ]
        return subprocess.run(
            cmd, cwd=ROOT, check=True, text=True, capture_output=capture,
        )

    def psql(self, database: str, sql: str, capture: bool = False):
        return self.run(
            "exec", "-T", "db",
            "psql", "-U", self.user, "-d", database, "-tAc", sql,
            capture=capture,
        )


def cmd_backup(compose: Compose) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = f"{compose.db}-{stamp}-{secrets.token_hex(3)}.dump"
    container_path = f"/tmp/{name}"
    host_path = BACKUP_DIR / name
    # Custom format (-Fc) keeps indexes/constraints for pg_restore.
    compose.run(
        "exec", "-T", "db",
        "pg_dump", "-U", compose.user, "-d", compose.db, "-Fc", "-f", container_path,
    )
    # -L follows the symlink/real path so docker cp gets the file, not a link.
    compose.run("cp", f"db:{container_path}", str(host_path))
    compose.run("exec", "-T", "db", "rm", "-f", container_path)
    print(f"Backup written to {host_path.relative_to(ROOT)} (database {compose.db})")


def schema_table_count(compose: Compose, database: str) -> int:
    result = compose.psql(
        database,
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
        capture=True,
    )
    try:
        return int(result.stdout.strip() or "0")
    except ValueError:
        return 0


def database_exists(compose: Compose, database: str) -> bool:
    result = compose.psql(
        "postgres", f"SELECT 1 FROM pg_database WHERE datname='{database}'",
        capture=True,
    )
    return result.stdout.strip() == "1"


def cmd_restore(compose: Compose, args: argparse.Namespace) -> None:
    backup = Path(args.file)
    if not backup.is_absolute():
        backup = ROOT / backup
    if not backup.exists():
        raise SystemExit(f"Backup file not found: {backup}")
    target = args.target_db
    if not TEST_DB.search(target):
        raise SystemExit(
            "Refusing to restore into a database whose name is not clearly a "
            f"test target (name={target!r}); use a name like research_restore_test."
        )
    if database_exists(compose, target):
        if schema_table_count(compose, target) > 0 and not args.force_empty:
            raise SystemExit(
                f"Target database {target!r} already has tables; refusing to "
                "overwrite without --force-empty."
            )
    else:
        compose.run("exec", "-T", "db", "createdb", "-U", compose.user, target)
    if args.force_empty:
        compose.psql(target, "DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    container_path = f"/tmp/rm-restore-{secrets.token_hex(3)}.dump"
    compose.run("cp", str(backup), f"db:{container_path}")
    # --no-owner keeps the restore independent of the original role owner.
    compose.run(
        "exec", "-T", "db",
        "pg_restore", "-U", compose.user, "-d", target, "--no-owner", container_path,
    )
    compose.run("exec", "-T", "db", "rm", "-f", container_path)
    print(f"Restored {backup.relative_to(ROOT)} into database {target}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PostgreSQL backup/restore via compose",
        epilog="Both argument orders are accepted: "
               "'backup --project P --compose-env E' and "
               "'--project P --compose-env E backup'.",
    )
    # The shared flags are accepted either before or after the subcommand so
    # the documented commands keep working verbatim (R3).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--compose-env", required=True, help="compose env file path")
    common.add_argument("--project", required=True, help="isolated compose project name")

    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backup", parents=[common], help="pg_dump the compose database")
    restore = sub.add_parser(
        "restore", parents=[common], help="restore a backup into a test database"
    )
    restore.add_argument("--file", required=True, help="backup file (under runtime/backups/)")
    restore.add_argument("--target-db", required=True, help="target test database name")
    restore.add_argument("--force-empty", action="store_true",
                         help="drop/recreate public schema in an existing target")

    # Normalize: if the subcommand appears after the shared flags, move it to
    # the front so the subparser sees it (argparse expects the subcommand first).
    argv = sys.argv[1:]
    if argv and argv[0].startswith("-"):
        for index, token in enumerate(argv):
            if token in ("backup", "restore"):
                argv = [token, *argv[:index], *argv[index + 1:]]
                break
    args = parser.parse_args(argv)

    compose_env = Path(args.compose_env)
    if not compose_env.is_absolute():
        compose_env = ROOT / compose_env
    if not compose_env.exists():
        raise SystemExit(f"Compose env file not found: {compose_env}")
    compose = Compose(args.project, compose_env)
    if args.cmd == "backup":
        cmd_backup(compose)
    else:
        cmd_restore(compose, args)


if __name__ == "__main__":
    main()
