"""Launch instructions reach a local-only synthetic server on supported hosts."""

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def test_demo_launcher_local_health_or_native_fail_closed(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    root = tmp_path / "synthetic-demo"
    command = [
        sys.executable,
        str(repo / "tools/run_work_intake_demo.py"),
        "--data-dir",
        str(root),
        "--initialise",
    ]
    if sys.platform != "linux":
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        assert result.returncode == 2
        assert "requires Linux or WSL" in result.stderr
        assert not root.exists()
        return
    tmp_path.chmod(0o700)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    command += ["--port", str(port)]
    log_path = tmp_path / "synthetic-launch.log"
    with log_path.open("wb") as output:
        process = subprocess.Popen(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            cwd=repo,
            env=os.environ.copy(),
        )
        try:
            ready = False
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/_stcore/health", timeout=1
                    ) as response:
                        ready = response.status == 200 and response.read(16) == b"ok"
                    if ready:
                        break
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(0.05)
            assert ready, log_path.read_text(encoding="utf-8")[-4000:]
            assert (root / "requests.db").is_file()
            assert (root / "attachments").is_dir()
            assert (root / "synthetic-sync").is_dir()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
