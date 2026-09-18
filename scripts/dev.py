"""Start API and frontend together; terminate both process trees on Ctrl+C."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if not (ROOT / ".env").exists():
        raise SystemExit("Run python scripts/setup_local.py first")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise SystemExit("Node.js/npm is required")
    processes = []
    try:
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ],
                cwd=ROOT / "backend",
            )
        )
        processes.append(
            subprocess.Popen([npm, "run", "dev", "--", "--strictPort"], cwd=ROOT / "frontend")
        )
        print(
            "Research Manager: http://localhost:5173  |  API: http://127.0.0.1:8000/docs",
            flush=True,
        )
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for p in processes:
            if p.poll() is None:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(p.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                else:
                    p.terminate()
        for p in processes:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    raise SystemExit(main())
