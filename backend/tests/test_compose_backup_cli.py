"""CLI parsing and compose isolation checks (no Docker daemon needed).

R2: a generated env file, used exactly as documented, must be the env_file the
    backend and migrate services actually load -- never the project's .env.
R3: the backup tool must accept the documented argument order (subcommand
    first) as well as the interspersed order.
"""

import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *argv], cwd=ROOT, capture_output=True, text=True
    )


def _resolve_env_file(path: Path) -> str:
    """Mirror how compose's env_file interpolation resolves `${ENV_FILE}`."""
    raw = path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        if line.startswith("ENV_FILE="):
            value = line.split("=", 1)[1].strip()
            return value.strip('"').strip("'")
    return ""


def test_generated_env_is_self_contained_and_compose_loads_it(tmp_path):
    env_file = tmp_path / "isolated.env"
    result = _run(str(SCRIPTS / "compose_env.py"), str(env_file))
    assert result.returncode == 0, result.stderr
    text = env_file.read_text(encoding="utf-8")
    assert "ENV_FILE=" in text, "generated env must pin ENV_FILE (R2)"
    assert "POSTGRES_PASSWORD=" in text and "SECRET_KEY=" in text

    # The path the service env_file should resolve to:
    target = _resolve_env_file(env_file)
    assert target, "ENV_FILE must be present and non-empty"

    # Without a daemon: render the compose config and check the service
    # env_file points at the generated file, not the project .env.
    # --no-env-resolution reports paths without reading/printing secrets.
    config = subprocess.run(
        [
            "docker", "compose",
            "--env-file", str(env_file),
            "-p", f"rm-test-{uuid.uuid4().hex[:8]}",
            "config", "--no-env-resolution", "--format", "json",
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert config.returncode == 0, (
        config.stderr or "docker compose config failed"
    )
    rendered = json.loads(config.stdout)
    for service in ("backend", "migrate"):
        entries = rendered["services"][service].get("env_file") or []
        assert entries, f"{service} has no env_file"
        loaded = entries[0]["path"] if isinstance(entries[0], dict) else entries[0]
        assert Path(loaded).name == env_file.name, (
            f"{service} would load {loaded}, not the generated env"
        )


def test_backup_cli_accepts_documented_argument_order(tmp_path):
    env_file = tmp_path / "e.env"
    env_file.write_text("POSTGRES_USER=research\nPOSTGRES_DB=research\n")
    # Documented order: subcommand first, then the shared flags.
    for argv in (
        ("backup", "--project", "rm-x", "--compose-env", str(env_file)),
        ("--project", "rm-x", "--compose-env", str(env_file), "backup"),
        ("restore", "--file", "runtime/backups/x.dump", "--target-db", "t_test",
         "--project", "rm-x", "--compose-env", str(env_file)),
        ("--project", "rm-x", "--compose-env", str(env_file),
         "restore", "--file", "runtime/backups/x.dump", "--target-db", "t_test"),
    ):
        result = _run(str(SCRIPTS / "postgres_backup.py"), *argv)
        # A parse error exits 2 with "unrecognized arguments". Everything else
        # (env file exists, docker not running, backup missing) must NOT be a
        # parse error -- i.e. the order was accepted.
        assert result.returncode != 2 or "unrecognized arguments" not in result.stderr, (
            f"arg order rejected: {argv}\n{result.stderr}"
        )


def test_backup_cli_rejects_missing_shared_flags():
    result = _run(str(SCRIPTS / "postgres_backup.py"), "backup")
    assert result.returncode == 2
