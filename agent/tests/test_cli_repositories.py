"""T03 Agent CLI: explicit repository binding and old-server safety (A09).

These tests stub the network and scanner so no real server, account, or Git
repository is touched. The repository id must come from the user's explicit
--repository flag; a server that does not echo that id back (an old server, or
one that registered the copy as uncategorized) must fail loudly instead of
printing a false "bound" success.
"""
import sys
import uuid

import pytest

from research_agent import cli


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isolated agent home with stored credentials and a stubbed scanner."""
    monkeypatch.setenv("RESEARCH_AGENT_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "scan", lambda path: {})
    monkeypatch.setattr(cli.Path, "resolve", lambda self, strict=False: self)
    db = cli.connect_state()
    db.executemany(
        "INSERT INTO settings VALUES (?,?)",
        [("server", "http://localhost:8000"), ("token", "tok")],
    )
    db.commit()
    yield db
    db.close()


def run_link(monkeypatch, capsys, responses, repository=None):
    """Run `link` with a stubbed POST /agent/copies returning `responses`."""
    seen = {}

    def fake_request(server, endpoint, token="", body=None, form=False):
        seen["body"] = body
        return responses

    monkeypatch.setattr(cli, "request", fake_request)
    argv = ["link", "--project", str(uuid.uuid4()), "--path", "x"]
    if repository:
        argv += ["--repository", repository]
    monkeypatch.setattr(sys, "argv", ["research_agent", *argv])
    code = cli.main()
    out = capsys.readouterr()
    return code, out, seen.get("body", {})


def test_link_without_repository_registers_uncategorized(env, monkeypatch, capsys):
    copy_id = str(uuid.uuid4())
    code, out, body = run_link(
        monkeypatch, capsys, {"id": copy_id, "sequence": 0, "repository_id": None}
    )
    assert code == 0
    assert "repository_id" not in body  # no repository field sent at all
    assert "未归类" in out.out


def test_link_with_repository_confirmed_by_server(env, monkeypatch, capsys):
    repo = str(uuid.uuid4())
    code, out, body = run_link(
        monkeypatch,
        capsys,
        {"id": str(uuid.uuid4()), "sequence": 0, "repository_id": repo},
        repository=repo,
    )
    assert code == 0
    assert body["repository_id"] == repo
    assert "绑定" in out.out


def test_link_with_repository_old_server_fails(env, monkeypatch, capsys):
    """A09: an old server ignores repository_id and returns null -> fail."""
    repo = str(uuid.uuid4())
    code, out, _ = run_link(
        monkeypatch,
        capsys,
        {"id": str(uuid.uuid4()), "sequence": 0, "repository_id": None},
        repository=repo,
    )
    assert code == 1
    assert "未确认仓库绑定" in out.err
    assert "绑定成功" not in out.out and "已登记并绑定" not in out.out


def test_link_with_repository_mismatched_server_fails(env, monkeypatch, capsys):
    """A09: a server returning a DIFFERENT repository_id must also fail."""
    repo = str(uuid.uuid4())
    other = str(uuid.uuid4())
    code, out, _ = run_link(
        monkeypatch,
        capsys,
        {"id": str(uuid.uuid4()), "sequence": 0, "repository_id": other},
        repository=repo,
    )
    assert code == 1
    assert "未确认仓库绑定" in out.err


def test_repositories_command_lists(env, monkeypatch, capsys):
    repos = [
        {"id": str(uuid.uuid4()), "name": "分析代码"},
        {"id": str(uuid.uuid4()), "name": "论文排版"},
    ]
    monkeypatch.setattr(cli, "request", lambda *a, **k: repos)
    monkeypatch.setattr(
        sys, "argv", ["research_agent", "repositories", "--project", str(uuid.uuid4())]
    )
    assert cli.main() == 0
    out = capsys.readouterr().out
    assert "分析代码" in out and "论文排版" in out
    assert repos[0]["id"] in out
