"""Generate an isolated compose env file for testing or local deployment.

Why: ``docker compose --env-file X`` only changes *interpolation*. The
``env_file:`` a service loads is separate, so without setting ``ENV_FILE`` the
backend/migrate containers would still read the developer's everyday ``.env``
and mix in its SECRET_KEY, accounts and DATABASE_URL (R2).

This tool therefore writes a dedicated env file (secrets included, git-ignored
under runtime/) that also contains ``ENV_FILE=<its own absolute path>``, so the
documented command alone gives a fully isolated stack:

  python scripts/compose_env.py runtime/env/t02.env
  docker compose --env-file runtime/env/t02.env -p rm-t02 up -d --build

Verifying isolation without a daemon:
  docker compose --env-file runtime/env/t02.env -p rm-t02 \
      config --no-env-resolution --format json
  # both backend and migrate env_file[0].path must equal the generated path
"""

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/compose_env.py <output-env-path>")
    target = Path(sys.argv[1])
    if not target.is_absolute():
        target = ROOT / target
    if target.exists():
        raise SystemExit(f"Refusing to overwrite existing env file: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    values = {
        # Pin the service env_file to this very file so the stack cannot fall
        # back to the project's .env (path is quoted: compose keeps it literal).
        "ENV_FILE": f'"{target.as_posix()}"',
        "PROJECT_NAME": "Research Manager",
        "SECRET_KEY": secrets.token_urlsafe(48),
        # Compose builds the Postgres DSN from these; the password is
        # percent-encoded in Settings, so reserved characters are safe.
        "POSTGRES_USER": "research",
        "POSTGRES_DB": "research",
        "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
        "FRONTEND_HOST": "http://127.0.0.1:8080",
        "FIRST_SUPERUSER": "admin@example.com",
        "FIRST_SUPERUSER_PASSWORD": secrets.token_urlsafe(20),
        "ENABLE_SIGNUP": "false",
        "PUBLIC_PORT": "8080",
    }
    target.write_text(
        "\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8"
    )
    try:
        target.chmod(0o600)
    except OSError:
        pass  # best effort on Windows
    try:
        shown = target.relative_to(ROOT)
    except ValueError:
        # Output outside the repo (e.g. a default CI temp dir) is valid.
        shown = target
    print(
        f"Wrote isolated compose env to {shown} ({len(values)} keys, ENV_FILE pinned)"
    )


if __name__ == "__main__":
    main()
