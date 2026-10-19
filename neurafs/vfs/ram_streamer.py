"""NeuraFS Zero-Latency Prioritized Chunk-0 RAM Streamer."""

import lzma
import math
import os
import subprocess
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
        self.original_name = self.orig_info.get("name", "audio.wav")
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
        self.total_samples = int(self.orig_info.get("samples") or 0)
        self.output_samples = math.ceil(
            self.total_samples * self.target_sample_rate / self.sample_rate
        ) if self.sample_rate else self.total_samples
        
        # Нов интелигентен LRU кеш за брзо премотување (чува последни 3 чанка)
        self.chunk_cache = OrderedDict()
        self.cache_limit = 3
        self._encoded_file_cache: Optional[bytes] = None

    def _resynchronize_single_chunk(self, chunk_idx: int) -> np.ndarray:
        """Evaluates neural agents for a single 2.5s temporal chunk in RAM using container-bound codec."""
        units = self.chunks_map.get(chunk_idx, [])
        if not units:
            return np.zeros((self.channels, int(self.sample_rate * config.CHUNK_DURATION_SEC)), dtype=np.float32)

        # The codec API reconstructs chunk indices relative to the supplied unit
        # list. Renumber a single selected chunk so SIREN does not drop chunk 1+.
        units = [dict(unit, time_slice_idx=0) for unit in units]

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
        total_samples = self.output_samples
        bytes_per_sample = 2  # 16-bit PCM
        pcm_data_size = total_samples * self.channels * bytes_per_sample
        file_size = pcm_data_size + 36
        if file_size > 0xFFFFFFFF:
            raise ValueError("Virtual WAV exceeds RIFF's 4 GiB limit.")
        
        header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF', file_size, b'WAVE',
            b'fmt ', 16, 1, self.channels, self.target_sample_rate,
            self.target_sample_rate * self.channels * bytes_per_sample,
            self.channels * bytes_per_sample, bytes_per_sample * 8,
            b'data', pcm_data_size
        )
        return header

    @property
    def file_extension(self) -> str:
        return os.path.splitext(self.original_name)[1].lower()

    @property
    def virtual_file_size(self) -> int:
        """Exact virtual byte size, including the source file's visible format."""
        if self.file_extension in (".wav", ".wave"):
            return 44 + self.output_samples * self.channels * 2
        return len(self._render_encoded_file())

    def _chunk_pcm(self, chunk_idx: int) -> np.ndarray:
        """Return a normalized, target-rate PCM chunk from the small LRU cache."""
        if chunk_idx in self.chunk_cache:
            chunk = self.chunk_cache[chunk_idx]
            self.chunk_cache.move_to_end(chunk_idx)
            return chunk

        chunk = self._resynchronize_single_chunk(chunk_idx)
        chunk_samples = int(self.target_sample_rate * config.CHUNK_DURATION_SEC)
        if chunk.shape[-1] < chunk_samples:
            chunk = np.pad(chunk, ((0, 0), (0, chunk_samples - chunk.shape[-1])))
        else:
            chunk = chunk[..., :chunk_samples]
        self.chunk_cache[chunk_idx] = chunk
        if len(self.chunk_cache) > self.cache_limit:
            self.chunk_cache.popitem(last=False)
        return chunk

    def _render_pcm_range(self, start_sample: int, end_sample: int) -> np.ndarray:
        """Render a random-access sample interval with the chunker's overlap-add."""
        start_sample = max(0, int(start_sample))
        end_sample = min(self.output_samples, int(end_sample))
        if end_sample <= start_sample:
            return np.zeros((self.channels, 0), dtype=np.float32)

        chunk_samples = int(self.target_sample_rate * config.CHUNK_DURATION_SEC)
        overlap_samples = int(chunk_samples * 0.05)
        step_samples = chunk_samples - overlap_samples
        output = np.zeros((self.channels, end_sample - start_sample), dtype=np.float32)
        weights = np.zeros(end_sample - start_sample, dtype=np.float32)

        window = np.ones(chunk_samples, dtype=np.float32)
        if overlap_samples:
            fade = np.hanning(overlap_samples * 2).astype(np.float32)
            window[:overlap_samples] = fade[:overlap_samples]
            window[-overlap_samples:] = fade[overlap_samples:]

        first_chunk = max(0, start_sample // step_samples - 1)
        last_chunk = min(self.total_chunks - 1, (end_sample - 1) // step_samples)
        for chunk_idx in range(first_chunk, last_chunk + 1):
            chunk_start = chunk_idx * step_samples
            left = max(start_sample, chunk_start)
            right = min(end_sample, chunk_start + chunk_samples)
            if right <= left:
                continue
            local_start = left - chunk_start
            local_end = right - chunk_start
            output_start = left - start_sample
            output_end = right - start_sample
            local_window = window[local_start:local_end]
            chunk = self._chunk_pcm(chunk_idx)
            output[:, output_start:output_end] += (
                chunk[:, local_start:local_end] * local_window
            )
            weights[output_start:output_end] += local_window

        weights[weights < 1e-6] = 1.0
        return output / weights[np.newaxis, :]

    @staticmethod
    def _pcm16_bytes(pcm: np.ndarray) -> bytes:
        return (np.clip(pcm, -1.0, 1.0) * 32767.0).astype(np.int16).T.tobytes()

    def read_pcm_bytes(self, offset: int, length: int) -> bytes:
        """Serve byte-exact WAV reads, respecting the virtual size and EOF."""
        if offset < 0 or length <= 0:
            return b""
        file_size = self.virtual_file_size
        if offset >= file_size:
            return b""
        end = min(file_size, offset + length)
        header = self._generate_wav_header()
        result = bytearray()

        if offset < len(header):
            header_end = min(end, len(header))
            result.extend(header[offset:header_end])
        payload_start = max(offset, len(header))
        if end > payload_start:
            byte_start = payload_start - len(header)
            byte_end = end - len(header)
            block_align = self.channels * 2
            frame_start = byte_start // block_align
            frame_end = (byte_end + block_align - 1) // block_align
            pcm = self._render_pcm_range(frame_start, frame_end)
            pcm_bytes = self._pcm16_bytes(pcm)
            result.extend(pcm_bytes[byte_start - frame_start * block_align:byte_end - frame_start * block_align])
        return bytes(result)

    def _render_encoded_file(self) -> bytes:
        """Re-encode reconstructed PCM in memory to match the visible extension."""
        if self._encoded_file_cache is not None:
            return self._encoded_file_cache

        if self.file_extension in (".wav", ".wave"):
            output = bytearray(self._generate_wav_header())
            offset = 0
            while offset < self.virtual_file_size - 44:
                block = self.read_pcm_bytes(44 + offset, 1024 * 1024)
                if not block:
                    break
                output.extend(block)
                offset += len(block)
            self._encoded_file_cache = bytes(output)
            return self._encoded_file_cache

        codecs = {
            ".mp3": ("mp3", ["-c:a", "libmp3lame", "-b:a", "320k"]),
            ".flac": ("flac", ["-c:a", "flac"]),
            ".m4a": ("ipod", ["-c:a", "aac", "-b:a", "256k"]),
            ".aac": ("adts", ["-c:a", "aac", "-b:a", "256k"]),
            ".ogg": ("ogg", ["-c:a", "libvorbis", "-q:a", "6"]),
            ".opus": ("opus", ["-c:a", "libopus", "-b:a", "192k"]),
            ".wma": ("asf", ["-c:a", "wmav2", "-b:a", "192k"]),
            ".aif": ("aiff", ["-c:a", "pcm_s16be"]),
            ".aiff": ("aiff", ["-c:a", "pcm_s16be"]),
        }
        try:
            muxer, codec_args = codecs[self.file_extension]
        except KeyError as exc:
            raise ValueError(
                f"RAM VFS cannot produce the original audio format '{self.file_extension}'."
            ) from exc

        units = self.chunk_units
        blobs = [self.raw_blobs_data[u["offset"]:u["offset"] + u["length"]] for u in units]
        num_chunks = max((int(u.get("time_slice_idx", 0)) for u in units), default=-1) + 1
        pcm = NeuraFSEngine.resynthesize_audio_from_units(
            chunk_units=units,
            blob_list=blobs,
            channels=self.channels,
            sample_rate=self.sample_rate,
            precision=self.precision,
            neural_info=self.neural_info,
            num_chunks=num_chunks,
            num_samples=self.total_samples,
        )
        if self.target_sample_rate != self.sample_rate:
            pcm = resample_poly(pcm, self.target_sample_rate, self.sample_rate, axis=-1)
        pcm = np.asarray(pcm[..., :self.output_samples], dtype=np.float32)
        if pcm.shape[-1] < self.output_samples:
            pcm = np.pad(pcm, ((0, 0), (0, self.output_samples - pcm.shape[-1])))

        command = [
            "ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(self.target_sample_rate),
            "-ac", str(self.channels), "-i", "pipe:0", "-map_metadata", "-1",
            *codec_args, "-f", muxer, "pipe:1",
        ]
        try:
            result = subprocess.run(
                command,
                input=np.ascontiguousarray(pcm.T).tobytes(),
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            raise RuntimeError("FFmpeg is required to virtualize this audio format.") from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Could not render virtual audio: {detail}")
        self._encoded_file_cache = result.stdout
        return self._encoded_file_cache

    def read_file_bytes(self, offset: int, length: int) -> bytes:
        """Read virtual audio bytes in their visible original format."""
        if offset < 0 or length <= 0:
            return b""
        if self.file_extension in (".wav", ".wave"):
            return self.read_pcm_bytes(offset, length)
        payload = self._render_encoded_file()
        return payload[offset:offset + length]

    def generate_pcm_stream(self) -> Generator[bytes, None, None]:
        """Yield the same sample sequence exposed by random-access WAV reads."""
        chunk_samples = int(self.target_sample_rate * config.CHUNK_DURATION_SEC)
        overlap_samples = int(chunk_samples * 0.05)
        step_samples = chunk_samples - overlap_samples
        for start in range(0, self.output_samples, step_samples):
            end = min(self.output_samples, start + step_samples)
            yield self._pcm16_bytes(self._render_pcm_range(start, end))

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
