"""NeuraFS On-Demand Chunk Resynthesis & RAM Streaming Buffer Engine."""

import threading
from typing import Dict, Any, List, Optional
import numpy as np

from neurafs.core.config import config, PrecisionMode
from neurafs.core.engine import NeuraFSEngine


class RAMStreamBuffer:
    """Manages chunk-level resynthesis in RAM for zero-latency audio streaming."""

    def __init__(self, manifest: Dict[str, Any], raw_blobs_data: bytes):
        self.manifest = manifest
        self.raw_blobs_data = raw_blobs_data
        self.orig_info = manifest.get("original", {})
        self.neural_info = manifest.get("neural", {})

        self.sample_rate = self.orig_info.get("sample_rate", 44100)
        self.channels = self.orig_info.get("channels", 2)
        self.chunk_units = manifest.get("chunks", [])

        precision_str = self.neural_info.get("precision", "fp16")
        self.precision = PrecisionMode.HIGH_32 if precision_str == "fp32" else PrecisionMode.STANDARD_16

        # Group chunk units by time_slice_idx
        self.slice_groups: Dict[int, List[Dict[str, Any]]] = {}
        for unit in self.chunk_units:
            ts = unit["time_slice_idx"]
            self.slice_groups.setdefault(ts, []).append(unit)

        self.total_slices = len(self.slice_groups)
        self.resynthesized_slices: Dict[int, np.ndarray] = {}
        self.lock = threading.Lock()

        # Instantly resynthesize chunk 0 (first 2.5 seconds) on startup
        self._resynthesize_slice(0)

        # Launch background worker thread for remaining chunks
        if self.total_slices > 1:
            threading.Thread(target=self._background_resynthesis_loop, daemon=True).start()

    def _resynthesize_slice(self, slice_idx: int) -> Optional[np.ndarray]:
        """Resynthesizes a single temporal slice into RAM."""
        with self.lock:
            if slice_idx in self.resynthesized_slices:
                return self.resynthesized_slices[slice_idx]

        units = self.slice_groups.get(slice_idx, [])
        if not units:
            return None

        blob_list = [self.raw_blobs_data[u["offset"] : u["offset"] + u["length"]] for u in units]

        pcm_float = NeuraFSEngine.resynthesize_audio_from_units(
            chunk_units=units,
            raw_blobs=blob_list,
            channels=self.channels,
            sample_rate=self.sample_rate,
            precision=self.precision,
        )

        with self.lock:
            self.resynthesized_slices[slice_idx] = pcm_float

        return pcm_float

    def _background_resynthesis_loop(self) -> None:
        """Background daemon sequentially resynthesizing remaining audio chunks."""
        for slice_idx in range(1, self.total_slices):
            self._resynthesize_slice(slice_idx)

    def read_pcm_bytes(self, offset_bytes: int, length_bytes: int) -> bytes:
        """Reads reconstructed 16-bit PCM byte array directly from RAM buffers."""
        bytes_per_sample = 2 * self.channels
        start_sample = offset_bytes // bytes_per_sample
        end_sample = (offset_bytes + length_bytes) // bytes_per_sample

        slice_samples = int(self.sample_rate * config.CHUNK_DURATION_SEC)
        start_slice = start_sample // slice_samples
        end_slice = end_sample // slice_samples

        out_chunks = []
        for s_idx in range(start_slice, end_slice + 1):
            pcm_slice = self._resynthesize_slice(s_idx)
            if pcm_slice is not None:
                out_chunks.append(pcm_slice)

        if not out_chunks:
            return b""

        full_pcm_float = np.concatenate(out_chunks, axis=0)
        
        # Calculate local slice offset
        local_start = start_sample - (start_slice * slice_samples)
        local_end = local_start + (end_sample - start_sample)
        
        selected_pcm = full_pcm_float[local_start:local_end]
        pcm_int16 = (np.clip(selected_pcm, -1.0, 1.0) * 32767.0).astype(np.int16)

        return pcm_int16.tobytes()