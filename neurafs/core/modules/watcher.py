"""NeuraFS Storage File System Watcher Daemon Module."""

import os
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path
from typing import Optional, Callable, Any

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


PID_FILE = Path.home() / ".neurafs" / "watcher.pid"


class StorageEventHandler(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """Intercepts file system creation and modification events with strict noise filtering."""

    IGNORED_EXTENSIONS = {".tmp", ".part", ".crdownload", ".hcs", ".sys", ".lnk", ".bak"}
    IGNORED_FILES = {"desktop.ini", ".ds_store", "thumbs.db"}

    def __init__(self, callback: Optional[Callable[[str], None]] = None):
        super().__init__()
        self.callback = callback
        self._active_jobs = set()

    def _is_ignored(self, file_path: str) -> bool:
        path = Path(file_path)
        if path.is_dir():
            return True
        if ".temp" in path.parts:
            return True
        if path.name.lower() in self.IGNORED_FILES or path.name.startswith("~$"):
            return True
        if path.suffix.lower() in self.IGNORED_EXTENSIONS:
            return True
        return False

    def _wait_until_settled(self, file_path: str, timeout: int = 30) -> bool:
        """Ensures file copying is fully finished and file lock is released by OS."""
        if not os.path.exists(file_path):
            return False

        start_time = time.time()
        last_size = -1

        while time.time() - start_time < timeout:
            try:
                current_size = os.path.getsize(file_path)
                with open(file_path, "rb"):
                    pass
                if current_size == last_size and current_size > 0:
                    return True
                last_size = current_size
            except (OSError, PermissionError):
                pass
            time.sleep(1)
        return False

    def _handle_event(self, file_path: str):
        if self._is_ignored(file_path):
            return

        if file_path in self._active_jobs:
            return

        def process():
            self._active_jobs.add(file_path)
            if self._wait_until_settled(file_path):
                from neurafs.core.modules.queue_manager import QueueManager
                QueueManager.add_or_update_job(file_path)
            self._active_jobs.discard(file_path)

        threading.Thread(target=process, daemon=True).start()

    def on_deleted(self, event):
        if not event.is_directory:
            from neurafs.core.modules.queue_manager import QueueManager
            QueueManager.handle_file_deleted(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._handle_event(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._handle_event(event.src_path)


class NeuraFSWatcher:
    """Background Daemon Manager for Watcher process."""

    @classmethod
    def _get_pid(cls) -> Optional[int]:
        if PID_FILE.exists():
            try:
                return int(PID_FILE.read_text().strip())
            except ValueError:
                pass
        return None

    @classmethod
    def is_active(cls) -> bool:
        """Checks if background Watcher daemon process is alive."""
        pid = cls._get_pid()
        if not pid:
            return False
        if PSUTIL_AVAILABLE:
            return psutil.pid_exists(pid)
        try:
            if sys.platform == "win32":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if h:
                    kernel32.CloseHandle(h)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except Exception:
            return False

    @classmethod
    def start_daemon(cls) -> bool:
        """Launches Watcher in a detached background daemon process."""
        if not WATCHDOG_AVAILABLE:
            print("⚠️  [NeuraFS Watcher] 'watchdog' package missing. Run: pip install watchdog")
            return False

        if cls.is_active():
            print("[NeuraFS Watcher] Background daemon already running.")
            return True

        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        python_exe = sys.executable
        cmd = [python_exe, "-m", "neurafs.core.modules.watcher"]

        kwargs = {}
        if sys.platform == "win32":
            CREATE_NO_WINDOW = 0x08000000
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            **kwargs
        )
        PID_FILE.write_text(str(proc.pid))
        print(f"👁️  [NeuraFS Watcher] Launched background watcher daemon (PID: {proc.pid})")
        return True

    @classmethod
    def stop_daemon(cls) -> bool:
        """Stops background Watcher daemon process."""
        pid = cls._get_pid()
        if not pid:
            return True

        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass

        if PID_FILE.exists():
            try:
                os.remove(PID_FILE)
            except OSError:
                pass

        print("👁️  [NeuraFS Watcher] Stopped background watcher daemon.")
        return True

    @classmethod
    @classmethod
    def run_forever(cls):
        """Blocking execution loop meant for detached background daemon process."""
        from neurafs.core.storage import StorageManager
        from neurafs.core.modules.queue_manager import QueueManager

        target_path = StorageManager.get_path()

        if not WATCHDOG_AVAILABLE:
            sys.exit(1)

        if not os.path.exists(target_path):
            os.makedirs(target_path, exist_ok=True)

        # Start Queue Processing Loop
        QueueManager.start_worker()

        event_handler = StorageEventHandler()
        observer = Observer()
        observer.schedule(event_handler, path=target_path, recursive=True)
        observer.start()

        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            observer.stop()
            QueueManager.stop_worker()
        observer.join()


if __name__ == "__main__":
    NeuraFSWatcher.run_forever()