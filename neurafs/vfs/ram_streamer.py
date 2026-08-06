"""NeuraFS Zero-Latency Prioritized Chunk-0 RAM Streamer."""

import io
import torch
import numpy as np
from typing import Generator, Dict, Any, List, Tuple
from scipy.signal import resample_poly

from neurafs.core.config import config, DecodeMode, PrecisionMode, TargetQualityTier
from neurafs.core.container import HCSContainer
from neurafs.core.codecs.siren import SirenAgent
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

    def _resynchronize_single_chunk(self, chunk_idx: int) -> np.ndarray:
        """Evaluates SIREN neural subband agents for a single 2.5s temporal chunk in RAM."""
        units = self.chunks_map.get(chunk_idx, [])
        if not units:
            return np.zeros((self.channels, int(self.sample_rate * config.CHUNK_DURATION_SEC)), dtype=np.float32)

        device = torch.device("cpu")
        samples_per_chunk = int(self.sample_rate * config.CHUNK_DURATION_SEC)
        t_coords = torch.linspace(-1.0, 1.0, steps=samples_per_chunk, dtype=torch.float32).unsqueeze(-1).to(device)

        subband_pcm_list = []
        for unit in units:
            offset = unit["offset"]
            length = unit["length"]
            raw_blob = self.raw_blobs_data[offset : offset + length]

            agent = SirenAgent.deserialize_weights(
                raw_blob,
                in_features=1,
                hidden_features=self.neural_info.get("hidden_features", config.SIREN_HIDDEN_FEATURES),
                hidden_layers=self.neural_info.get("hidden_layers", config.SIREN_HIDDEN_LAYERS),
                out_features=self.channels,
                precision=self.precision,
            ).to(device)

            agent.eval()
            with torch.no_grad():
                pred_pcm = agent(t_coords).cpu().numpy().T
            subband_pcm_list.append(pred_pcm)

        # Synthesize subbands into full-spectrum chunk PCM
        chunk_pcm = SubbandFilterBank.synthesize_subbands(subband_pcm_list)

        # Apply Adaptive Resampling if hardware forces fallback tier (e.g. 44100Hz -> 22050Hz)
        if self.target_sample_rate != self.sample_rate:
            chunk_pcm = resample_poly(chunk_pcm, self.target_sample_rate, self.sample_rate, axis=-1).astype(np.float32)

        return chunk_pcm

    def get_priority_chunk_0_pcm(self) -> Tuple[np.ndarray, int]:
        """Priority 1: Immediately resynthesizes Chunk 0 for 0ms playback start."""
        chunk_0_pcm = self._resynchronize_single_chunk(chunk_idx=0)
        return chunk_0_pcm, self.target_sample_rate

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
