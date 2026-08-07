"""NeuraFS Storage File System Watcher Module."""

import os
import time
import threading
from pathlib import Path
from typing import Optional, Callable, Any

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


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
                    pass  # Attempt exclusive read access
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
                print(f"\n👁️  [NeuraFS Watcher] Detected settled new file: {os.path.basename(file_path)}")
                if self.callback:
                    self.callback(file_path)
            time.sleep(3)
            self._active_jobs.discard(file_path)

        threading.Thread(target=process, daemon=True).start()

    def on_created(self, event):
        if not event.is_directory:
            self._handle_event(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._handle_event(event.src_path)


class NeuraFSWatcher:
    """Background Daemon Observer managing file system monitoring on physical storage."""

    _observer: Optional[Any] = None
    _is_running: bool = False

    @classmethod
    def start(cls, target_path: str, callback: Optional[Callable[[str], None]] = None) -> bool:
        """Starts file system watcher in background thread."""
        if not WATCHDOG_AVAILABLE:
            print("⚠️  [NeuraFS Watcher] 'watchdog' package missing. Run: pip install watchdog")
            return False

        if cls._is_running:
            return True

        if not os.path.exists(target_path):
            os.makedirs(target_path, exist_ok=True)

        event_handler = StorageEventHandler(callback=callback)
        cls._observer = Observer()
        cls._observer.schedule(event_handler, path=target_path, recursive=True)
        cls._observer.start()
        cls._is_running = True
        print(f"👁️  [NeuraFS Watcher] Active & monitoring storage: '{target_path}'")
        return True

    @classmethod
    def stop(cls) -> bool:
        """Stops background file watcher cleanly."""
        if cls._observer and cls._is_running:
            cls._observer.stop()
            cls._observer.join()
            cls._is_running = False
            cls._observer = None
            print("👁️  [NeuraFS Watcher] Stopped background monitoring.")
            return True
        return False

    @classmethod
    def is_active(cls) -> bool:
        """Returns True if background thread observer is alive."""
        return cls._is_running and cls._observer is not None and cls._observer.is_alive()