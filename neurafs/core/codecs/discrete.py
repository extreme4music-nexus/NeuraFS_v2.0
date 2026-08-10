"""Shared helpers for packing/unpacking discrete RVQ code tensors into .hcs blobs."""

from __future__ import annotations

import struct
from typing import Any, Dict, Tuple

import numpy as np


# Magic + version + ndim + dtype_code + shape...
_HEADER = "<4sB B B"


def pack_codes(codes: np.ndarray, extra: Dict[str, Any] | None = None) -> bytes:
    """Pack an integer code tensor (e.g. [n_q, T] or [C, n_q, T]) into a binary blob.

    Layout:
      magic(4)='NQCS' | ver(u8)=1 | ndim(u8) | dtype(u8) | shape(ndim * u32) | raw
    dtype: 0=int16, 1=int32, 2=uint16, 3=uint32
    """
    arr = np.asarray(codes)
    if arr.dtype == np.int16:
        dtype_code = 0
    elif arr.dtype == np.int32:
        dtype_code = 1
    elif arr.dtype == np.uint16:
        dtype_code = 2
    elif arr.dtype == np.uint32:
        dtype_code = 3
    else:
        arr = arr.astype(np.int32)
        dtype_code = 1

    shape = arr.shape
    header = struct.pack(
        f"<4sBBB{len(shape)}I",
        b"NQCS",
        1,
        len(shape),
        dtype_code,
        *shape,
    )
    return header + arr.tobytes()


def unpack_codes(blob: bytes) -> np.ndarray:
    """Inverse of pack_codes."""
    if len(blob) < 7:
        raise ValueError("Discrete code blob too short")
    magic, ver, ndim, dtype_code = struct.unpack_from("<4sBBB", blob, 0)
    if magic != b"NQCS":
        raise ValueError(f"Invalid discrete codes magic: {magic!r}")
    if ver != 1:
        raise ValueError(f"Unsupported discrete codes version: {ver}")
    offset = 7
    shape = struct.unpack_from(f"<{ndim}I", blob, offset)
    offset += 4 * ndim
    dtype_map = {0: np.int16, 1: np.int32, 2: np.uint16, 3: np.uint32}
    dtype = dtype_map.get(dtype_code)
    if dtype is None:
        raise ValueError(f"Unknown discrete dtype code: {dtype_code}")
    arr = np.frombuffer(blob[offset:], dtype=dtype)
    expected = int(np.prod(shape)) if shape else 0
    if arr.size < expected:
        raise ValueError("Truncated discrete code payload")
    return arr[:expected].reshape(shape).copy()


def pcm_to_mono_batch(pcm_data: np.ndarray) -> np.ndarray:
    """Convert (channels, samples) float PCM to mono float32 waveform [samples]."""
    if pcm_data.ndim == 1:
        return pcm_data.astype(np.float32, copy=False)
    # Average channels for codecs that expect mono; stereo handled by caller if needed
    return pcm_data.mean(axis=0).astype(np.float32)


def ensure_channels_shape(pcm: np.ndarray, channels: int) -> np.ndarray:
    """Normalize decoded PCM to (channels, samples)."""
    pcm = np.asarray(pcm, dtype=np.float32)
    if pcm.ndim == 1:
        if channels <= 1:
            return pcm[np.newaxis, :]
        return np.repeat(pcm[np.newaxis, :], channels, axis=0)
    if pcm.shape[0] == channels:
        return pcm
    if pcm.shape[0] == 1 and channels > 1:
        return np.repeat(pcm, channels, axis=0)
    if pcm.shape[0] > channels:
        return pcm[:channels]
    # pad by repeating last channel
    pad = np.repeat(pcm[-1:], channels - pcm.shape[0], axis=0)
    return np.concatenate([pcm, pad], axis=0)
