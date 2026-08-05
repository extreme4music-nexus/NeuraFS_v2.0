"""NeuraFS Windows WinFSP Kernel Driver Interface."""

import sys
import os
from typing import Dict, Any, List

try:
    import winfsp
except ImportError:
    winfsp = None

from neurafs.vfs.interface import NeuraFSVFSInterface


class NeuraFSWinFSP:
    """WinFSP driver service mounting NeuraFS containers to a Windows drive letter."""

    def __init__(self, storage_root: str):
        self.vfs = NeuraFSVFSInterface(storage_root)

    def get_file_info(self, path: str) -> Dict[str, Any]:
        """Translates FileAttributes and FileSize for Windows Explorer queries."""
        if path == "\\":
            return {
                "file_attributes": 0x10,  # FILE_ATTRIBUTE_DIRECTORY
                "allocation_size": 0,
                "file_size": 0,
            }

        try:
            attr = self.vfs.getattr(path)
            return {
                "file_attributes": 0x01,  # FILE_ATTRIBUTE_READONLY
                "allocation_size": attr.size,
                "file_size": attr.size,
            }
        except FileNotFoundError:
            raise FileExistsError("File not found")

    def read_directory(self, path: str) -> List[Dict[str, Any]]:
        """Returns virtual file list for Windows Directory Enumeration."""
        entries = []
        if path == "\\":
            attrs = self.vfs.readdir("")
            for a in attrs:
                entries.append({
                    "file_name": a.name,
                    "file_attributes": 0x01,
                    "file_size": a.size,
                })
        return entries

    def read(self, path: str, offset: int, length: int) -> bytes:
        """Handles Windows kernel offset read requests from RAM buffers."""
        return self.vfs.read(virtual_path=path, offset=offset, length=length)


def mount_windows_winfsp(storage_dir: str, drive_letter: str = "Z:") -> None:
    """Mounts target storage directory as a Windows virtual drive."""
    if winfsp is None:
        raise RuntimeError("Missing dependency 'winfsp'. Ensure WinFSP runtime and Python bindings are installed.")

    print(f"[NeuraFS WinFSP] Mounting '{storage_dir}' as drive {drive_letter}...")
    # Initialize WinFSP FileSystem Host Service
    fs_host = winfsp.FileSystemHost(NeuraFSWinFSP(storage_dir))
    fs_host.mount(drive_letter)
    fs_host.run()


if __name__ == "__main__":
    storage = sys.argv[1] if len(sys.argv) > 1 else "storage"
    drive = sys.argv[2] if len(sys.argv) > 2 else "Z:"
    mount_windows_winfsp(storage, drive)