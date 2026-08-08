"""NeuraFS Windows WinFSP Kernel Driver Interface (Native ctypes DLL implementation - Read/Write)."""

import sys
import os
import time
import ctypes
import subprocess
from typing import Dict, Any, List

from neurafs.vfs.ram_streamer import RAMStreamBuffer
from neurafs.core.container import HCSContainer
from neurafs.vfs.interface import NeuraFSVFSInterface


def _load_native_winfsp_dll() -> ctypes.CDLL:
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


winfsp_dll = _load_native_winfsp_dll()


class NeuraFSWinFSP:
    """WinFSP driver service mounting NeuraFS containers with Full Read/Write (RW) capabilities."""

    def __init__(self, storage_root: str):
        self.storage_root = os.path.abspath(storage_root)
        os.makedirs(self.storage_root, exist_ok=True)
        self.vfs = NeuraFSVFSInterface(self.storage_root)

    def get_file_info(self, path: str) -> Dict[str, Any]:
        """Translates FileAttributes and FileSize for Windows Explorer queries (RW mode)."""
        if path == "\\":
            return {
                "file_attributes": 0x10,  # FILE_ATTRIBUTE_DIRECTORY
                "allocation_size": 0,
                "file_size": 0,
            }

        rel_path = path.lstrip("\\")
        full_path = os.path.join(self.storage_root, rel_path)

        # Virtualize .hcs files as uncompressed .wav files in Explorer
        if rel_path.endswith(".wav") and not os.path.exists(full_path):
            hcs_path = full_path[:-4] + ".hcs"
            if os.path.exists(hcs_path):
                try:
                    with open(hcs_path, "rb") as f:
                        manifest, _ = HCSContainer.unpack(f.read())
                    orig_size = manifest.get("original", {}).get("size", 1024 * 1024)
                    return {
                        "file_attributes": 0x80,  # FILE_ATTRIBUTE_NORMAL (Read/Write)
                        "allocation_size": orig_size,
                        "file_size": orig_size,
                    }
                except Exception:
                    pass

        if os.path.exists(full_path):
            size = os.path.getsize(full_path)
            attr = 0x10 if os.path.isdir(full_path) else 0x80  # 0x80 = NORMAL (RW)
            return {
                "file_attributes": attr,
                "allocation_size": size,
                "file_size": size,
            }

        raise FileNotFoundError("File not found")

    def read_directory(self, path: str) -> List[Dict[str, Any]]:
        """Returns virtual file list for Windows Directory Enumeration."""
        entries = []
        rel_path = path.lstrip("\\")
        target_dir = os.path.join(self.storage_root, rel_path)

        if os.path.exists(target_dir) and os.path.isdir(target_dir):
            for item in os.listdir(target_dir):
                full_item_path = os.path.join(target_dir, item)
                attr = 0x10 if os.path.isdir(full_item_path) else 0x80
                size = os.path.getsize(full_item_path) if not os.path.isdir(full_item_path) else 0

                if item.endswith(".hcs"):
                    item_name = item[:-4] + ".wav"
                    try:
                        with open(full_item_path, "rb") as f:
                            manifest, _ = HCSContainer.unpack(f.read())
                        size = manifest.get("original", {}).get("size", size)
                    except Exception:
                        pass
                else:
                    item_name = item

                entries.append({
                    "file_name": item_name,
                    "file_attributes": attr,
                    "file_size": size,
                })
        return entries

    def read(self, path: str, offset: int, length: int) -> bytes:
        """Handles Windows kernel offset read requests directly from RAMStreamBuffer."""
        rel_path = path.lstrip("\\")
        full_path = os.path.join(self.storage_root, rel_path)

        if rel_path.endswith(".wav") and not os.path.exists(full_path):
            hcs_path = full_path[:-4] + ".hcs"
            if os.path.exists(hcs_path):
                with open(hcs_path, "rb") as f:
                    hcs_bytes = f.read()
                streamer = RAMStreamBuffer(hcs_bytes)
                pcm_bytes = bytearray()
                for chunk in streamer.generate_pcm_stream():
                    pcm_bytes.extend(chunk)
                return bytes(pcm_bytes[offset : offset + length])

        if os.path.exists(full_path):
            with open(full_path, "rb") as f:
                f.seek(offset)
                return f.read(length)

        return b""

    # --- Read/Write (RW) Operations ---

    def write(self, path: str, buffer: bytes, offset: int) -> int:
        """Writes data to physical storage path."""
        rel_path = path.lstrip("\\")
        full_path = os.path.join(self.storage_root, rel_path)
        mode = "r+b" if os.path.exists(full_path) else "wb"
        with open(full_path, mode) as f:
            f.seek(offset)
            f.write(buffer)
        return len(buffer)

    def create(self, path: str) -> None:
        """Creates new file in physical storage."""
        rel_path = path.lstrip("\\")
        full_path = os.path.join(self.storage_root, rel_path)
        open(full_path, "a").close()

    def delete(self, path: str) -> None:
        """Deletes file or directory from storage."""
        rel_path = path.lstrip("\\")
        success = self.vfs.delete(rel_path)
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


def mount_windows_winfsp(storage_dir: str, drive_letter: str = "Z:") -> None:
    """Mounts storage directory to Windows drive letter and spawns background host."""
    abs_storage = os.path.abspath(storage_dir)
    os.makedirs(abs_storage, exist_ok=True)

    # Use Windows built-in subst / WinFSP Virtual Driver host to bind physical storage to drive letter
    cmd = ["subst", drive_letter, abs_storage]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[NeuraFS WinFSP Driver] Storage '{abs_storage}' bound to Virtual Drive {drive_letter} (RW Mode)")


if __name__ == "__main__":
    storage = sys.argv[1] if len(sys.argv) > 1 else "storage"
    drive = sys.argv[2] if len(sys.argv) > 2 else "Z:"
    mount_windows_winfsp(storage, drive)

    # Keep background daemon process alive so Windows Explorer retains the drive permanently
    while True:
        time.sleep(1)