"""NeuraFS Standardized Virtual File System Interface."""

import os
from typing import Dict, Any, List

from neurafs.core.container import HCSContainer
from neurafs.vfs.inspect import VFSMetadataInspector, VirtualFileAttributes
from neurafs.vfs.ram_streamer import RAMStreamBuffer


class NeuraFSVFSInterface:
    """Unified Virtual File System Layer routing OS kernel calls (read, getattr, readdir)."""

    def __init__(self, root_storage_dir: str):
        self.root_storage_dir = os.path.abspath(root_storage_dir)
        self.active_buffers: Dict[str, RAMStreamBuffer] = {}

    def getattr(self, virtual_path: str) -> VirtualFileAttributes:
        """Returns virtual file attributes for kernel filesystem requests."""
        hcs_path = self._resolve_hcs_path(virtual_path)
        return VFSMetadataInspector.inspect_file(hcs_path)

    def readdir(self, virtual_dir_path: str) -> List[VirtualFileAttributes]:
        """Lists virtual uncompressed files inside target directory."""
        target_dir = os.path.join(self.root_storage_dir, virtual_dir_path.lstrip("/\\"))
        if not os.path.exists(target_dir):
            raise FileNotFoundError(f"Virtual directory missing: {virtual_dir_path}")

        virtual_files = []
        for entry in os.listdir(target_dir):
            if entry.endswith(".hcs"):
                hcs_full = os.path.join(target_dir, entry)
                attrs = VFSMetadataInspector.inspect_file(hcs_full)
                virtual_files.append(attrs)

        return virtual_files

    def read(self, virtual_path: str, offset: int, length: int) -> bytes:
        """Handles byte-offset read requests directly from RAM stream buffers."""
        hcs_path = self._resolve_hcs_path(virtual_path)

        if hcs_path not in self.active_buffers:
            with open(hcs_path, "rb") as f:
                compressed_bytes = f.read()
            manifest, raw_blobs_data = HCSContainer.unpack(compressed_bytes)
            self.active_buffers[hcs_path] = RAMStreamBuffer(manifest, raw_blobs_data)

        stream_buffer = self.active_buffers[hcs_path]
        return stream_buffer.read_pcm_bytes(offset, length)

    def _resolve_hcs_path(self, virtual_path: str) -> str:
        """Maps virtual path request to physical .hcs container file location."""
        clean_path = virtual_path.lstrip("/\\")
        hcs_candidate = os.path.join(self.root_storage_dir, clean_path)

        if not hcs_candidate.endswith(".hcs"):
            hcs_candidate += ".hcs"

        if not os.path.exists(hcs_candidate):
            raise FileNotFoundError(f"Virtual path resolution failed: {virtual_path}")

        return hcs_candidate