import argparse
import getpass
import json
import os
import platform
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .scanner import ScanError, scan


def request(server: str, endpoint: str, token: str = "", body=None, form=False):
    url = urllib.parse.urlsplit(server)
    if url.scheme != "https" and not (
        url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("远端服务器必须使用 HTTPS；HTTP 仅支持本机回环地址")
    if url.username or url.password or url.query or url.fragment:
        raise ValueError("服务器地址不能包含凭据、查询参数或片段")
    data = (
        None
        if body is None
        else (urllib.parse.urlencode(body).encode() if form else json.dumps(body).encode())
    )
    headers = {"Content-Type": "application/x-www-form-urlencoded" if form else "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        server.rstrip("/") + "/api/v1" + endpoint, data=data, headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"服务器返回 HTTP {exc.code}；请检查账户、设备凭据或项目绑定") from None
    except urllib.error.URLError:
        raise ValueError("无法连接服务器；观察记录已保留，可重试") from None


def state_path() -> Path:
    return Path(os.environ.get("RESEARCH_AGENT_HOME", str(Path.home() / ".research-manager")))


def connect_state():
    home = state_path()
    home.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        home.chmod(0o700)
    db = sqlite3.connect(home / "agent.db", timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript("""
      CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS copies (id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, sequence INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS outbox (copy_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
    """)
    if os.name != "nt":
        (home / "agent.db").chmod(0o600)
    return db


def credentials(db):
    settings = dict(db.execute("SELECT key,value FROM settings").fetchall())
    if "token" not in settings:
        raise ValueError("请先执行 research-agent login")
    return settings["server"], settings["token"]


def login(args, db):
    if db.execute("SELECT 1 FROM settings WHERE key='token'").fetchone():
        raise ValueError("此配置目录已配对；更换账户请使用新的 RESEARCH_AGENT_HOME，避免混用副本")
    password = getpass.getpass("账户密码：")
    auth = request(
        args.server,
        "/login/access-token",
        body={"username": args.email, "password": password},
        form=True,
    )
    enrollment = request(
        args.server,
        "/devices",
        auth["access_token"],
        {"name": args.name or platform.node(), "platform": platform.system()},
    )
    with db:
        db.executemany(
            "INSERT INTO settings VALUES (?,?)",
            [("server", args.server), ("token", enrollment["token"])],
        )
    print("设备配对完成。仅保存设备凭据，不保存账户密码。")


def run_scan(db):
    server, token = credentials(db)
    failures = 0
    for copy in db.execute("SELECT * FROM copies").fetchall():
        try:
            observation = scan(copy["path"])
            # Atomic allocation ensures concurrent scans cannot reuse a sequence.
            with db:
                seq = db.execute(
                    "UPDATE copies SET sequence=sequence+1 WHERE id=? RETURNING sequence",
                    (copy["id"],),
                ).fetchone()[0]
                observation["sequence"] = seq
                db.execute(
                    "INSERT INTO outbox VALUES (?,?) ON CONFLICT(copy_id) DO UPDATE SET payload=excluded.payload",
                    (copy["id"], json.dumps(observation)),
                )
        except (ScanError, OSError) as exc:
            failures += 1
            print(f"扫描未完成：{copy['path']}：{exc}", file=sys.stderr)
    # Latest-state outbox deliberately coalesces intermediate observations.
    for item in db.execute("SELECT * FROM outbox").fetchall():
        try:
            request(
                server,
                f"/agent/copies/{item['copy_id']}/observations",
                token,
                json.loads(item["payload"]),
            )
            with db:
                db.execute(
                    "DELETE FROM outbox WHERE copy_id=? AND payload=?",
                    (item["copy_id"], item["payload"]),
                )
        except ValueError as exc:
            failures += 1
            print(str(exc), file=sys.stderr)
    try:
        request(server, "/agent/heartbeat", token, {})
    except ValueError as exc:
        failures += 1
        print(str(exc), file=sys.stderr)
    pending = db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
    print(f"扫描完成；待上报 {pending} 条，失败 {failures} 项。未修改仓库文件。")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description="科研项目只读观察客户端")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("login", help="通过账户配对当前设备")
    p.add_argument("--server", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--name")
    commands.add_parser("projects", help="查看可绑定的项目 ID")
    p = commands.add_parser("repositories", help="查看项目下可绑定的仓库 ID")
    p.add_argument("--project", required=True)
    p = commands.add_parser("link", help="显式登记一个仓库根目录")
    p.add_argument("--project", required=True)
    p.add_argument("--path", required=True)
    p.add_argument(
        "--repository",
        help="可选：显式绑定到该仓库 UUID；仓库身份来自网页确认，不由 remote 推断",
    )
    p = commands.add_parser("scan", help="只读扫描并上报，断网时保存最后观察")
    p.add_argument("--watch", type=int, default=0, help="每隔多少秒重复扫描，至少 15 秒")
    commands.add_parser("status", help="查看本地登记与待上报数量")
    args = parser.parse_args()
    if args.command == "scan" and args.watch and args.watch < 15:
        parser.error("--watch 至少为 15 秒")
    try:
        with connect_state() as db:
            if args.command == "login":
                login(args, db)
            elif args.command == "status":
                for copy in db.execute("SELECT * FROM copies"):
                    print(f"{copy['id']}  {copy['path']}  seq={copy['sequence']}")
                print("待上报：", db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])
            elif args.command == "projects":
                server, token = credentials(db)
                for project in request(server, "/agent/projects", token):
                    print(f"{project['id']}  {project['name']}")
            elif args.command == "repositories":
                server, token = credentials(db)
                for repo in request(
                    server, f"/agent/projects/{args.project}/repositories", token
                ):
                    print(f"{repo['id']}  {repo['name']}")
            elif args.command == "link":
                path = str(Path(args.path).expanduser().resolve(strict=True))
                scan(path)  # Validate Git root before any registration.
                server, token = credentials(db)
                body = {"project_id": args.project, "local_path": path}
                if args.repository:
                    body["repository_id"] = args.repository
                copy = request(server, "/agent/copies", token, body)
                if args.repository:
                    # An explicit bind must be confirmed by the server. An old
                    # server that ignores repository_id (returns null/absent) or
                    # a mismatched one means the bind did NOT happen; fail rather
                    # than print a false "bound" success. Never retry to mutate.
                    returned = copy.get("repository_id")
                    if returned != args.repository:
                        raise ValueError(
                            "服务器未确认仓库绑定（可能为旧版本服务端，副本或已登记为未归类）；"
                            "请升级服务端并在网页核对关联，不要重试篡改绑定"
                        )
                with db:
                    db.execute(
                        "INSERT INTO copies VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET sequence=MAX(copies.sequence,excluded.sequence)",
                        (copy["id"], path, copy["sequence"]),
                    )
                if args.repository:
                    print(f"已登记并绑定仓库 {args.repository}：", path)
                elif copy.get("repository_id"):
                    # Re-registering an already-bound copy without --repository:
                    # the server kept the existing binding, so report it truthfully
                    # instead of claiming the copy is uncategorized.
                    print(f"已登记（保持现有仓库关联 {copy['repository_id']}）：", path)
                else:
                    print("已登记（未归类，可在网页关联仓库）：", path)
            else:
                while True:
                    code = run_scan(db)
                    if not args.watch:
                        return code
                    time.sleep(args.watch)
        return 0
    except (ValueError, ScanError, OSError, sqlite3.Error) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
