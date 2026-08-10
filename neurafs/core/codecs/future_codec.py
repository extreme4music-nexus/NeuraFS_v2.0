"""Backward-compatible FutureNeuralCodec stub and legacy re-exports.

Prefer neurafs.core.codecs.base / dac / encodec / siren_codec for new work.
"""

from typing import Any, Dict, Tuple

import numpy as np

from neurafs.core.codecs.base import (
    BaseNeuralCodec,
    CODEC_REGISTRY,
    get_codec,
    list_codecs,
    register_codec,
)
from neurafs.core.exceptions import NeuralResynthesisError


class FutureNeuralCodec(BaseNeuralCodec):
    """Legacy placeholder codec kept for registry / import compatibility."""

    codec_id = "future_codec"
    architecture = "FutureNeuralCodec_v1"
    requires_subband_pipeline = False

    def __init__(self, latent_dim: int = 128, num_quantizers: int = 8):
        self.codec_name = "FutureNeuralCodec_v1"
        self.latent_dim = latent_dim
        self.num_quantizers = num_quantizers

    def encode_media(
        self,
        pcm_data: np.ndarray,
        sample_rate: int,
        channels: int,
        filename: str,
        file_size: int,
        precision=None,
        **kwargs: Any,
    ):
        raise NeuralResynthesisError(
            "FutureNeuralCodec is a stub. Use codec='dac' or codec='encodec' instead."
        )

    def decode_media(
        self,
        chunk_units,
        blob_list,
        channels: int,
        sample_rate: int,
        neural_info: Dict[str, Any],
        precision=None,
        **kwargs: Any,
    ) -> np.ndarray:
        raise NeuralResynthesisError(
            "FutureNeuralCodec is a stub. Use codec='dac' or codec='encodec' instead."
        )

    def encode_frame(
        self,
        pcm_chunk: np.ndarray,
        sample_rate: int,
        target_quality: float = 0.95,
    ) -> Tuple[bytes, Dict[str, Any]]:
        if len(pcm_chunk) == 0:
            raise NeuralResynthesisError("Cannot encode empty PCM audio slice.")
        downsample_factor = 320
        num_frames = max(1, len(pcm_chunk) // downsample_factor)
        mock_tokens = np.zeros((self.num_quantizers, num_frames), dtype=np.int16)
        metadata = {
            "codec": self.codec_name,
            "latent_dim": self.latent_dim,
            "quantizers": self.num_quantizers,
            "num_samples": int(len(pcm_chunk)),
            "sample_rate": sample_rate,
        }
        return mock_tokens.tobytes(), metadata

    def decode_frame(
        self,
        raw_bytes: bytes,
        num_samples: int,
        sample_rate: int,
        metadata: Dict[str, Any],
    ) -> np.ndarray:
        if not raw_bytes or num_samples <= 0:
            return np.zeros(num_samples, dtype=np.float32)
        return np.zeros(num_samples, dtype=np.float32)


__all__ = [
    "BaseNeuralCodec",
    "FutureNeuralCodec",
    "CODEC_REGISTRY",
    "register_codec",
    "get_codec",
    "list_codecs",
    "NeuralResynthesisError",
]
