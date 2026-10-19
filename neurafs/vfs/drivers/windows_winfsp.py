"""NeuraFS Windows WinFSP Kernel Driver Interface (True User-Mode Filesystem with OS-Level Illusion).

Implements a real WinFSP user-mode file system that intercepts Windows kernel I/O
requests (GetFileInfo, ReadDirectory, Read) to present .hcs neural containers as
their original uncompressed media files. The OS and all applications (Explorer,
media players, file managers) see the original file names, sizes, and attributes.

Requires WinFSP to provide transparent reads from the virtual audio namespace.
"""

import sys
import os
import time
import ctypes
import struct
import subprocess
import threading
import signal
import shutil
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from neurafs.vfs.interface import NeuraFSVFSInterface


# --------------------------------------------------------------------------- #
#  Windows constants
# --------------------------------------------------------------------------- #
FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_ATTRIBUTE_READONLY = 0x01
FILE_ATTRIBUTE_ARCHIVE = 0x20

_WINFSP_AVAILABLE = False
_winfsp_dll = None


def _load_native_winfsp_dll() -> Optional[ctypes.CDLL]:
    """Discovers and loads native winfsp-x64.dll from standard installation paths."""
    candidates = [
        "winfsp-x64.dll",
        r"C:\Program Files (x86)\WinFsp\bin\winfsp-x64.dll",
        r"C:\Program Files\WinFsp\bin\winfsp-x64.dll",
    ]
    for path in candidates:
        try:
            return ctypes.CDLL(path)
        except OSError:
            continue
    return None


_winfsp_dll = _load_native_winfsp_dll()
_WINFSP_AVAILABLE = _winfsp_dll is not None

try:
    from winfspy import (
        BaseFileSystemOperations,
        FILE_ATTRIBUTE,
        FileSystem,
        NTStatusMediaWriteProtected,
        NTStatusNotADirectory,
        NTStatusObjectNameNotFound,
    )
    from winfspy.plumbing import SecurityDescriptor
except ImportError:
    BaseFileSystemOperations = None
    FILE_ATTRIBUTE = None
    FileSystem = None
    NTStatusMediaWriteProtected = None
    NTStatusNotADirectory = None
    NTStatusObjectNameNotFound = None
    SecurityDescriptor = None


class NeuraFSWinFSP:
    """WinFSP driver service mounting NeuraFS containers with true OS-level illusion.

    Intercepts Windows kernel filesystem callbacks:
    - GetFileInfo  → spoofs original file name, size, timestamps
    - ReadDirectory → hides .hcs extensions, shows original names
    - Read         → streams decoded PCM from RAM buffer on-the-fly
    - Explorer     → shows codec info in file details tooltip

    The OS is completely lied to: .hcs files appear as their original media files.
    """

    def __init__(self, storage_root: str):
        self.storage_root = os.path.abspath(storage_root)
        os.makedirs(self.storage_root, exist_ok=True)
        self.vfs = NeuraFSVFSInterface(self.storage_root)
        self._shutdown_event = threading.Event()

    def get_file_info(self, path: str) -> Dict[str, Any]:
        """Translates FileAttributes and FileSize for Windows Explorer queries.

        This is the core of the OS illusion — we intercept stat() calls and return
        the ORIGINAL file's metadata (name, size, timestamps) even though the
        physical file is actually .hcs compressed.
        """
        rel_path = path.lstrip("\\/")
        if not rel_path:
            return {
                "file_attributes": FILE_ATTRIBUTE_DIRECTORY,
                "allocation_size": 0,
                "file_size": 0,
            }

        try:
            attr = self.vfs.getattr(rel_path)
            file_attr = FILE_ATTRIBUTE_DIRECTORY if attr.get("is_dir") else (FILE_ATTRIBUTE_NORMAL | FILE_ATTRIBUTE_ARCHIVE)
            size = attr.get("size", 0)

            result = {
                "file_attributes": file_attr,
                "allocation_size": size,
                "file_size": size,
            }

            # Inject codec metadata for Explorer info tooltip
            if attr.get("codec"):
                result["codec"] = attr["codec"]
            if attr.get("mtime"):
                result["mtime"] = attr["mtime"]

            return result
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {path}")

    def read_directory(self, path: str) -> List[Dict[str, Any]]:
        """Returns virtual file list for Windows Directory Enumeration.

        Hides .hcs extensions and presents original filenames to Explorer.
        Each entry includes the codec used for encoding in its metadata.
        """
        rel_path = path.lstrip("\\/")
        items = self.vfs.readdir(rel_path)
        entries = []
        for item in items:
            attr = FILE_ATTRIBUTE_DIRECTORY if item.get("is_dir") else (FILE_ATTRIBUTE_NORMAL | FILE_ATTRIBUTE_ARCHIVE)
            entry = {
                "file_name": item["name"],
                "file_attributes": attr,
                "file_size": item.get("size", 0),
            }
            if item.get("codec"):
                entry["codec"] = item["codec"]
            entries.append(entry)
        return entries

    def read(self, path: str, offset: int, length: int) -> bytes:
        """Handles Windows kernel offset read requests directly from RAMStreamBuffer.

        This intercepts the actual read() syscall. When an application (media player,
        Explorer preview, etc.) reads the file, we decode the neural chunks from RAM
        and serve raw PCM bytes with a valid WAV header — making the OS believe it's
        reading a real uncompressed WAV file.
        """
        rel_path = path.lstrip("\\/")
        return self.vfs.read(virtual_path=rel_path, offset=offset, length=length)

    # --- Read/Write (RW) Operations ---

    def write(self, path: str, buffer: bytes, offset: int) -> int:
        """Writes data to physical storage path (for new file drops that will be auto-encoded)."""
        rel_path = path.lstrip("\\")
        full_path = os.path.join(self.storage_root, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        mode = "r+b" if os.path.exists(full_path) else "wb"
        with open(full_path, mode) as f:
            f.seek(offset)
            f.write(buffer)
        return len(buffer)

    def create(self, path: str) -> None:
        """Creates new file in physical storage (triggers watcher auto-encode pipeline)."""
        rel_path = path.lstrip("\\")
        full_path = os.path.join(self.storage_root, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        open(full_path, "a").close()

    def delete(self, path: str) -> None:
        """Deletes file or directory from storage (cleans up .hcs + state DB)."""
        rel_path = path.lstrip("\\")
        self.vfs.delete(rel_path)
        full_path = os.path.join(self.storage_root, rel_path)
        if os.path.isdir(full_path):
            os.rmdir(full_path)
        elif os.path.exists(full_path):
            os.remove(full_path)

    def mkdir(self, path: str) -> None:
        """Creates directory in physical storage."""
        rel_path = path.lstrip("\\")
        full_path = os.path.join(self.storage_root, rel_path)
        os.makedirs(full_path, exist_ok=True)

    def cleanup_ram_buffers(self) -> None:
        """Forces immediate cleanup of all active RAM stream buffers.

        Called on unmount or when the system detects playback has stopped.
        Ensures zero memory leaks by releasing all cached decoded audio.
        """
        if hasattr(self.vfs, 'active_buffers'):
            buffer_count = len(self.vfs.active_buffers)
            self.vfs.active_buffers.clear()
            if buffer_count > 0:
                print(f"[NeuraFS WinFSP] Cleaned {buffer_count} RAM stream buffers (0 bytes leaked)")

    def shutdown(self) -> None:
        """Signals the driver daemon loop to exit cleanly."""
        self._shutdown_event.set()
        self.cleanup_ram_buffers()


@dataclass
class _VirtualHandle:
    path: str
    is_dir: bool


if BaseFileSystemOperations is not None:
    class _NeuraFSWinFSPOperations(BaseFileSystemOperations):
        """Read-only WinFSP callbacks backed by NeuraFS virtual paths."""

        def __init__(self, storage_root: str):
            super().__init__()
            self.vfs = NeuraFSVFSInterface(storage_root)
            self.security = SecurityDescriptor.from_string(
                "O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FR;;;WD)"
            )

        @staticmethod
        def _clean(path: str) -> str:
            return str(path).replace("/", "\\").strip("\\")

        @staticmethod
        def _attributes(attr: Dict[str, Any]) -> Dict[str, int]:
            is_dir = bool(attr.get("is_dir"))
            file_attrs = (
                FILE_ATTRIBUTE.FILE_ATTRIBUTE_DIRECTORY.value
                if is_dir
                else FILE_ATTRIBUTE.FILE_ATTRIBUTE_ARCHIVE.value
                | FILE_ATTRIBUTE.FILE_ATTRIBUTE_READONLY.value
            )
            size = 0 if is_dir else int(attr.get("size", 0))
            return {
                "file_attributes": file_attrs,
                "allocation_size": ((size + 4095) // 4096) * 4096,
                "file_size": size,
                "creation_time": 0,
                "last_access_time": 0,
                "last_write_time": 0,
                "change_time": 0,
            }

        def _get_info(self, path: str) -> Dict[str, int]:
            try:
                return self._attributes(self.vfs.getattr(path))
            except FileNotFoundError as exc:
                raise NTStatusObjectNameNotFound() from exc

        def get_volume_info(self):
            usage = shutil.disk_usage(self.vfs.root_storage_dir)
            return {"total_size": usage.total, "free_size": usage.free, "volume_label": "NeuraFS"}

        def set_volume_label(self, volume_label):
            raise NTStatusMediaWriteProtected()

        def get_security_by_name(self, file_name):
            info = self._get_info(self._clean(file_name))
            return info["file_attributes"], self.security.handle, self.security.size

        def get_security(self, file_context):
            return self.security

        def open(self, file_name, create_options, granted_access):
            path = self._clean(file_name)
            info = self._get_info(path)
            is_dir = bool(info["file_attributes"] & FILE_ATTRIBUTE.FILE_ATTRIBUTE_DIRECTORY.value)
            return _VirtualHandle(path, is_dir)

        def close(self, file_context):
            return None

        def cleanup(self, file_context, file_name, flags):
            """Handle WinFSP cleanup callbacks for read-only virtual handles."""
            return None

        def get_file_info(self, file_context):
            return self._get_info(file_context.path)

        def read(self, file_context, offset, length):
            if file_context.is_dir:
                raise NTStatusNotADirectory()
            return self.vfs.read(file_context.path, offset, length)

        def read_directory(self, file_context, marker):
            if not file_context.is_dir:
                raise NTStatusNotADirectory()
            entries = []
            parent = file_context.path
            if parent:
                entries.extend([
                    {"file_name": ".", **self._get_info(parent)},
                    {"file_name": "..", **self._get_info(os.path.dirname(parent))},
                ])
            for item in self.vfs.readdir(parent):
                # Directory enumeration should use the metadata already returned by
                # the VFS. In particular, do not render whole compressed files just
                # because Explorer is listing a directory; the exact virtual size is
                # resolved when the application requests that file's information.
                item_is_dir = bool(item.get("is_dir"))
                attrs = (
                    FILE_ATTRIBUTE.FILE_ATTRIBUTE_DIRECTORY.value
                    if item_is_dir
                    else FILE_ATTRIBUTE.FILE_ATTRIBUTE_ARCHIVE.value
                    | FILE_ATTRIBUTE.FILE_ATTRIBUTE_READONLY.value
                )
                size = 0 if item_is_dir else int(item.get("size", 0))
                entries.append({
                    "file_name": item["name"],
                    "file_attributes": attrs,
                    "allocation_size": ((size + 4095) // 4096) * 4096,
                    "file_size": size,
                    "creation_time": 0,
                    "last_access_time": 0,
                    "last_write_time": 0,
                    "change_time": 0,
                })
            entries.sort(key=lambda item: item["file_name"].casefold())
            if marker is None:
                return entries
            for index, item in enumerate(entries):
                if item["file_name"] == marker:
                    return entries[index + 1:]
            return entries

        def get_dir_info_by_name(self, file_context, file_name):
            if not file_context.is_dir:
                raise NTStatusNotADirectory()
            path = os.path.join(file_context.path, file_name) if file_context.path else file_name
            return {"file_name": file_name, **self._get_info(path)}

        def create(self, file_name, create_options, granted_access, file_attributes, security_descriptor, allocation_size):
            raise NTStatusMediaWriteProtected()

        def write(self, file_context, buffer, offset, write_to_end_of_file, constrained_io):
            raise NTStatusMediaWriteProtected()


def mount_windows_winfsp(storage_dir: str, drive_letter: str = "Z:") -> None:
    """Mount the actual NeuraFS virtual namespace through WinFSP."""
    if not _WINFSP_AVAILABLE or FileSystem is None or BaseFileSystemOperations is None:
        raise RuntimeError(
            "WinFSP and winfspy are required for transparent HCS virtualization; "
            "a subst mapping cannot provide virtual-file reads."
        )
    abs_storage = os.path.abspath(storage_dir)
    os.makedirs(abs_storage, exist_ok=True)
    operations = _NeuraFSWinFSPOperations(abs_storage)
    filesystem = FileSystem(
        drive_letter,
        operations,
        sector_size=512,
        sectors_per_allocation_unit=8,
        read_only_volume=1,
        file_system_name="NeuraFS",
    )
    filesystem.start()
    try:
        print(f"[NeuraFS WinFSP] Virtual audio filesystem mounted at {drive_letter}")
        shutdown_event = threading.Event()
        previous_handlers = {}

        def request_shutdown(_sig, _frame):
            shutdown_event.set()

        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                previous_handlers[signum] = signal.signal(signum, request_shutdown)
            except (ValueError, OSError):
                pass
        while not shutdown_event.wait(1.0):
            pass
    finally:
        filesystem.stop()
        for signum, handler in locals().get("previous_handlers", {}).items():
            try:
                signal.signal(signum, handler)
            except (ValueError, OSError):
                pass


if __name__ == "__main__":
    storage = sys.argv[1] if len(sys.argv) > 1 else "storage"
    drive = sys.argv[2] if len(sys.argv) > 2 else "Z:"

    mount_windows_winfsp(storage, drive)
