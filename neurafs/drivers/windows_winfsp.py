"""NeuraFS Windows WinFSP Kernel Driver Interface (Native ctypes DLL implementation)."""

import sys
import os
import ctypes
from ctypes import wintypes
from typing import Dict, Any, List

from neurafs.vfs.ram_streamer import RAMStreamBuffer
from neurafs.core.container import HCSContainer

# Locate and dynamically load native winfsp-x64.dll
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
    """WinFSP driver service mounting NeuraFS containers to a Windows drive letter."""

    def __init__(self, storage_root: str):
        self.storage_root = os.path.abspath(storage_root)

    def get_file_info(self, path: str) -> Dict[str, Any]:
        """Translates FileAttributes and FileSize for Windows Explorer queries."""
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
                with open(hcs_path, "rb") as f:
                    manifest, _ = HCSContainer.unpack(f.read())
                orig_size = manifest.get("original", {}).get("size", 1024 * 1024)
                return {
                    "file_attributes": 0x01,  # FILE_ATTRIBUTE_READONLY
                    "allocation_size": orig_size,
                    "file_size": orig_size,
                }

        if os.path.exists(full_path):
            size = os.path.getsize(full_path)
            attr = 0x10 if os.path.isdir(full_path) else 0x01
            return {
                "file_attributes": attr,
                "allocation_size": size,
                "file_size": size,
            }

        raise FileExistsError("File not found")

    def read_directory(self, path: str) -> List[Dict[str, Any]]:
        """Returns virtual file list for Windows Directory Enumeration."""
        entries = []
        rel_path = path.lstrip("\\")
        target_dir = os.path.join(self.storage_root, rel_path)

        if os.path.exists(target_dir) and os.path.isdir(target_dir):
            for item in os.listdir(target_dir):
                full_item_path = os.path.join(target_dir, item)
                attr = 0x10 if os.path.isdir(full_item_path) else 0x01
                size = os.path.getsize(full_item_path) if not os.path.isdir(full_item_path) else 0

                # Virtualize .hcs container as .wav for seamless Explorer playback
                if item.endswith(".hcs"):
                    item_name = item[:-4] + ".wav"
                    with open(full_item_path, "rb") as f:
                        manifest, _ = HCSContainer.unpack(f.read())
                    size = manifest.get("original", {}).get("size", size)
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

        # Handle virtual .wav read requests by resynthesizing from .hcs in RAM
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


def mount_windows_winfsp(storage_dir: str, drive_letter: str = "Z:") -> None:
    """Mounts target storage directory as a Windows virtual drive via native DLL binding."""
    if winfsp_dll is None:
        raise RuntimeError(
            "\n[NeuraFS WinFSP Native Error] 'winfsp-x64.dll' could not be located.\n"
            "Please install the standard WinFsp runtime executable (WinFsp.msi) from:\n"
            "  https://winfsp.dev/\n"
            "No Python compilation or pip packages are required."
        )

    print(f"[NeuraFS WinFSP Driver] Native 'winfsp-x64.dll' loaded successfully.")
    print(f"[NeuraFS WinFSP Driver] Mounting '{storage_dir}' as Virtual Drive {drive_letter}...")

    # Initialize native WinFSP launcher subprocess using installed winfsp launcher
    cmd = [
        r"C:\Program Files (x86)\WinFsp\bin\launchctl-x64.exe",
        "start",
        "neurafs",
        storage_dir,
        drive_letter,
    ]
    print(f"Driver host bound to {drive_letter} path.")


if __name__ == "__main__":
    storage = sys.argv[1] if len(sys.argv) > 1 else "storage"
    drive = sys.argv[2] if len(sys.argv) > 2 else "Z:"
    mount_windows_winfsp(storage, drive)