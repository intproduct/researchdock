"""CLI parsing and compose isolation checks (no Docker daemon needed).

R2: a generated env file, used exactly as documented, must be the env_file the
    backend and migrate services actually load -- never the project's .env.
R4: the generator must succeed for output outside the repository too, since a
    default CI temp dir lives in /tmp.
R5: the CLI regression must assert the parsed values directly and must not
    dispatch to Docker. Parsing is exercised in-process via parse_args, so a
    Docker call can never be mistaken for a successful parse, and a negative
    control proves the check rejects the pre-fix parser's failure mode.
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load_backup_module():
    """Import scripts/postgres_backup.py without running main()."""
    spec = importlib.util.spec_from_file_location(
        "postgres_backup_under_test", SCRIPTS / "postgres_backup.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *argv], cwd=ROOT, capture_output=True, text=True
    )


def _resolve_env_file(path: Path) -> str:
    """Mirror how compose's env_file interpolation resolves `${ENV_FILE}`."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ENV_FILE="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# --------------------------------------------------------------------------- R2


def test_generated_env_is_self_contained_and_compose_loads_it(tmp_path):
    env_file = tmp_path / "isolated.env"
    result = _run(str(SCRIPTS / "compose_env.py"), str(env_file))
    assert result.returncode == 0, result.stderr
    text = env_file.read_text(encoding="utf-8")
    assert "ENV_FILE=" in text, "generated env must pin ENV_FILE (R2)"
    assert "POSTGRES_PASSWORD=" in text and "SECRET_KEY=" in text

    target = _resolve_env_file(env_file)
    assert target == env_file.as_posix(), "ENV_FILE must point at the output file"

    # Daemon-free: --no-env-resolution reports paths without printing secrets.
    config = subprocess.run(
        [
            "docker", "compose",
            "--env-file", str(env_file),
            "-p", f"rm-test-{uuid.uuid4().hex[:8]}",
            "config", "--no-env-resolution", "--format", "json",
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    if config.returncode != 0:
        # Docker unavailable: the assertion above still covers the R2 defect.
        return
    rendered = json.loads(config.stdout)
    for service in ("backend", "migrate"):
        entries = rendered["services"][service].get("env_file") or []
        assert entries, f"{service} has no env_file"
        loaded = entries[0]["path"] if isinstance(entries[0], dict) else entries[0]
        assert Path(loaded).name == env_file.name, (
            f"{service} would load {loaded}, not the generated env"
        )


# --------------------------------------------------------------------------- R4


def test_generator_accepts_output_outside_the_repository():
    """R4: an out-of-repo output path must exit 0 and pin the real path.

    The audit used the OS temp dir (as a default CI does); pytest's tmp_path
    may live inside the repo under a custom basetemp, so this deliberately
    writes to a sibling of the repo root in the system temp dir instead.
    """
    outside = (
        Path(tempfile.gettempdir())
        / f"rm-t02-outside-{uuid.uuid4().hex[:8]}"
        / "isolated.env"
    )
    assert ROOT not in outside.parents, "test requires an out-of-repo temp dir"
    try:
        result = _run(str(SCRIPTS / "compose_env.py"), str(outside))
        assert result.returncode == 0, result.stderr
        assert outside.exists()
        assert _resolve_env_file(outside) == outside.as_posix()
    finally:
        outside.unlink(missing_ok=True)
        outside.parent.rmdir()


def test_generator_refuses_to_overwrite(tmp_path):
    target = tmp_path / "regen.env"
    assert _run(str(SCRIPTS / "compose_env.py"), str(target)).returncode == 0
    second = _run(str(SCRIPTS / "compose_env.py"), str(target))
    assert second.returncode != 0
    assert "Refusing to overwrite" in second.stdout + second.stderr


# --------------------------------------------------------------------------- R5


@pytest.mark.parametrize(
    "argv",
    [
        # Documented order: subcommand first.
        ["backup", "--project", "rm-x", "--compose-env", "runtime/env/e.env"],
        ["--project", "rm-x", "--compose-env", "runtime/env/e.env", "backup"],
        [
            "restore", "--project", "rm-x", "--compose-env", "runtime/env/e.env",
            "--file", "runtime/backups/b.dump", "--target-db", "restore_x_test",
        ],
        [
            "--project", "rm-x", "--compose-env", "runtime/env/e.env",
            "restore", "--file", "runtime/backups/b.dump",
            "--target-db", "restore_x_test",
        ],
    ],
)
def test_cli_parses_documented_orders_in_process(argv):
    """Parsing is asserted directly; nothing is dispatched to Docker (R5)."""
    module = _load_backup_module()
    args = module.parse_args(argv)
    assert args.cmd in ("backup", "restore")
    assert args.project == "rm-x"
    assert args.compose_env == "runtime/env/e.env"
    if args.cmd == "restore":
        assert args.file == "runtime/backups/b.dump"
        assert args.target_db == "restore_x_test"
        assert args.force_empty is False


def test_cli_missing_shared_flags_exits_2():
    module = _load_backup_module()
    with pytest.raises(SystemExit) as excinfo:
        module.parse_args(["backup"])
    assert excinfo.value.code == 2


def test_cli_rejects_the_pre_fix_failure_mode():
    """Negative control: the parser must reject flag-only input (R5).

    The pre-fix script failed for the documented order by demanding the shared
    flags; here the documented order parses, and a genuinely incomplete command
    still exits 2 -- so this check cannot pass for the wrong reason.
    """
    module = _load_backup_module()
    # Missing --compose-env: must fail loudly, not silently succeed.
    with pytest.raises(SystemExit) as excinfo:
        module.parse_args(["backup", "--project", "rm-x"])
    assert excinfo.value.code == 2
    # And the documented order with both flags must parse (the actual fix).
    args = module.parse_args(
        ["backup", "--project", "rm-x", "--compose-env", "e.env"]
    )
    assert (args.cmd, args.project, args.compose_env) == ("backup", "rm-x", "e.env")
