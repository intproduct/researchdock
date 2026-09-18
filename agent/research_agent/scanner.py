import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class ScanError(Exception):
    pass


def git(path: Path, *args: str, allow_fail: bool = False, raw: bool = False) -> str:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    # Never use shell=True, execute hooks, run network commands or lock the index.
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(path), *args],
            env=env,
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScanError("Git 不可用或扫描超时") from exc
    if result.returncode and not allow_fail:
        # Git stderr may contain credential-bearing URLs; don't forward it.
        raise ScanError("Git 读取失败：请确认目录可信、可读且是有效仓库")
    return (result.stdout if raw else result.stdout.strip()) if result.returncode == 0 else ""


def redact_remote(value: str) -> str | None:
    if not value:
        return None
    if "://" in value:
        try:
            parsed = urlsplit(value)
            host = parsed.hostname or ""
            if ":" in host:
                host = f"[{host}]"
            if parsed.port:
                host += f":{parsed.port}"
            return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
        except ValueError:
            return None
    # SCP-style git@host:path URLs: discard username and any accidental suffixes.
    return value.split("@", 1)[-1].split("?", 1)[0].split("#", 1)[0]


def scan(path: str) -> dict:
    root = Path(path).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ScanError("请登记仓库根目录")
    top = git(root, "rev-parse", "--show-toplevel")
    if Path(top).resolve() != root:
        raise ScanError("请登记 Git 仓库根目录，而非子目录")
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", allow_fail=True)
    head = git(root, "rev-parse", "--verify", "HEAD", allow_fail=True)
    upstream = git(
        root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", allow_fail=True
    )
    # -z keeps newline/non-ASCII filenames unambiguous; rename has an extra path.
    entries = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", raw=True)
    changed = untracked = 0
    parts = entries.split("\0")
    i = 0
    while i < len(parts):
        record = parts[i]
        if record:
            if record.startswith("??"):
                untracked += 1
            else:
                changed += 1
            if "R" in record[:2] or "C" in record[:2]:
                i += 1
        i += 1
    remote_name = (
        git(root, "config", "--get", f"branch.{branch}.remote", allow_fail=True) if branch else ""
    )
    remote = git(root, "remote", "get-url", remote_name or "origin", allow_fail=True)
    result = {
        "observed_at": datetime.now(UTC).isoformat(),
        "branch": branch or None,
        "head": head or None,
        "upstream": upstream or None,
        "remote_url": redact_remote(remote),
        "dirty": bool(changed or untracked),
        "changed_files": changed,
        "untracked_files": untracked,
        "ahead": None,
        "behind": None,
        "comparison": "unknown",
        "reason": "未设置跟踪分支",
    }
    if not head:
        result["reason"] = "仓库尚无提交"
    elif not branch:
        result["reason"] = "分离 HEAD；未指定比较基准"
    elif git(root, "rev-parse", "--is-shallow-repository") == "true":
        result["reason"] = "浅克隆，历史不完整"
    elif upstream:
        common = git(root, "merge-base", "HEAD", "@{upstream}", allow_fail=True)
        if not common:
            result.update(comparison="unrelated", reason="与缓存的跟踪分支没有共同祖先")
        else:
            ahead, behind = map(
                int, git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}").split()
            )
            state = (
                "diverged"
                if ahead and behind
                else "ahead"
                if ahead
                else "behind"
                if behind
                else "synced"
            )
            result.update(
                ahead=ahead,
                behind=behind,
                comparison=state,
                reason="仅比较本地缓存的跟踪分支；未联网刷新远端",
            )
    return result
