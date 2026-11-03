"""Development runner: serve the backend and restart it when Python files change.

Use this instead of ``uvicorn --reload`` when the server has no console (IDE panels, background
launches). On Windows, uvicorn's reloader stops its worker with CTRL_C_EVENT and then waits
without a timeout; that event only reaches processes sharing a console, so a headless server
hangs on the first file change. This runner ends the worker directly.

Always binds to 127.0.0.1.

    .venv/Scripts/python scripts/dev_backend.py [--port 8000]
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parent.parent
WATCHED_DIRS = [ROOT / "backend", ROOT / "schemas"]
WATCHED_FILES = [ROOT / ".env"]
POLL_SECONDS = 1.0


def snapshot() -> Dict[Path, int]:
    files = [f for d in WATCHED_DIRS for f in d.rglob("*.py")] + [f for f in WATCHED_FILES if f.exists()]
    seen: Dict[Path, int] = {}
    for f in files:
        try:
            seen[f] = f.stat().st_mtime_ns
        except OSError:
            pass  # removed between listing and stat; the next poll notices
    return seen


def start(port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.friday.api.app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
    )


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        # /T also ends the real interpreter that the venv launcher starts as a child.
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.terminate()
    proc.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8000)
    port = parser.parse_args().port

    seen = snapshot()
    proc = start(port)
    try:
        while True:
            time.sleep(POLL_SECONDS)
            current = snapshot()
            if current == seen:
                continue
            time.sleep(0.3)  # let a multi-file save finish
            seen = snapshot()
            print("[dev_backend] Files changed; restarting the server.", flush=True)
            stop(proc)
            proc = start(port)
    except KeyboardInterrupt:
        pass
    finally:
        stop(proc)


if __name__ == "__main__":
    main()
