"""Create local-only credentials and migrate the database. Run with .venv Python."""

import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    env_file = ROOT / ".env"
    (ROOT / "runtime").mkdir(exist_ok=True)
    if not env_file.exists():
        password = secrets.token_urlsafe(20)
        values = {
            "PROJECT_NAME": "Research Manager",
            "SECRET_KEY": secrets.token_urlsafe(48),
            "DATABASE_URL": "sqlite:///./research.db",
            "FRONTEND_HOST": "http://localhost:5173",
            "FIRST_SUPERUSER": "admin@example.com",
            "FIRST_SUPERUSER_PASSWORD": password,
            "ENABLE_SIGNUP": "false",
        }
        env_file.write_text(
            "\n".join(f'{key}="{value}"' for key, value in values.items()) + "\n", encoding="utf-8"
        )
        credentials = ROOT / "credentials.local.txt"
        credentials.write_text(
            f"本地初始账户：admin@example.com\n初始密码：{password}\n登录后可在账户设置修改密码。此文件不提交到 Git。\n",
            encoding="utf-8",
        )
        if os.name != "nt":
            env_file.chmod(0o600)
            credentials.chmod(0o600)
        print("Created .env and credentials.local.txt (excluded from Git).")
    if "--env-only" in sys.argv:
        return
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "backend", check=True
    )
    subprocess.run([sys.executable, "-m", "app.initial_data"], cwd=ROOT / "backend", check=True)
    print("Ready. Login details: credentials.local.txt")


if __name__ == "__main__":
    main()
