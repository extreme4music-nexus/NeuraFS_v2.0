"""Descript Audio Codec (DAC) adapter for NeuraFS.

Optional dependency: `pip install descript-audio-codec` (imports as `dac`).
When unavailable, the codec stays registered but encode/decode raise a clear error
via BaseNeuralCodec.is_available() / get_codec().
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from neurafs.core.codecs.base import BaseNeuralCodec, CodecKind
from neurafs.core.codecs.discrete import (
    ensure_channels_shape,
    pack_codes,
    pcm_to_mono_batch,
    unpack_codes,
)
from neurafs.core.config import PrecisionMode, config
from neurafs.core.dsp import TemporalChunker
from neurafs.core.exceptions import NeuralResynthesisError


def _try_import_dac():
    try:
        import dac  # type: ignore

        return dac
    except Exception:
        return None


class DACCodec(BaseNeuralCodec):
    """Discrete RVQ neural codec backed by Descript Audio Codec."""

    codec_id = "dac"
    architecture = "DAC"
    kind = CodecKind.DISCRETE_CODES
    requires_subband_pipeline = False

    def __init__(self, model_type: str = "44khz", n_quantizers: Optional[int] = None):
        self.model_type = model_type
        self.n_quantizers = n_quantizers
        self._model = None

    @classmethod
    def is_available(cls) -> bool:
        return _try_import_dac() is not None

    @classmethod
    def availability_error(cls) -> Optional[str]:
        return (
            "Install Descript Audio Codec: pip install descript-audio-codec "
            "(optional extra: pip install neurafs[dac])."
        )

    def _load_model(self):
        if self._model is not None:
            return self._model
        dac = _try_import_dac()
        if dac is None:
            raise NeuralResynthesisError(self.availability_error())
        device = config.get_compute_device()
        model_path = dac.utils.download(model_type=self.model_type)
        model = dac.DAC.load(model_path)
        model.to(device)
        model.eval()
        self._model = model
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

        model = self._load_model()
        device = next(model.parameters()).device
        n_q = kwargs.get("n_quantizers", self.n_quantizers)

        # Encode per temporal chunk so VFS can seek without full-file decode
        chunks = TemporalChunker.slice_into_chunks(pcm_data, sample_rate=sample_rate)
        concatenated = bytearray()
        chunk_units: List[Dict[str, Any]] = []
        blob_offset = 0
        code_shapes = []

        for chunk in chunks:
            pcm_chunk = chunk["pcm_data"]
            if pcm_chunk.ndim == 1:
                wav = torch.from_numpy(pcm_chunk).float().unsqueeze(0).unsqueeze(0).to(device)
            else:
                wav = torch.from_numpy(pcm_chunk).float().unsqueeze(1).to(device)

            with torch.no_grad():
                x = model.preprocess(wav, sample_rate)
                # encode returns z, codes, latents, commitment_loss, codebook_loss
                _z, codes, *_rest = model.encode(x, n_quantizers=n_q)
                # codes: [1, n_q, T] for mono or [C, n_q, T] for multi-channel
                codes_np = codes.detach().cpu().numpy().astype(np.int16)

            blob = pack_codes(codes_np)
            blob_len = len(blob)
            chunk_units.append(
                {
                    "time_slice_idx": chunk["chunk_idx"],
                    "subband_idx": 0,
                    "offset": blob_offset,
                    "length": blob_len,
                    "num_samples": int(chunk["pcm_data"].shape[-1]),
                }
            )
            concatenated.extend(blob)
            blob_offset += blob_len
            code_shapes.append(list(codes_np.shape))

        neural_meta = {
            "architecture": self.architecture,
            "codec": self.codec_id,
            "kind": self.kind.value,
            "precision": precision.value,
            "model_type": self.model_type,
            "n_quantizers": n_q,
            "sample_rate": sample_rate,
            "channels": channels,
            "subbands": 1,
            "num_chunks": len(chunks),
            "code_shapes": code_shapes,
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

        model = self._load_model()
        device = next(model.parameters()).device
        pcm_chunks: List[np.ndarray] = []

        # Ensure chronological order
        ordered = sorted(
            zip(chunk_units, blob_list),
            key=lambda pair: int(pair[0].get("time_slice_idx", 0)),
        )

        for unit, blob in ordered:
            codes_np = unpack_codes(blob)
            codes = torch.from_numpy(codes_np.astype(np.int64)).to(device)
            if codes.dim() == 2:
                codes = codes.unsqueeze(0)
            with torch.no_grad():
                # Map codes → quantized latents → waveform
                z = model.quantizer.from_codes(codes)[0]
                y = model.decode(z)
                # y: [1, 1, T] for mono or [C, 1, T] for multi-channel
                pcm_buf = y.squeeze(1).detach().cpu().numpy().astype(np.float32)

            target_len = int(unit.get("num_samples") or 0)
            if target_len > 0 and pcm_buf.shape[-1] != target_len:
                if pcm_buf.shape[-1] > target_len:
                    pcm_buf = pcm_buf[..., :target_len]
                else:
                    pcm_buf = np.pad(pcm_buf, ((0, 0), (0, target_len - pcm_buf.shape[-1])))

            pcm_chunks.append(ensure_channels_shape(pcm_buf, channels))

        if not pcm_chunks:
            return np.zeros((channels, 0), dtype=np.float32)

        return TemporalChunker.reconstruct_from_chunks(
            pcm_chunks, sample_rate=sample_rate
        )
