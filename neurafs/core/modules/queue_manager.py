"""NeuraFS Async Queue Manager & Dynamic Lifecycle Module."""

import os
import sys
import stat
import time
import lzma
import hashlib
import subprocess
import threading
from typing import Dict, Any, Optional

from neurafs.core.modules.classifier import MediaClassifier
from neurafs.core.modules.activity_logger import ActivityLogger
from neurafs.sdk.python.sdk import NeuraFSSDK
from neurafs.core.modules.state_db import StateManager


class QueueManager:
    """Manages processing queue, file locking, event handling, and conditional OS alerts."""

    _queue: Dict[str, Dict[str, Any]] = {}
    _lock = threading.Lock()
    _worker_thread: Optional[threading.Thread] = None
    _is_running = False

    @classmethod
    def start_worker(cls):
        """Starts the background queue processing worker thread."""
        if cls._is_running:
            return
        cls._is_running = True
        cls._worker_thread = threading.Thread(target=cls._worker_loop, daemon=True)
        cls._worker_thread.start()

    @classmethod
    def stop_worker(cls):
        """Stops the queue worker thread."""
        cls._is_running = False

    @classmethod
    def add_or_update_job(cls, file_path: str):
        """Adds a new file or updates hash if file was modified before processing."""
        if not os.path.exists(file_path):
            return

        abs_path = os.path.abspath(file_path)
        file_name = os.path.basename(abs_path)
        file_hash = cls._get_quick_hash(abs_path)

        with cls._lock:
            if abs_path in cls._queue:
                job = cls._queue[abs_path]
                if job["status"] == "PENDING":
                    if job["hash"] != file_hash:
                        job["hash"] = file_hash
                        job["updated_at"] = time.time()
                        StateManager.update_status(abs_path, status="QUEUED")
                        ActivityLogger.log("QUEUE_UPDATED", f"Updated file buffer in queue: {file_name}")
                    return
                elif job["status"] == "PROCESSING":
                    return

            is_audio = MediaClassifier.is_neural_audio(abs_path)
            file_type = "AUDIO_NEURAL" if is_audio else "STANDARD_DATA"
            StateManager.register_file(abs_path, file_type=file_type, status="QUEUED")

            cls._queue[abs_path] = {
                "path": abs_path,
                "file_name": file_name,
                "status": "PENDING",
                "hash": file_hash,
                "added_at": time.time(),
                "is_audio": is_audio
            }
            ActivityLogger.log("QUEUED", f"Added file to queue: {file_name}")

    @classmethod
    def handle_file_deleted(cls, file_path: str):
        """Handles user file deletion based on current processing status."""
        abs_path = os.path.abspath(file_path)
        file_name = os.path.basename(abs_path)

        with cls._lock:
            if abs_path not in cls._queue:
                return

            status = cls._queue[abs_path]["status"]

            if status == "PENDING":
                del cls._queue[abs_path]
                StateManager.update_status(abs_path, status="DELETED")
                ActivityLogger.log("CANCELLED", f"Removed from queue (deleted by user): {file_name}")

            elif status == "PROCESSING":
                ActivityLogger.log("PROTECTED", f"User attempted deletion during conversion: {file_name}")
                cls._trigger_os_alert(
                    "NeuraFS Action Blocked",
                    f"File '{file_name}' is currently converting and cannot be deleted right now."
                )

    @classmethod
    def get_status_summary(cls) -> Dict[str, int]:
        """Returns counts of pending and active processing jobs directly from persistent SQLite DB."""
        try:
            return StateManager.get_queue_metrics()
        except Exception:
            with cls._lock:
                pending = sum(1 for j in cls._queue.values() if j["status"] == "PENDING")
                processing = sum(1 for j in cls._queue.values() if j["status"] == "PROCESSING")
                return {"pending": pending, "processing": processing}

    @classmethod
    def _worker_loop(cls):
        """Processes queued jobs sequentially."""
        while cls._is_running:
            target_job = None

            with cls._lock:
                for path, job in cls._queue.items():
                    if job["status"] == "PENDING":
                        job["status"] = "PROCESSING"
                        target_job = job
                        break

            if target_job:
                cls._process_job(target_job)
            else:
                time.sleep(1)

    @classmethod
    def _process_job(cls, job: Dict[str, Any]):
        file_path = job["path"]
        file_name = job["file_name"]
        is_audio = job["is_audio"]

        # Apply Lazy Read-Only Lock & Update State DB
        cls._set_readonly(file_path, True)
        StateManager.update_status(file_path, status="PROCESSING")
        ActivityLogger.log("PROCESSING", f"Started conversion: {file_name}")

        try:
            output_hcs = f"{file_path}.hcs"
            if is_audio:
                # FastAPI / SDK Neural Encoding
                NeuraFSSDK.encode_file(file_path, output_hcs)
            else:
                # Fast LZMA Compression for general data files
                cls._lzma_pack(file_path, output_hcs)

            StateManager.update_status(file_path, status="COMPLETED_HCS", hcs_path=output_hcs)
            ActivityLogger.log("COMPLETED", f"Successfully converted to container: {os.path.basename(output_hcs)}")

        except Exception as err:
            StateManager.update_status(file_path, status="ERROR")
            ActivityLogger.log("ERROR", f"Conversion failed for {file_name}: {err}")

        finally:
            # Unlock file and remove job
            cls._set_readonly(file_path, False)
            with cls._lock:
                cls._queue.pop(file_path, None)

    @classmethod
    def _set_readonly(cls, file_path: str, readonly: bool):
        """Toggles Read-Only OS file attribute."""
        if not os.path.exists(file_path):
            return
        try:
            if sys.platform == "win32":
                import ctypes
                FILE_ATTRIBUTE_READONLY = 0x1
                attrs = ctypes.windll.kernel32.GetFileAttributesW(file_path)
                if attrs != -1:
                    if readonly:
                        new_attrs = attrs | FILE_ATTRIBUTE_READONLY
                    else:
                        new_attrs = attrs & ~FILE_ATTRIBUTE_READONLY
                    ctypes.windll.kernel32.SetFileAttributesW(file_path, new_attrs)
            else:
                mode = os.stat(file_path).st_mode
                if readonly:
                    os.chmod(file_path, mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
                else:
                    os.chmod(file_path, mode | stat.S_IWUSR)
        except Exception:
            pass

    @classmethod
    def _trigger_os_alert(cls, title: str, message: str):
        """Displays OS notification silently without flashing CMD windows."""
        try:
            if sys.platform == "win32":
                CREATE_NO_WINDOW = 0x08000000
                ps_cmd = (
                    f'[reflection.assembly]::loadwithpartialname("System.Windows.Forms");'
                    f'[System.Windows.Forms.MessageBox]::Show("{message}", "{title}", 0, 48)'
                )
                subprocess.Popen(
                    ["powershell", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW
                )
            else:
                subprocess.run(["notify-send", title, message], check=False)
        except Exception:
            pass

    @classmethod
    def _lzma_pack(cls, input_path: str, output_path: str):
        """Packs standard files into standard compressed HCS containers."""
        with open(input_path, "rb") as f_in, lzma.open(output_path, "wb") as f_out:
            f_out.write(f_in.read())

    @classmethod
    def _get_quick_hash(cls, file_path: str) -> str:
        try:
            size = os.path.getsize(file_path)
            return f"{size}_{os.path.getmtime(file_path)}"
        except Exception:
            return ""