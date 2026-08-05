"""NeuraFS Linux FUSE Kernel Driver Interface."""

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
    """FUSE operation handler routing Linux kernel I/O requests to NeuraFS VFS Interface."""

    def __init__(self, storage_root: str):
        self.vfs = NeuraFSVFSInterface(storage_root)

    def getattr(self, path: str, fh: Any = None) -> Dict[str, Any]:
        """Maps file status attributes for Linux stat() queries."""
        if path == "/":
            return {
                "st_mode": (0o040755),  # Directory, rwxr-xr-x
                "st_nlink": 2,
                "st_size": 4096,
            }

        try:
            attr = self.vfs.getattr(path)
            return {
                "st_mode": (0o100444),  # Regular file, r--r--r--
                "st_nlink": 1,
                "st_size": attr.size,
                "st_blocks": (attr.size + 511) // 512,
            }
        except FileNotFoundError:
            raise FuseOSError(errno.ENOENT)
        except Exception as err:
            raise FuseOSError(errno.EIO)

    def readdir(self, path: str, fh: Any) -> List[str]:
        """Lists directory entries for ls / readdir() calls."""
        entries = [".", ".."]
        if path == "/":
            try:
                attrs = self.vfs.readdir("")
                entries.extend([a.name for a in attrs])
            except Exception as err:
                raise FuseOSError(errno.EIO)
        return entries

    def open(self, path: str, flags: int) -> int:
        """Validates read access permissions when a file is opened."""
        try:
            # Enforce read-only access flags
            if (flags & os.O_WRONLY) or (flags & os.O_RDWR):
                raise FuseOSError(errno.EROFS)
            _ = self.vfs.getattr(path)
            return 0
        except FileNotFoundError:
            raise FuseOSError(errno.ENOENT)

    def read(self, path: str, length: int, offset: int, fh: int) -> bytes:
        """Translates offset byte reads into NeuraFS RAM stream buffer fetches."""
        try:
            return self.vfs.read(virtual_path=path, offset=offset, length=length)
        except Exception as err:
            raise FuseOSError(errno.EIO)


def mount_linux_fuse(storage_dir: str, mount_point: str) -> None:
    """Mounts NeuraFS storage directory to target Linux mount point."""
    if FUSE is None:
        raise RuntimeError("Missing dependency 'fusepy'. Install via: pip install fusepy")

    os.makedirs(mount_point, exist_ok=True)
    print(f"[NeuraFS FUSE] Mounting '{storage_dir}' to '{mount_point}'...")
    FUSE(
        NeuraFSFUSE(storage_dir),
        mount_point,
        foreground=True,
        ro=True,
        nothreads=False,
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m neurafs.drivers.linux_fuse <storage_dir> <mount_point>")
        sys.exit(1)
    mount_linux_fuse(sys.argv[1], sys.argv[2])