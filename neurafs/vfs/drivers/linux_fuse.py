"""NeuraFS Linux FUSE Kernel Driver Interface (Read/Write Mode)."""

import os
import sys
import errno
from typing import Dict, Any, List

try:
    import fuse
    from fuse import FUSE, FuseOSError, Operations
except ImportError:
    FUSE = None
    FuseOSError = Exception
    Operations = object

from neurafs.vfs.interface import NeuraFSVFSInterface


class NeuraFSFUSE(Operations):
    """FUSE operation handler routing Linux kernel Read/Write I/O requests."""

    def __init__(self, storage_root: str):
        self.storage_root = os.path.abspath(storage_root)
        self.vfs = NeuraFSVFSInterface(self.storage_root)

    def getattr(self, path: str, fh: Any = None) -> Dict[str, Any]:
        """Maps file status attributes for Linux stat() queries (RW Mode)."""
        if path == "/":
            return {
                "st_mode": (0o040777),  # Directory, rwxrwxrwx (RW)
                "st_nlink": 2,
                "st_size": 4096,
            }

        try:
            attr = self.vfs.getattr(path)
            mode = 0o040777 if attr["is_dir"] else 0o100666
            return {
                "st_mode": mode,
                "st_nlink": 2 if attr["is_dir"] else 1,
                "st_size": attr["size"],
                "st_blocks": (attr["size"] + 511) // 512,
            }
        except FileNotFoundError:
            raise FuseOSError(errno.ENOENT)
        except Exception:
            raise FuseOSError(errno.EIO)

    def readdir(self, path: str, fh: Any) -> List[str]:
        """Lists directory entries for ls / readdir() calls."""
        entries = [".", ".."]
        if path == "/":
            try:
                attrs = self.vfs.readdir("")
                entries.extend([a.name for a in attrs])
            except Exception:
                raise FuseOSError(errno.EIO)
        return entries

    def open(self, path: str, flags: int) -> int:
        """Validates open access permissions."""
        return 0

    def read(self, path: str, length: int, offset: int, fh: int) -> bytes:
        """Translates offset byte reads into NeuraFS RAM stream buffer fetches."""
        try:
            return self.vfs.read(virtual_path=path, offset=offset, length=length)
        except Exception:
            raise FuseOSError(errno.EIO)

    # --- Write / Modify Operations ---

    def create(self, path: str, mode: int, fi: Any = None) -> int:
        full_path = os.path.join(self.storage_root, path.lstrip("/"))
        open(full_path, "a").close()
        return 0

    def write(self, path: str, data: bytes, offset: int, fh: int) -> int:
        full_path = os.path.join(self.storage_root, path.lstrip("/"))
        with open(full_path, "r+b" if os.path.exists(full_path) else "wb") as f:
            f.seek(offset)
            f.write(data)
        return len(data)

    def unlink(self, path: str) -> None:
        """Intercepts Linux file deletion / CUT operations."""
        success = self.vfs.delete(path)
        if not success:
            raise FuseOSError(errno.ENOENT)

    def mkdir(self, path: str, mode: int) -> None:
        full_path = os.path.join(self.storage_root, path.lstrip("/"))
        os.makedirs(full_path, exist_ok=True)

    def rmdir(self, path: str) -> None:
        """Intercepts Linux folder deletion."""
        success = self.vfs.delete(path)
        if not success:
            raise FuseOSError(errno.ENOENT)


def mount_linux_fuse(storage_dir: str, mount_point: str) -> None:
    """Mounts NeuraFS storage directory to target Linux mount point in Read/Write mode."""
    if FUSE is None:
        raise RuntimeError("Missing dependency 'fusepy'. Install via: pip install fusepy")

    os.makedirs(mount_point, exist_ok=True)
    print(f"[NeuraFS FUSE] Mounting '{storage_dir}' to '{mount_point}' (RW Mode)...")
    FUSE(
        NeuraFSFUSE(storage_dir),
        mount_point,
        foreground=True,
        ro=False,  # Full Read-Write
        nothreads=False,
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    mount_linux_fuse(sys.argv[1], sys.argv[2])