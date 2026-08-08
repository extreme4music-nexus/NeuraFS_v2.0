"""NeuraFS Web UI Process Manager for CLI."""

import os
import sys
import time
import subprocess
import psutil
from pathlib import Path

WEB_DIR = os.path.dirname(os.path.abspath(__file__))
APP_JS = os.path.join(WEB_DIR, "app.js")


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
    """Starts the Node.js Web UI server."""
    active_pid = WebManager.get_running_pid()
    if active_pid:
        print(f"[NeuraFS Web] Web server is already running (PID: {active_pid}).")
        return

    if not os.path.exists(APP_JS):
        print(f"[NeuraFS Web Error] app.js not found at {APP_JS}")
        return

    env = os.environ.copy()
    env["HOST"] = host
    env["PORT"] = str(port)

    cmd = ["node", APP_JS]
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0

    if daemon:
        proc = subprocess.Popen(
            cmd,
            cwd=WEB_DIR,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        WebManager.write_pid(proc.pid)
        print(f"[NeuraFS Web] Background server launched on http://{host}:{port} (PID: {proc.pid})")
    else:
        print(f"[NeuraFS Web] Starting server on http://{host}:{port}...")
        try:
            proc = subprocess.Popen(cmd, cwd=WEB_DIR, env=env)
            WebManager.write_pid(proc.pid)
            proc.wait()
        except KeyboardInterrupt:
            print("\n[NeuraFS Web] Stopping server...")
            proc.terminate()
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

        print("\n[NeuraFS Web Status] Status: RUNNING ✅")
        print(f" • PID        : {pid}")
        print(f" • RAM Usage  : {mem_mb} MB")
        print(f" • CPU Usage  : {cpu_pct}%")
        print(f" • Uptime     : {uptime}s\n")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        print("[NeuraFS Web Status] Status: UNKNOWN (PID file exists but process unresponsive)")