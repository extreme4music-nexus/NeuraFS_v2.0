"""NeuraFS HCS Binary Container Layout & Version Router Specification."""

import json
import lzma
import struct
from typing import Dict, List, Tuple, Any

from neurafs.core.config import config, PrecisionMode
from neurafs.core.exceptions import (
    InvalidHCSHeaderError,
    UnsupportedHCSVersionError,
    CorruptedManifestError,
)


class HCSContainer:
    """Handles binary serialization, header parsing, and version routing for .hcs files."""

    HEADER_STRUCT = ">4s4sI"  # Magic (4B), Flags/Version (4B), Manifest Length (4B)
    HEADER_SIZE = struct.calcsize(HEADER_STRUCT)  # 12 Bytes total

    @classmethod
    def pack(
        cls,
        manifest: Dict[str, Any],
        raw_blobs: List[bytes],
        precision: PrecisionMode = PrecisionMode.STANDARD_16,
    ) -> bytes:
        """Packs metadata manifest and raw weight blobs into a standardized HCS binary container."""
        # Ensure manifest compliance
        manifest["hcs_version"] = "1.0"
        manifest["neural"]["precision"] = precision.value

        try:
            meta_json_bytes = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        except Exception as err:
            raise CorruptedManifestError(f"Failed to serialize manifest to JSON: {err}") from err

        meta_len = len(meta_json_bytes)

        # Build 12-byte uncompressed header
        header = struct.pack(
            cls.HEADER_STRUCT,
            config.MAGIC_HEADER,
            config.FORMAT_VERSION_FLAGS,
            meta_len,
        )

        # Concatenate sequential raw neural weight blobs
        payload_bytes = bytearray()
        for blob in raw_blobs:
            payload_bytes.extend(blob)

        # Assemble uncompressed binary container layout
        container_payload = header + meta_json_bytes + bytes(payload_bytes)

        # Apply LZMA compression preset
        return lzma.compress(container_payload, preset=config.LZMA_PRESET)

    @classmethod
    def unpack(cls, compressed_bytes: bytes) -> Tuple[Dict[str, Any], bytes]:
        """Decompresses container and routes version handling based on header flags."""
        try:
            decompressed = lzma.decompress(compressed_bytes)
        except Exception as err:
            raise InvalidHCSHeaderError(f"LZMA decompression failed: {err}") from err

        if len(decompressed) < cls.HEADER_SIZE:
            raise InvalidHCSHeaderError("Container size is smaller than the mandatory 12-byte header.")

        # Parse 12-byte binary header
        magic, flags, meta_len = struct.unpack(
            cls.HEADER_STRUCT, decompressed[: cls.HEADER_SIZE]
        )

        # Validate Magic Identifier
        if magic != config.MAGIC_HEADER:
            raise InvalidHCSHeaderError(
                f"Invalid magic identifier: expected {config.MAGIC_HEADER!r}, got {magic!r}"
            )

        # Route version handling based on flags/magic
        return cls._route_version_unpack(magic, flags, meta_len, decompressed[cls.HEADER_SIZE :])

    @classmethod
    def _route_version_unpack(
        cls, magic: bytes, flags: bytes, meta_len: int, body_bytes: bytes
    ) -> Tuple[Dict[str, Any], bytes]:
        """Routes unpacking based on version flag specifications."""
        version_id = flags[3]  # Extract version byte from flag mask

        if version_id == 1:
            return cls._unpack_v1(meta_len, body_bytes)
        elif version_id == 2:
            # Future Hook for HCS2 INT8 Quantized Payload
            raise UnsupportedHCSVersionError("HCS2 (INT8 Quantized) format engine is not yet initialized.")
        else:
            raise UnsupportedHCSVersionError(f"Unsupported HCS version flag encountered: {flags!r}")

    @classmethod
    def _unpack_v1(cls, meta_len: int, body_bytes: bytes) -> Tuple[Dict[str, Any], bytes]:
        """Unpacks Version 1.0 (FP16/FP32 Raw Payload)."""
        if len(body_bytes) < meta_len:
            raise CorruptedManifestError("Container truncated before full JSON manifest could be read.")

        meta_bytes = body_bytes[:meta_len]
        raw_blobs_data = body_bytes[meta_len:]

        try:
            manifest = json.loads(meta_bytes.decode("utf-8"))
        except Exception as err:
            raise CorruptedManifestError(f"Failed to parse metadata JSON manifest: {err}") from err

        # Validate required manifest schema fields
        required_keys = ["hcs_version", "original", "neural", "chunks"]
        for key in required_keys:
            if key not in manifest:
                raise CorruptedManifestError(f"Missing mandatory key '{key}' in manifest schema.")

        return manifest, raw_blobs_data