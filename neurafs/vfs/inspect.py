"""NeuraFS VFS Instant Metadata Inspection & Attribute Mapping."""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass

from neurafs.core.container import HCSContainer


@dataclass
class VirtualFileAttributes:
    """Standardized virtual file attribute structure for kernel VFS interfaces."""

    name: str
    size: int
    is_dir: bool
    mode: int
    sample_rate: int = 44100
    channels: int = 2
    duration_sec: float = 0.0
    file_type: str = "neural_media"


class VFSMetadataInspector:
    """Parses .hcs container headers to expose virtual file attributes instantaneously."""

    @staticmethod
    def inspect_file(hcs_path: str) -> VirtualFileAttributes:
        """Reads 12-byte header and JSON manifest to construct virtual file stats in <1ms."""
        if not os.path.exists(hcs_path):
            raise FileNotFoundError(f"HCS container not found: {hcs_path}")

        with open(hcs_path, "rb") as f:
            # Read first 1024 bytes to parse header and manifest without reading full payload
            header_sample = f.read(1024)

        manifest, _ = HCSContainer.unpack(header_sample)
        orig = manifest.get("original", {})
        neural = manifest.get("neural", {})

        orig_name = orig.get("name", os.path.basename(hcs_path).replace(".hcs", ""))
        orig_size = orig.get("size", 0)
        file_type = orig.get("type", "neural_media")

        sample_rate = orig.get("sample_rate", 44100)
        channels = orig.get("channels", 2)
        total_samples = orig.get("samples", 0)
        duration_sec = total_samples / sample_rate if sample_rate > 0 else 0.0

        # POSIX file mode (Regular file, read-only: 0o100444)
        mode = 0o100444

        return VirtualFileAttributes(
            name=orig_name,
            size=orig_size,
            is_dir=False,
            mode=mode,
            sample_rate=sample_rate,
            channels=channels,
            duration_sec=duration_sec,
            file_type=file_type,
        )