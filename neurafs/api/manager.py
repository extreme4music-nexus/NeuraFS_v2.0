"""NeuraFS API Lifecycle & Process Manager for CLI."""

import os
import sys
import time
import subprocess
import psutil
import uvicorn
from neurafs.core.storage import StorageManager
from pathlib import Path


class APIManager:
    """Manages lifecycle states and PID tracking of the NeuraFS FastAPI server."""

    @classmethod
    def get_running_pid(cls) -> int | None:
        """Reads active PID from disk if process is alive."""
        pid_file = cls.get_pid_file()
        if not os.path.exists(pid_file):
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

    @staticmethod
    def get_pid_file() -> Path:
        """Returns PID file path inside central ~/.neurafs/run/ directory."""
        run_dir = Path.home() / ".neurafs" / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir / "neurafs_web.pid"

    @classmethod
    def clear_pid(cls) -> None:
        """Removes PID tracking file."""
        pid_file = cls.get_pid_file()
        if os.path.exists(pid_file):
            try:
                os.remove(pid_file)
            except OSError:
                pass


def start_api(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    daemon: bool = False
) -> None:
    """Starts the NeuraFS FastAPI server in foreground or background mode."""
    active_pid = APIManager.get_running_pid()
    if active_pid:
        print(f"[NeuraFS API] Server is already running (PID: {active_pid}).")
        return

    app_module = "neurafs.api.server:app"

    if daemon:
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            app_module,
            "--host",
            host,
            "--port",
            str(port),
        ]
        if reload:
            cmd.append("--reload")

        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        APIManager.write_pid(proc.pid)
        print(f"[NeuraFS API] Background server launched on http://{host}:{port} (PID: {proc.pid})")
    else:
        print(f"[NeuraFS API] Starting server on http://{host}:{port}...")
        uvicorn.run(app_module, host=host, port=port, reload=reload)


def stop_api() -> bool:
    """Stops the active NeuraFS API process and its child workers."""
    pid = APIManager.get_running_pid()
    if not pid:
        print("[NeuraFS API] No active API server process found.")
        return False

    print(f"[NeuraFS API] Terminating server process (PID: {pid})...")
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)

        for child in children:
            child.terminate()
        parent.terminate()

        _, alive = psutil.wait_procs(children + [parent], timeout=3.0)
        for p in alive:
            p.kill()

        APIManager.clear_pid()
        print("[NeuraFS API] Server stopped successfully.")
        return True
    except psutil.NoSuchProcess:
        APIManager.clear_pid()
        print("[NeuraFS API] Process already dead. Cleaned up PID file.")
        return True
    except Exception as err:
        print(f"[NeuraFS API] Error terminating process: {err}")
        return False


def restart_api(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    daemon: bool = False
) -> None:
    """Restarts the NeuraFS FastAPI server instance."""
    print("[NeuraFS API] Initiating restart sequence...")
    stop_api()
    time.sleep(1.0)
    start_api(host=host, port=port, reload=reload, daemon=daemon)


def status_api() -> None:
    """Prints current runtime status of the NeuraFS API server."""
    pid = APIManager.get_running_pid()
    if not pid:
        print("[NeuraFS API Status] Status: STOPPED (No active process)")
        return

    try:
        proc = psutil.Process(pid)
        mem_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
        cpu_pct = proc.cpu_percent(interval=0.1)
        uptime = round(time.time() - proc.create_time(), 1)

        print("\n[NeuraFS API Status] Status: RUNNING ✅")
        print(f" • PID        : {pid}")
        print(f" • RAM Usage  : {mem_mb} MB")
        print(f" • CPU Usage  : {cpu_pct}%")
        print(f" • Uptime     : {uptime}s\n")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        print("[NeuraFS API Status] Status: UNKNOWN (PID file exists but process unresponsive)")