import subprocess

import pytest

from research_agent.scanner import ScanError, redact_remote, scan


def g(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, encoding="utf-8"
    ).stdout.strip()


def commit(root, name, text):
    (root / name).write_text(text, encoding="utf-8")
    g(root, "add", "--", name)
    g(root, "commit", "-m", name)
    return g(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "中文项目"
    path.mkdir()
    g(path, "init", "-b", "main")
    g(path, "config", "user.name", "Test")
    g(path, "config", "user.email", "test@example.com")
    commit(path, "paper.md", "base")
    g(path, "remote", "add", "origin", "https://github.com/example/research.git")
    g(path, "update-ref", "refs/remotes/origin/main", "HEAD")
    g(path, "branch", "--set-upstream-to=origin/main", "main")
    return path


def test_git_relationships_and_no_mutation(repo):
    before = (repo / ".git/index").read_bytes()
    base = g(repo, "rev-parse", "HEAD")
    assert scan(str(repo))["comparison"] == "synced"
    assert (repo / ".git/index").read_bytes() == before
    assert g(repo, "rev-parse", "HEAD") == base
    commit(repo, "code.py", "print(1)")
    result = scan(str(repo))
    assert result["comparison"] == "ahead" and result["ahead"] == 1
    newer = g(repo, "rev-parse", "HEAD")
    g(repo, "update-ref", "refs/remotes/origin/main", newer)
    g(repo, "reset", "--hard", base)
    assert scan(str(repo))["comparison"] == "behind"
    commit(repo, "other.py", "print(2)")
    result = scan(str(repo))
    assert result["comparison"] == "diverged" and result["ahead"] == result["behind"] == 1


def test_dirty_detached_shallow_and_empty(repo, tmp_path):
    (repo / "paper.md").write_text("changed")
    (repo / "new.txt").write_text("not tracked")
    result = scan(str(repo))
    assert result["comparison"] == "synced" and result["dirty"]
    assert result["changed_files"] == 1 and result["untracked_files"] == 1
    g(repo, "checkout", "--detach")
    assert "HEAD" in scan(str(repo))["reason"]
    shallow = tmp_path / "shallow"
    g(tmp_path, "clone", "--depth", "1", repo.as_uri(), str(shallow))
    assert scan(str(shallow))["comparison"] == "unknown"
    empty = tmp_path / "empty"
    empty.mkdir()
    g(empty, "init", "-b", "main")
    assert scan(str(empty))["head"] is None
    child = repo / "sub"
    child.mkdir()
    with pytest.raises(ScanError):
        scan(str(child))


@pytest.mark.parametrize(
    "source,expected",
    [
        ("https://secret:pass@github.com/owner/repo?token=x#y", "https://github.com/owner/repo"),
        ("git@github.com:owner/repo.git", "github.com:owner/repo.git"),
        ("ssh://git@server:2222/repo", "ssh://server:2222/repo"),
    ],
)
def test_credentials_redacted(source, expected):
    assert redact_remote(source) == expected


def test_offline_outbox_retries_same_event(repo, tmp_path, monkeypatch):
    from research_agent import cli

    monkeypatch.setenv("RESEARCH_AGENT_HOME", str(tmp_path / "state"))
    with cli.connect_state() as db:
        db.executemany(
            "INSERT INTO settings VALUES (?,?)",
            [("server", "http://localhost:8000"), ("token", "fake-device")],
        )
        db.execute("INSERT INTO copies VALUES (?,?,0)", ("copy-one", str(repo)))
        db.commit()

        def offline(*args, **kwargs):
            raise ValueError("offline")

        monkeypatch.setattr(cli, "request", offline)
        assert cli.run_scan(db) == 1
        assert db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 1
        monkeypatch.setattr(cli, "request", lambda *args, **kwargs: {"ok": True})
        assert cli.run_scan(db) == 0
        assert db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
        assert db.execute("SELECT sequence FROM copies").fetchone()[0] == 2
