"""NeuraFS Standardized Virtual File System Interface."""

import os
from typing import Dict, Any, List

from neurafs.vfs.virtual_layer import VFSVirtualLayer
from neurafs.vfs.ram_streamer import RAMStreamBuffer, DataStreamBuffer
from neurafs.core.container import HCSContainer
from neurafs.core.modules.state_db import StateManager
from neurafs.core.modules.activity_logger import ActivityLogger


class NeuraFSVFSInterface:
    """Unified Virtual File System Layer routing OS kernel calls (read, getattr, readdir)."""

    def __init__(self, root_storage_dir: str):
        self.root_storage_dir = os.path.abspath(root_storage_dir)
        self.active_buffers: Dict[str, RAMStreamBuffer] = {}

    def getattr(self, virtual_path: str) -> Dict[str, Any]:
        """Returns spoofed virtual file attributes for kernel filesystem requests."""
        attr = VFSVirtualLayer.get_virtual_attributes(self.root_storage_dir, virtual_path)
        if not attr:
            raise FileNotFoundError(f"Virtual path missing: {virtual_path}")
        return attr

    def readdir(self, virtual_dir_path: str) -> List[Dict[str, Any]]:
        """Lists virtualized uncompressed files inside target directory."""
        target_dir = os.path.join(self.root_storage_dir, virtual_dir_path.lstrip("/\\"))
        return VFSVirtualLayer.resolve_virtual_listing(target_dir)

    def read(self, virtual_path: str, offset: int, length: int) -> bytes:
        """Handles byte-offset read requests directly from RAM stream buffers or raw files."""
        clean_rel = virtual_path.lstrip("/\\")
        phys_direct = os.path.join(self.root_storage_dir, clean_rel)
        phys_hcs = f"{phys_direct}.hcs"

        # Scenario A: File is COMPLETED_HCS (.hcs container)
        if os.path.exists(phys_hcs):
            if phys_hcs not in self.active_buffers:
                with open(phys_hcs, "rb") as f:
                    hcs_bytes = f.read()
                
                # Автоматска детекција: Невронско аудио или LZMA Податоци
                try:
                    self.active_buffers[phys_hcs] = RAMStreamBuffer(hcs_bytes)
                except Exception:
                    self.active_buffers[phys_hcs] = DataStreamBuffer(hcs_bytes)

            streamer = self.active_buffers[phys_hcs]
            if isinstance(streamer, RAMStreamBuffer):
                return streamer.read_pcm_bytes(offset, length)
            else:
                return streamer.read_bytes(offset, length)

        # Scenario B: File is in PROCESSING or UNCONVERTED state (Passthrough)
        if os.path.exists(phys_direct):
            with open(phys_direct, "rb") as f:
                f.seek(offset)
                return f.read(length)

        return b""

    def delete(self, virtual_path: str) -> bool:
        """Intercepts CUT/MOVE/DELETE operations to physically clean .hcs containers and state DB."""
        clean_rel = virtual_path.lstrip("/\\")
        phys_direct = os.path.join(self.root_storage_dir, clean_rel)
        phys_hcs = f"{phys_direct}.hcs"

        # Избриши ги активните RAM кешови за фајлот
        self.active_buffers.pop(phys_hcs, None)

        deleted = False
        target_path = None

        if os.path.exists(phys_hcs):
            os.remove(phys_hcs)
            target_path = phys_direct
            deleted = True
        elif os.path.exists(phys_direct):
            if os.path.isdir(phys_direct):
                os.rmdir(phys_direct)
            else:
                os.remove(phys_direct)
            target_path = phys_direct
            deleted = True

        if deleted and target_path:
            StateManager.update_status(target_path, status="DELETED")
            ActivityLogger.log("VFS_DELETE", f"Removed item via VFS virtual path: {os.path.basename(virtual_path)}")
            return True

        return False