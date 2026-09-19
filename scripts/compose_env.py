"""Generate an isolated compose env file for testing or local deployment.

Why: compose.yaml reads ``.env`` by default, and ``docker compose --env-file``
only changes interpolation, not the ``env_file:`` a service loads. This tool
writes a dedicated env file (secrets included, git-ignored under runtime/) and
compose.yaml takes it via ``ENV_FILE=<path>`` so a test stack never reads or
overwrites the developer's everyday .env or database.

Usage:
  python scripts/compose_env.py runtime/env/t02.env

Then run the stack isolated:
  docker compose --env-file runtime/env/t02.env -p rm-t02 up -d --build
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
    print(f"Wrote isolated compose env to {target.relative_to(ROOT)} ({len(values)} keys)")


if __name__ == "__main__":
    main()
