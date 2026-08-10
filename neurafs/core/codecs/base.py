"""NeuraFS pluggable neural codec contract, registry, and capability helpers."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Type

import numpy as np

from neurafs.core.config import PrecisionMode
from neurafs.core.exceptions import NeuralResynthesisError


class CodecKind(str, Enum):
    """Payload strategy used by a codec inside .hcs containers."""

    INR_WEIGHTS = "inr_weights"
    DISCRETE_CODES = "discrete_codes"


class BaseNeuralCodec(ABC):
    """Abstract contract for all NeuraFS media codecs (SIREN, DAC, EnCodec, ...)."""

    codec_id: str = "base"
    architecture: str = "Base"
    kind: CodecKind = CodecKind.INR_WEIGHTS
    requires_subband_pipeline: bool = False

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def availability_error(cls) -> Optional[str]:
        return None

    @abstractmethod
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
        """Return (payload_bytes, chunk_units, neural_meta)."""

    @abstractmethod
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
        """Resynthesize Float32 PCM shaped (channels, samples)."""

    def encode_frame(
        self,
        pcm_chunk: np.ndarray,
        sample_rate: int,
        target_quality: float = 0.95,
    ) -> Tuple[bytes, Dict[str, Any]]:
        channels = 1 if pcm_chunk.ndim == 1 else int(pcm_chunk.shape[0])
        payload, units, neural = self.encode_media(
            pcm_data=pcm_chunk,
            sample_rate=sample_rate,
            channels=channels,
            filename="frame",
            file_size=int(pcm_chunk.nbytes),
        )
        return payload, {**neural, "chunks": units, "num_samples": int(pcm_chunk.shape[-1])}

    def decode_frame(
        self,
        raw_bytes: bytes,
        num_samples: int,
        sample_rate: int,
        metadata: Dict[str, Any],
    ) -> np.ndarray:
        units = metadata.get("chunks") or [
            {"offset": 0, "length": len(raw_bytes), "time_slice_idx": 0}
        ]
        channels = int(metadata.get("channels", 1))
        precision_str = metadata.get("precision", "fp16")
        precision = (
            PrecisionMode.HIGH_32 if precision_str == "fp32" else PrecisionMode.STANDARD_16
        )
        if units and "offset" in units[0]:
            blobs = [raw_bytes[u["offset"] : u["offset"] + u["length"]] for u in units]
        else:
            blobs = [raw_bytes]
        pcm = self.decode_media(
            chunk_units=units,
            blob_list=blobs,
            channels=channels,
            sample_rate=sample_rate,
            neural_info=metadata,
            precision=precision,
        )
        if num_samples > 0 and pcm.shape[-1] > num_samples:
            return pcm[..., :num_samples]
        return pcm


CODEC_REGISTRY: Dict[str, Type[BaseNeuralCodec]] = {}


def register_codec(name: str, codec_class: Type[BaseNeuralCodec]) -> None:
    CODEC_REGISTRY[name.lower()] = codec_class


def list_codecs() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for name, cls in CODEC_REGISTRY.items():
        available = cls.is_available()
        out[name] = {
            "architecture": getattr(cls, "architecture", name),
            "kind": getattr(cls, "kind", CodecKind.INR_WEIGHTS).value,
            "available": available,
            "hint": None if available else cls.availability_error(),
        }
    return out


def get_codec(name: str) -> BaseNeuralCodec:
    key = (name or "").lower().strip()
    if key not in CODEC_REGISTRY:
        known = ", ".join(sorted(CODEC_REGISTRY)) or "(empty)"
        raise NeuralResynthesisError(
            f"Codec '{name}' is not registered. Available: {known}"
        )
    cls = CODEC_REGISTRY[key]
    if not cls.is_available():
        hint = cls.availability_error() or f"Install dependencies for codec '{key}'."
        raise NeuralResynthesisError(
            f"Codec '{key}' is registered but unavailable. {hint}"
        )
    return cls()
