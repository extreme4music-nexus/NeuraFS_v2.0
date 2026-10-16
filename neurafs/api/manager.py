"""NeuraFS API Lifecycle & Process Manager for CLI."""

import json
import os
import sys
import time
import subprocess
import psutil
import uvicorn
from neurafs.core.storage import StorageManager
from pathlib import Path
from urllib.request import urlopen

API_START_TIMEOUT = 10.0


def _health_url(host: str, port: int) -> str:
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    if ":" in probe_host and not probe_host.startswith("["):
        probe_host = f"[{probe_host}]"
    return f"http://{probe_host}:{port}/health"


def _api_endpoint_is_ready(host: str, port: int) -> bool:
    try:
        with urlopen(_health_url(host, port), timeout=0.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status == 200 and payload.get("status") == "ok"
    except Exception:
        return False


def _read_api_log_tail(log_file: Path) -> str:
    try:
        return "".join(log_file.read_text(encoding="utf-8", errors="replace").splitlines(True)[-20:]).strip()
    except OSError:
        return ""


def _api_listener_pid(port: int) -> int | None:
    """Return a NeuraFS API process already listening on the requested port."""
    try:
        listeners = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, OSError):
        return None

    for connection in listeners:
        if (
            connection.status != psutil.CONN_LISTEN
            or not connection.laddr
            or connection.laddr.port != port
            or connection.pid is None
        ):
            continue
        try:
            process = psutil.Process(connection.pid)
            command = " ".join(process.cmdline()).lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "neurafs.api.server" in command or "_run_api_server" in command or (
            "neurafs.exe" in command and " api start" in command
        ):
            return connection.pid
    return None


def _is_api_process(process) -> bool:
    try:
        command = " ".join(process.cmdline()).lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    return "neurafs.api.server" in command or "_run_api_server" in command or (
        "neurafs.exe" in command and " api start" in command
    )


def _wait_for_api_ready(proc, host: str, port: int, log_file: Path) -> None:
    deadline = time.monotonic() + API_START_TIMEOUT
    while True:
        exit_code = proc.poll()
        if exit_code is not None:
            detail = _read_api_log_tail(log_file)
            message = f"API process exited before its health endpoint became ready (exit code {exit_code})"
            if detail:
                message += f":\n{detail}"
            raise RuntimeError(message)
        if _api_endpoint_is_ready(host, port):
            # A different process may already own the port and answer this
            # probe. Give the newly spawned child time to report bind errors.
            time.sleep(0.25)
            exit_code = proc.poll()
            if exit_code is not None:
                detail = _read_api_log_tail(log_file)
                message = f"API process exited while validating readiness (exit code {exit_code})"
                if detail:
                    message += f":\n{detail}"
                raise RuntimeError(message)
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"API health endpoint did not respond within {API_START_TIMEOUT:g} seconds")
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


class APIManager:
    """Manages lifecycle states and PID tracking of the NeuraFS FastAPI server."""

    @classmethod
    def get_running_pid(cls) -> int | None:
        """Reads active PID from disk if process is alive."""
        pid_file = cls.get_pid_file()
        if not os.path.exists(pid_file):
            pid = _api_listener_pid(8000)
            if pid is not None:
                cls.write_pid(pid)
            return pid
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                if (
                    proc.is_running()
                    and proc.status() != psutil.STATUS_ZOMBIE
                    and _is_api_process(proc)
                ):
                    return pid
        except (ValueError, psutil.NoSuchProcess, PermissionError):
            pass

        cls.clear_pid()
        pid = _api_listener_pid(8000)
        if pid is not None:
            cls.write_pid(pid)
        return pid
    
    @classmethod
    def write_pid(cls, pid: int) -> None:
        """Writes process PID to persistent PID file."""
        pid_file = cls.get_pid_file()
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(pid), encoding="utf-8")

    @staticmethod
    def get_pid_file() -> Path:
        """Returns PID file path inside central ~/.neurafs/run/ directory."""
        run_dir = Path.home() / ".neurafs" / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir / "neurafs_api.pid"

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
        if _api_endpoint_is_ready(host, port):
            print(f"[NeuraFS API] Server is already running (PID: {active_pid}).")
            return
        raise RuntimeError(
            f"API process {active_pid} is tracked but {_health_url(host, port)} is not responding."
        )
    if _api_endpoint_is_ready(host, port):
        listener_pid = _api_listener_pid(port)
        if listener_pid is not None:
            APIManager.write_pid(listener_pid)
            print(f"[NeuraFS API] Server is already running (PID: {listener_pid}).")
            return
        raise RuntimeError(
            f"An API health endpoint is already responding at {_health_url(host, port)}, "
            "but its listener could not be identified safely; refusing to launch a duplicate."
        )

    app_module = "neurafs.api.server:app"

    if daemon:
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "_run_api_server", "--host", host, "--port", str(port)]
        else:
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

        from neurafs.utils.process import spawn_silent_daemon

        log_file = Path.home() / ".neurafs" / "logs" / "api.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        proc = None
        try:
            with log_file.open("a", encoding="utf-8") as log_stream:
                proc = spawn_silent_daemon(
                    cmd,
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                )
            _wait_for_api_ready(proc, host, port, log_file)
            APIManager.write_pid(proc.pid)
        except Exception as err:
            _terminate_started_process(proc)
            APIManager.clear_pid()
            raise RuntimeError(
                f"Background API server failed to start. Log: {log_file}. {err}"
            ) from err

        print(f"[NeuraFS API] Background server ready on http://{host}:{port} (PID: {proc.pid})")
    else:
        print(f"[NeuraFS API] Starting server on http://{host}:{port}...")
        uvicorn.run(app_module, host=host, port=port, reload=reload)


def stop_api() -> bool:
    """Stops the active NeuraFS API process and its child workers."""
    pid = APIManager.get_running_pid()
    if not pid:
        if _api_endpoint_is_ready("127.0.0.1", 8000):
            print("[NeuraFS API] A healthy API is responding but its process could not be identified; leaving it untouched.")
            return False
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
        if _api_endpoint_is_ready("127.0.0.1", 8000):
            print("[NeuraFS API Status] Status: RUNNING (healthy endpoint; process not identified)")
            return
        print("[NeuraFS API Status] Status: STOPPED (No active process)")
        return

    try:
        proc = psutil.Process(pid)
        mem_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
        cpu_pct = proc.cpu_percent(interval=0.1)
        uptime = round(time.time() - proc.create_time(), 1)

        print("\n[NeuraFS API Status] Status: RUNNING [OK]")
        print(f" • PID        : {pid}")
        print(f" • RAM Usage  : {mem_mb} MB")
        print(f" • CPU Usage  : {cpu_pct}%")
        print(f" • Uptime     : {uptime}s\n")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        print("[NeuraFS API Status] Status: UNKNOWN (PID file exists but process unresponsive)")
