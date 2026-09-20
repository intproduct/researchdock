"""T03 A13 Windows CLI smoke: two isolated agents bind one repository.

Boots a throwaway backend (temp SQLite, free loopback port, test-only secret),
creates a project + repository through the real HTTP API, then runs two agents
with separate RESEARCH_AGENT_HOME and separate device enrollments that both
link the SAME repository UUID and report an observation. Finally it reads the
project copies back and asserts both copies are grouped under that repository.

No real user repository, account, or credential is touched. Temporary git repos
are created only as scanner inputs and are never written to by the agent.
"""
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
PORT = None
BASE = None


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http(path, body=None, token=None, method=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}/api/v1{path}", data=data,
        method=method or ("POST" if body is not None else "GET"),
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def login_token(email, password):
    data = urllib.parse.urlencode({"username": email, "password": password}).encode()
    req = urllib.request.Request(f"{BASE}/api/v1/login/access-token", data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["access_token"]


def wait_ready(timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{BASE}/api/v1/utils/health-check/", timeout=3)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def make_git_repo(path: Path):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    (path / "f.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=path, check=True,
    )


def run_agent(home: Path, argv: list[str]):
    env = os.environ.copy()
    env["RESEARCH_AGENT_HOME"] = str(home)
    env["PYTHONPATH"] = str(ROOT / "agent")
    return subprocess.run(
        [PY, "-m", "research_agent", *argv],
        env=env, capture_output=True, text=True, cwd=ROOT / "agent",
    )


def main():
    global PORT, BASE
    PORT = free_port()
    BASE = f"http://127.0.0.1:{PORT}"
    work = Path(tempfile.mkdtemp(prefix="t03-smoke-"))
    db_file = work / "smoke.db"
    email, password = "smoke@example.com", "smoke-pass-2026"

    env = os.environ.copy()
    env.update({
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "SECRET_KEY": "t03-smoke-secret-key-0123456789abcdef",
        "FIRST_SUPERUSER": email,
        "FIRST_SUPERUSER_PASSWORD": password,
        "ENABLE_SIGNUP": "true",
        "EMAILS_FROM_EMAIL": "noreply@example.com",
        "FASTAPI_ENV": "development",
        "PYTHONPATH": str(ROOT / "backend"),
    })

    # Migrate schema, then start the server as a subprocess so it reads the same
    # isolated DATABASE_URL/secret (importing app.main in-process can race env).
    subprocess.run(
        [PY, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend", env=env, check=True, capture_output=True,
    )
    # Create the initial superuser; uvicorn does not run init_db on startup.
    subprocess.run(
        [PY, "app/initial_data.py"],
        cwd=ROOT / "backend", env=env, check=True, capture_output=True,
    )
    server = subprocess.Popen(
        [PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(PORT), "--log-level", "error"],
        cwd=ROOT / "backend", env=env,
    )
    if not wait_ready():
        print("FAIL: server did not become ready", flush=True)
        server.terminate()
        return 1
    print(f"server ready on {BASE}", flush=True)

    token = login_token(email, password)
    project = http("/projects", {"name": "论文A", "stage": "active"}, token)
    repo = http(f"/projects/{project['id']}/repositories", {"name": "分析代码"}, token)
    print(f"project={project['id']} repository={repo['id']}")

    # Two isolated agents, each with its own home and device, both binding the
    # same repository UUID. Device enrollment is done over HTTP (equivalent to
    # `login`, which prompts for a password that cannot be piped non-interactively
    # on Windows); the device token is written into each agent's own state db.
    reports = []
    for name, sub in (("win-agent-a", "a"), ("win-agent-b", "b")):
        home = work / f"home-{sub}"
        repo_dir = work / f"repo-{sub}"
        make_git_repo(repo_dir)
        enrollment = http("/devices", {"name": name, "platform": "Windows"}, token)
        home.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(home / "agent.db")
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.executemany("INSERT INTO settings VALUES (?,?)",
                         [("server", BASE), ("token", enrollment["token"])])
        conn.commit()
        conn.close()
        repos = run_agent(home, ["repositories", "--project", project["id"]])
        assert repos.returncode == 0 and repo["id"] in repos.stdout, repos.stderr
        link = run_agent(home, [
            "link", "--project", project["id"], "--repository", repo["id"],
            "--path", str(repo_dir),
        ])
        assert link.returncode == 0, f"link {name}: {link.stderr}"
        print(f"linked {name}", flush=True)
        scan = run_agent(home, ["scan"])
        assert scan.returncode == 0, f"scan {name}: {scan.stderr}"
        print(f"scanned {name}", flush=True)
        reports.append((name, link.stdout.strip()))

    # Both copies must be grouped under the same repository server-side.
    copies = http(f"/projects/{project['id']}/copies", None, token)
    assert len(copies) == 2, copies
    assert all(c["repository_id"] == repo["id"] for c in copies), copies
    assert all(c["binding_revision"] == 1 for c in copies), copies
    assert all(c["sequence"] >= 1 for c in copies), copies
    # Uncategorized group is empty.
    assert not any(c["repository_id"] is None for c in copies), copies

    server.terminate()
    try:
        server.wait(timeout=10)
    except Exception:
        server.kill()
    shutil.rmtree(work, True)
    print("A13 SMOKE OK: 2 isolated agents bound one repository; grouped correctly")
    for name, msg in reports:
        print(f"  {name}: {msg}")
    return 0


if __name__ == "__main__":
    import urllib.parse
    raise SystemExit(main())
