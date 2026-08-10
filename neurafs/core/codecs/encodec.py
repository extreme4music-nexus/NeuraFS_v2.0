"""Meta EnCodec adapter for NeuraFS.

Preferred dependency: `pip install encodec`
Fallback: `torchaudio.pipelines.ENCODEC_*` when available.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from neurafs.core.codecs.base import BaseNeuralCodec, CodecKind
from neurafs.core.codecs.discrete import (
    ensure_channels_shape,
    pack_codes,
    unpack_codes,
)
from neurafs.core.config import PrecisionMode, config
from neurafs.core.dsp import TemporalChunker
from neurafs.core.exceptions import NeuralResynthesisError


def _try_import_encodec_model():
    """Return (backend_name, factory) or (None, None)."""
    try:
        from encodec import EncodecModel  # type: ignore

        def factory(bandwidth: float = 6.0, sample_rate: int = 24000):
            if sample_rate >= 48000:
                model = EncodecModel.encodec_model_48khz()
            else:
                model = EncodecModel.encodec_model_24khz()
            model.set_target_bandwidth(bandwidth)
            return model

        return "encodec", factory
    except Exception:
        pass

    try:
        import torchaudio  # type: ignore

        def factory(bandwidth: float = 6.0, sample_rate: int = 24000):
            # torchaudio Encodec bundles; pick closest
            if hasattr(torchaudio.pipelines, "ENCODEC_24KHZ"):
                bundle = torchaudio.pipelines.ENCODEC_24KHZ
                model = bundle.get_model()
                if hasattr(model, "set_target_bandwidth"):
                    model.set_target_bandwidth(bandwidth)
                return model
            raise ImportError("torchaudio EnCodec pipeline unavailable")

        return "torchaudio", factory
    except Exception:
        return None, None


class EnCodecCodec(BaseNeuralCodec):
    """Discrete RVQ neural codec backed by Meta EnCodec."""

    codec_id = "encodec"
    architecture = "EnCodec"
    kind = CodecKind.DISCRETE_CODES
    requires_subband_pipeline = False

    def __init__(self, bandwidth: float = 6.0, model_sr: int = 24000):
        self.bandwidth = bandwidth
        self.model_sr = model_sr
        self._model = None
        self._backend = None

    @classmethod
    def is_available(cls) -> bool:
        name, _ = _try_import_encodec_model()
        return name is not None

    @classmethod
    def availability_error(cls) -> Optional[str]:
        return (
            "Install EnCodec: pip install encodec  "
            "(optional extra: pip install neurafs[encodec]), "
            "or use a torchaudio build that ships EnCodec pipelines."
        )

    def _load_model(self, sample_rate: int):
        if self._model is not None:
            return self._model
        backend, factory = _try_import_encodec_model()
        if factory is None:
            raise NeuralResynthesisError(self.availability_error())
        device = config.get_compute_device()
        model = factory(bandwidth=self.bandwidth, sample_rate=sample_rate)
        model.to(device)
        model.eval()
        self._model = model
        self._backend = backend
        return model

    def encode_media(
        self,
        pcm_data: np.ndarray,
        sample_rate: int,
        channels: int,
        filename: str,
        file_size: int,
        precision: PrecisionMode = PrecisionMode.STANDARD_16,
        **kwargs: Any,
    ) -> Tuple[bytes, List[Dict[str, Any]], Dict[str, Any]]:
        import torch

        bandwidth = float(kwargs.get("bandwidth", self.bandwidth))
        model = self._load_model(sample_rate)
        if hasattr(model, "set_target_bandwidth"):
            model.set_target_bandwidth(bandwidth)
        device = next(model.parameters()).device

        chunks = TemporalChunker.slice_into_chunks(pcm_data, sample_rate=sample_rate)
        concatenated = bytearray()
        chunk_units: List[Dict[str, Any]] = []
        blob_offset = 0

        for chunk in chunks:
            pcm = chunk["pcm_data"].astype(np.float32)
            if pcm.ndim == 1:
                wav = torch.from_numpy(pcm).unsqueeze(0).unsqueeze(0)
            else:
                wav = torch.from_numpy(pcm).unsqueeze(0)  # [1, C, T]
            wav = wav.to(device)

            with torch.no_grad():
                # encodec API: encode -> list of (codes, scale) frames
                encoded = model.encode(wav)
                # Flatten frame codes: each codes is [n_q, T] or [B, n_q, T]
                frame_codes = []
                for frame in encoded:
                    codes = frame[0] if isinstance(frame, (tuple, list)) else frame
                    if codes.dim() == 3:
                        codes = codes[0]
                    frame_codes.append(codes.detach().cpu().numpy().astype(np.int16))
                # Concatenate along time for single chunk blob
                codes_np = np.concatenate(frame_codes, axis=-1) if frame_codes else np.zeros((1, 0), np.int16)

            blob = pack_codes(codes_np)
            blob_len = len(blob)
            chunk_units.append(
                {
                    "time_slice_idx": chunk["chunk_idx"],
                    "subband_idx": 0,
                    "offset": blob_offset,
                    "length": blob_len,
                    "num_samples": int(pcm.shape[-1]),
                }
            )
            concatenated.extend(blob)
            blob_offset += blob_len

        neural_meta = {
            "architecture": self.architecture,
            "codec": self.codec_id,
            "kind": self.kind.value,
            "precision": precision.value,
            "bandwidth": bandwidth,
            "backend": self._backend,
            "sample_rate": sample_rate,
            "channels": channels,
            "subbands": 1,
            "num_chunks": len(chunks),
        }
        return bytes(concatenated), chunk_units, neural_meta

    def decode_media(
        self,
        chunk_units: List[Dict[str, Any]],
        blob_list: List[bytes],
        channels: int,
        sample_rate: int,
        neural_info: Dict[str, Any],
        precision: PrecisionMode = PrecisionMode.STANDARD_16,
        **kwargs: Any,
    ) -> np.ndarray:
        import torch

        bandwidth = float(neural_info.get("bandwidth", self.bandwidth))
        model = self._load_model(sample_rate)
        if hasattr(model, "set_target_bandwidth"):
            model.set_target_bandwidth(bandwidth)
        device = next(model.parameters()).device

        pcm_chunks: List[np.ndarray] = []
        ordered = sorted(
            zip(chunk_units, blob_list),
            key=lambda pair: int(pair[0].get("time_slice_idx", 0)),
        )

        for unit, blob in ordered:
            codes_np = unpack_codes(blob)
            codes = torch.from_numpy(codes_np.astype(np.int64)).unsqueeze(0).to(device)
            # EncodedFrame format: list[(codes, scale)]
            encoded_frames = [(codes, None)]
            with torch.no_grad():
                wav = model.decode(encoded_frames)
                # wav: [B, C, T]
                pcm = wav[0].detach().cpu().numpy().astype(np.float32)

            target_len = int(unit.get("num_samples") or 0)
            if target_len > 0 and pcm.shape[-1] != target_len:
                if pcm.shape[-1] > target_len:
                    pcm = pcm[..., :target_len]
                else:
                    pcm = np.pad(pcm, ((0, 0), (0, target_len - pcm.shape[-1])))

            pcm_chunks.append(ensure_channels_shape(pcm, channels))

        if not pcm_chunks:
            return np.zeros((channels, 0), dtype=np.float32)

        return TemporalChunker.reconstruct_from_chunks(
            pcm_chunks, sample_rate=sample_rate
        )
