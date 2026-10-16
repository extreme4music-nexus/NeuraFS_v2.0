"""NeuraFS Web UI Process Manager for CLI."""

import json
import os
import sys
import time
import subprocess
import psutil
from pathlib import Path
from urllib.request import urlopen

WEB_DIR = os.path.dirname(os.path.abspath(__file__))
APP_JS = os.path.join(WEB_DIR, "app.js")
WEB_START_TIMEOUT = 10.0


def _health_url(host: str, port: int) -> str:
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    if ":" in probe_host and not probe_host.startswith("["):
        probe_host = f"[{probe_host}]"
    return f"http://{probe_host}:{port}/health"


def _web_endpoint_is_ready(host: str, port: int) -> bool:
    try:
        with urlopen(_health_url(host, port), timeout=0.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status == 200 and payload.get("service") == "neurafs-web"
    except Exception:
        return False


def _read_web_log_tail(log_file: Path) -> str:
    try:
        return "".join(log_file.read_text(encoding="utf-8", errors="replace").splitlines(True)[-20:]).strip()
    except OSError:
        return ""


def _wait_for_web_ready(proc, host: str, port: int, log_file: Path | None = None) -> None:
    deadline = time.monotonic() + WEB_START_TIMEOUT
    while True:
        exit_code = proc.poll()
        if exit_code is not None:
            detail = _read_web_log_tail(log_file) if log_file else ""
            message = f"Web process exited before its health endpoint became ready (exit code {exit_code})"
            if detail:
                message += f":\n{detail}"
            raise RuntimeError(message)
        if _web_endpoint_is_ready(host, port):
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Web health endpoint did not respond within {WEB_START_TIMEOUT:g} seconds")
        time.sleep(0.2)


def _terminate_started_process(proc) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3.0)


class WebManager:
    """Manages lifecycle states and PID tracking of the Node.js Web UI server."""

    @staticmethod
    def get_pid_file() -> Path:
        """Returns PID file path inside central ~/.neurafs/run/ directory."""
        run_dir = Path.home() / ".neurafs" / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir / "neurafs_web.pid"

    @classmethod
    def get_running_pid(cls) -> int | None:
        """Reads active PID from disk if process is alive."""
        pid_file = cls.get_pid_file()
        if not pid_file.exists():
            return None
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    return pid
        except (ValueError, psutil.NoSuchProcess, PermissionError):
            pass

        cls.clear_pid()
        return None

    @classmethod
    def write_pid(cls, pid: int) -> None:
        """Persists process ID to execution storage."""
        pid_file = cls.get_pid_file()
        with open(pid_file, "w", encoding="utf-8") as f:
            f.write(str(pid))

    @classmethod
    def clear_pid(cls) -> None:
        """Removes PID tracking file."""
        pid_file = cls.get_pid_file()
        if pid_file.exists():
            try:
                pid_file.unlink()
            except OSError:
                pass


def start_web(host: str = "127.0.0.1", port: int = 3000, daemon: bool = False) -> None:
    """Starts the Node.js Web UI server and confirms its health endpoint."""
    active_pid = WebManager.get_running_pid()
    if active_pid:
        if _web_endpoint_is_ready(host, port):
            print(f"[NeuraFS Web] Web server is already running (PID: {active_pid}).")
            return
        raise RuntimeError(
            f"Web process {active_pid} is tracked but http://{host}:{port}/health is not responding."
        )

    if not os.path.exists(APP_JS):
        raise FileNotFoundError(f"NeuraFS Web app.js not found at {APP_JS}")

    env = os.environ.copy()
    env["HOST"] = host
    env["PORT"] = str(port)
    cmd = ["node", APP_JS]

    if daemon:
        from neurafs.utils.process import spawn_silent_daemon

        log_file = Path.home() / ".neurafs" / "logs" / "web.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        proc = None
        try:
            with log_file.open("a", encoding="utf-8") as log_stream:
                proc = spawn_silent_daemon(
                    cmd,
                    cwd=WEB_DIR,
                    env=env,
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                )
            _wait_for_web_ready(proc, host, port, log_file)
            WebManager.write_pid(proc.pid)
        except Exception as err:
            _terminate_started_process(proc)
            WebManager.clear_pid()
            raise RuntimeError(
                f"Background web server failed to start. Log: {log_file}. {err}"
            ) from err

        print(f"[NeuraFS Web] Background server ready on http://{host}:{port} (PID: {proc.pid})")
        return

    print(f"[NeuraFS Web] Starting server on http://{host}:{port}...")
    proc = None
    try:
        proc = subprocess.Popen(cmd, cwd=WEB_DIR, env=env)
        _wait_for_web_ready(proc, host, port)
        WebManager.write_pid(proc.pid)
        print(f"[NeuraFS Web] Server ready on http://{host}:{port} (PID: {proc.pid})")
        exit_code = proc.wait()
        raise RuntimeError(f"Web process exited unexpectedly with code {exit_code}.")
    except KeyboardInterrupt:
        print("\n[NeuraFS Web] Stopping server...")
        _terminate_started_process(proc)
    except Exception:
        _terminate_started_process(proc)
        raise
    finally:
        WebManager.clear_pid()


def stop_web() -> bool:
    """Stops the active Web UI process."""
    pid = WebManager.get_running_pid()
    if not pid:
        print("[NeuraFS Web] No active Web server process found.")
        return False

    print(f"[NeuraFS Web] Terminating process (PID: {pid})...")
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)

        for child in children:
            child.terminate()
        parent.terminate()

        _, alive = psutil.wait_procs(children + [parent], timeout=3.0)
        for p in alive:
            p.kill()

        WebManager.clear_pid()
        print("[NeuraFS Web] Server stopped successfully.")
        return True
    except psutil.NoSuchProcess:
        WebManager.clear_pid()
        print("[NeuraFS Web] Process already dead. Cleaned up PID file.")
        return True
    except Exception as err:
        print(f"[NeuraFS Web] Error terminating process: {err}")
        return False


def restart_web(port: int = 3000, daemon: bool = False) -> None:
    """Restarts the NeuraFS Web UI server."""
    print("[NeuraFS Web] Initiating restart sequence...")
    stop_web()
    time.sleep(1.0)
    start_web(port=port, daemon=daemon)


def status_web() -> None:
    """Prints current runtime status of the NeuraFS Web UI server."""
    pid = WebManager.get_running_pid()
    if not pid:
        print("[NeuraFS Web Status] Status: STOPPED (No active process)")
        return

    try:
        proc = psutil.Process(pid)
        mem_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
        cpu_pct = proc.cpu_percent(interval=0.1)
        uptime = round(time.time() - proc.create_time(), 1)

        print("\n[NeuraFS Web Status] Status: RUNNING [OK]")
        print(f" • PID        : {pid}")
        print(f" • RAM Usage  : {mem_mb} MB")
        print(f" • CPU Usage  : {cpu_pct}%")
        print(f" • Uptime     : {uptime}s\n")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        print("[NeuraFS Web Status] Status: UNKNOWN (PID file exists but process unresponsive)")