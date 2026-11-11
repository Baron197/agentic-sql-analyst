"""Run the API and the web app together for a local demo: `uv run poe demo`.

Starts `uvicorn` on 127.0.0.1:8000 and the Vite dev server on 127.0.0.1:5173 (which proxies
`/api` to the API), and stops both on Ctrl+C or when either one exits.
"""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

API = [
    sys.executable,
    "-m",
    "uvicorn",
    "sql_analyst.api.main:create_app",
    "--factory",
    "--host",
    "127.0.0.1",
    "--port",
    "8000",
]
WEB_URL = "http://127.0.0.1:5173"


def stop(proc: subprocess.Popen) -> None:
    """Stop a process and its children (npm starts Vite as a child process)."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
    else:
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    root = Path.cwd()
    if not (root / "web" / "node_modules").is_dir():
        print("The web app isn't installed yet: run `uv run poe web-install` first.")
        return 1
    npm = shutil.which("npm")
    if npm is None:
        print("npm not found: install Node.js LTS (https://nodejs.org/).")
        return 1
    env = {**os.environ, "HF_HUB_DISABLE_SYMLINKS_WARNING": "1"}
    group = {} if os.name == "nt" else {"start_new_session": True}
    procs = [
        subprocess.Popen(API, env=env, **group),
        subprocess.Popen([npm, "--prefix", "web", "run", "dev"], env=env, **group),
    ]
    print(f"\nStarting the API and the web app. Open {WEB_URL} (Ctrl+C stops both).\n")
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            stop(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
