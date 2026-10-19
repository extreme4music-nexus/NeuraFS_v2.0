"""NeuraFS Zero-Latency Prioritized Chunk-0 RAM Streamer."""

import io
import lzma
import torch
import numpy as np
from collections import OrderedDict
from typing import Generator, Dict, Any, List, Tuple, Optional
from scipy.signal import resample_poly

from neurafs.core.config import config, DecodeMode, PrecisionMode, TargetQualityTier
from neurafs.core.container import HCSContainer
from neurafs.core.codecs.siren import SirenAgent
from neurafs.core.engine import NeuraFSEngine
from neurafs.core.dsp import SubbandFilterBank, TemporalChunker


class RAMStreamBuffer:
    """Manages prioritized chunk resynthesis and zero-latency RAM audio streaming."""

    def __init__(self, hcs_bytes: bytes, decode_mode: DecodeMode = DecodeMode.REALTIME_ADAPTIVE):
        self.hcs_bytes = hcs_bytes
        self.decode_mode = decode_mode
        self.manifest, self.raw_blobs_data = HCSContainer.unpack(hcs_bytes)
        self.orig_info = self.manifest.get("original", {})
        self.neural_info = self.manifest.get("neural", {})

        self.sample_rate = self.orig_info.get("sample_rate", config.DEFAULT_SAMPLE_RATE)
        self.channels = self.orig_info.get("channels", 2)
        self.precision_str = self.neural_info.get("precision", "fp16")
        self.precision = PrecisionMode.HIGH_32 if self.precision_str == "fp32" else PrecisionMode.STANDARD_16

        self.chunk_units = self.manifest.get("chunks", [])
        self.num_subbands = self.neural_info.get("subbands", config.DEFAULT_SUBBANDS)

        # Resolve Dynamic Quality Degradation Tier based on hardware scanner
        self.hw_profile = config.scan_hardware(self.precision)
        self.target_sample_rate, self.quality_tier = config.resolve_decode_tier(
            self.decode_mode, self.hw_profile, self.sample_rate
        )

        # Group manifest units by temporal chunk index
        self.chunks_map: Dict[int, List[Dict[str, Any]]] = {}
        for unit in self.chunk_units:
            c_idx = unit["time_slice_idx"]
            self.chunks_map.setdefault(c_idx, []).append(unit)

        self.total_chunks = len(self.chunks_map)
        
        # Нов интелигентен LRU кеш за брзо премотување (чува последни 3 чанка)
        self.chunk_cache = OrderedDict()
        self.cache_limit = 3

    def _resynchronize_single_chunk(self, chunk_idx: int) -> np.ndarray:
        """Evaluates neural agents for a single 2.5s temporal chunk in RAM using container-bound codec."""
        units = self.chunks_map.get(chunk_idx, [])
        if not units:
            return np.zeros((self.channels, int(self.sample_rate * config.CHUNK_DURATION_SEC)), dtype=np.float32)

        blob_list = [
            self.raw_blobs_data[u["offset"] : u["offset"] + u["length"]] for u in units
        ]
        chunk_pcm = NeuraFSEngine.resynthesize_audio_from_units(
            chunk_units=units,
            blob_list=blob_list,
            channels=self.channels,
            sample_rate=self.sample_rate,
            precision=self.precision,
            neural_info=self.neural_info,
            num_chunks=1,
        )
        if self.target_sample_rate != self.sample_rate:
            chunk_pcm = resample_poly(
                chunk_pcm, self.target_sample_rate, self.sample_rate, axis=-1
            ).astype(np.float32)
        return chunk_pcm

    def get_priority_chunk_0_pcm(self) -> Tuple[np.ndarray, int]:
        """Priority 1: Immediately resynthesizes Chunk 0 for 0ms playback start."""
        chunk_0_pcm = self._resynchronize_single_chunk(chunk_idx=0)
        return chunk_0_pcm, self.target_sample_rate
        
    def _generate_wav_header(self) -> bytes:
        """Generates a dynamic 44-byte valid RIFF/WAV header on the fly."""
        import struct
        total_samples = self.orig_info.get("samples", 0)
        bytes_per_sample = 2  # 16-bit PCM
        pcm_data_size = total_samples * self.channels * bytes_per_sample
        file_size = pcm_data_size + 36
        
        header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF', file_size, b'WAVE',
            b'fmt ', 16, 1, self.channels, self.target_sample_rate,
            self.target_sample_rate * self.channels * bytes_per_sample,
            self.channels * bytes_per_sample, bytes_per_sample * 8,
            b'data', pcm_data_size
        )
        return header

    def read_pcm_bytes(self, offset: int, length: int) -> bytes:
        """Handles byte-exact random-access read requests from the OS kernel."""
        wav_header = self._generate_wav_header()
        requested_length = length
        result = bytearray()
        
        # Scenario 1: Intercept RIFF header (bytes 0 to 43)
        if offset < 44:
            header_slice = wav_header[offset : offset + requested_length]
            result.extend(header_slice)
            if len(result) >= requested_length:
                return bytes(result)
            current_pcm_offset = 0
        else:
            current_pcm_offset = offset - 44

        # Scenario 2: PCM Audio Payload
        bytes_per_sample = 2
        chunk_samples = int(self.target_sample_rate * config.CHUNK_DURATION_SEC)
        chunk_bytes = chunk_samples * self.channels * bytes_per_sample
        
        start_chunk = current_pcm_offset // chunk_bytes
        bytes_needed = requested_length - len(result)
        end_chunk = (current_pcm_offset + bytes_needed) // chunk_bytes
        
        for c_idx in range(start_chunk, end_chunk + 1):
            if c_idx >= self.total_chunks:
                break
                
            if c_idx in self.chunk_cache:
                chunk_pcm_bytes = self.chunk_cache[c_idx]
                self.chunk_cache.move_to_end(c_idx)
            else:
                pcm_float = self._resynchronize_single_chunk(c_idx)
                chunk_pcm_bytes = (np.clip(pcm_float, -1.0, 1.0) * 32767.0).astype(np.int16).T.tobytes()
                
                self.chunk_cache[c_idx] = chunk_pcm_bytes
                if len(self.chunk_cache) > self.cache_limit:
                    self.chunk_cache.popitem(last=False)
                    
            chunk_start_pos = c_idx * chunk_bytes
            local_offset = max(0, current_pcm_offset - chunk_start_pos)
            remaining_needed = requested_length - len(result)
            bytes_to_take = min(len(chunk_pcm_bytes) - local_offset, remaining_needed)
            
            result.extend(chunk_pcm_bytes[local_offset : local_offset + bytes_to_take])
            if len(result) >= requested_length:
                break
            current_pcm_offset = chunk_start_pos + len(chunk_pcm_bytes)
            
        return bytes(result)

    def generate_pcm_stream(self) -> Generator[bytes, None, None]:
        """Yields continuous Int16 PCM byte buffers chunk-by-chunk directly from RAM."""
        previous_chunk = None

        for c_idx in range(self.total_chunks):
            current_chunk = self._resynchronize_single_chunk(c_idx)

            if previous_chunk is not None:
                # Apply smooth Overlap-Add crossfade between adjacent chunks
                stitched_pcm = TemporalChunker.reconstruct_from_chunks(
                    [previous_chunk, current_chunk],
                    sample_rate=self.target_sample_rate
                )
                # Extract second half of crossfaded buffer
                half_len = stitched_pcm.shape[-1] // 2
                pcm_out = stitched_pcm[..., :half_len]
            else:
                pcm_out = current_chunk

            previous_chunk = current_chunk

            # Convert Float32 [-1.0, 1.0] to Int16 PCM bytes for audio output
            audio_int16 = (np.clip(pcm_out, -1.0, 1.0) * 32767.0).astype(np.int16)
            yield audio_int16.T.tobytes()

class DataStreamBuffer:
    """Handles transparent on-the-fly LZMA decompression for non-media data files in RAM."""

    def __init__(self, hcs_bytes: bytes):
        self.hcs_bytes = hcs_bytes
        self._decompressed_data: Optional[bytes] = None

    def _decompress_all(self) -> bytes:
        if self._decompressed_data is None:
            try:
                self._decompressed_data = lzma.decompress(self.hcs_bytes)
            except Exception:
                self._decompressed_data = b""
        return self._decompressed_data

    def read_bytes(self, offset: int, length: int) -> bytes:
        """Serves byte-exact offset reads from decompressed RAM buffer."""
        data = self._decompress_all()
        return data[offset : offset + length]