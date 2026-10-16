"""NeuraFS Parallel Encoding Engine & Multi-Agent Orchestrator."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import numpy as np

from neurafs.core.codecs import get_codec
from neurafs.core.codecs.siren_codec import _isolated_subband_worker  # noqa: F401  (mp pickling alias)
from neurafs.core.config import PrecisionMode, config
from neurafs.core.container import HCSContainer
from neurafs.core.dsp import AudioLoader
from neurafs.benchmarks.metrics import compute_metrics


class NeuraFSEngine:
    """Core orchestrator: routes encode/decode through the pluggable codec registry."""

    @classmethod
    def encode_media(
        cls,
        file_bytes: bytes,
        filename: str,
        precision: PrecisionMode = PrecisionMode.STANDARD_16,
        codec: Optional[str] = None,
        **codec_kwargs: Any,
    ) -> bytes:
        """Encode media into .hcs neural container bytes using the selected codec.

        Parameters
        ----------
        codec :
            Registry id (`siren`, `dac`, `encodec`). Defaults to config.DEFAULT_CODEC.
        """
        start_time = time.time()
        codec_id = (codec or config.DEFAULT_CODEC).lower().strip()
        agent = get_codec(codec_id)

        pcm_data, sample_rate, channels = AudioLoader.load_from_bytes(file_bytes)

        payload, chunk_units, neural_meta = agent.encode_media(
            pcm_data=pcm_data,
            sample_rate=sample_rate,
            channels=channels,
            filename=filename,
            file_size=len(file_bytes),
            precision=precision,
            **codec_kwargs,
        )

        complexity = neural_meta.pop("complexity", {}) if isinstance(neural_meta, dict) else {}

        manifest = {
            "hcs_version": "1.0",
            "original": {
                "name": filename,
                "size": len(file_bytes),
                "type": "neural_media",
                "channels": channels,
                "sample_rate": sample_rate,
                "samples": int(pcm_data.shape[-1]),
            },
            "neural": {
                **neural_meta,
                "codec": neural_meta.get("codec", codec_id),
                "architecture": neural_meta.get("architecture", codec_id.upper()),
                "precision": precision.value,
                "encode_seconds": round(time.time() - start_time, 3),
            },
            "metrics": complexity if isinstance(complexity, dict) else {},
            "chunks": chunk_units,
        }

        hcs_bytes = HCSContainer.pack(manifest, payload, precision=precision)

        # Optional reconstruction metrics (best-effort; never fail encode)
        try:
            blob_list = [
                payload[u["offset"] : u["offset"] + u["length"]] for u in chunk_units
            ]
            recon_pcm = cls.resynthesize_audio_from_units(
                chunk_units=chunk_units,
                blob_list=blob_list,
                channels=channels,
                sample_rate=sample_rate,
                precision=precision,
                neural_info=manifest["neural"],
            )
            metrics = compute_metrics(pcm_data, recon_pcm, sample_rate)
            manifest["metrics"].update(metrics)
            hcs_bytes = HCSContainer.pack(manifest, payload, precision=precision)
        except Exception:
            pass

        return hcs_bytes

    @classmethod
    def resynthesize_audio_from_units(
        cls,
        chunk_units: List[Dict[str, Any]],
        blob_list: List[bytes],
        channels: int,
        sample_rate: int,
        precision: PrecisionMode,
        num_subbands: Optional[int] = None,
        num_chunks: Optional[int] = None,
        neural_info: Optional[Dict[str, Any]] = None,
        codec: Optional[str] = None,
        **kwargs: Any,
    ) -> np.ndarray:
        """Resynthesize full PCM by dispatching to the codec recorded in neural_info."""
        info = dict(neural_info or {})
        if num_subbands is not None and "subbands" not in info:
            info["subbands"] = num_subbands
        if num_chunks is not None:
            info["num_chunks"] = num_chunks

        if isinstance(precision, str):
            precision = PrecisionMode.HIGH_32 if precision == "fp32" else PrecisionMode.STANDARD_16

        # Smart container auto-codec binding: original container codec takes strict precedence over external assignments
        bound_codec = info.get("codec") or _architecture_to_codec(info.get("architecture"))
        codec_id = bound_codec or codec or config.DEFAULT_CODEC
        agent = get_codec(str(codec_id))
        return agent.decode_media(
            chunk_units=chunk_units,
            blob_list=blob_list,
            channels=channels,
            sample_rate=sample_rate,
            neural_info=info,
            precision=precision,
            num_chunks=num_chunks or info.get("num_chunks"),
            **kwargs,
        )


def _architecture_to_codec(architecture: Optional[str]) -> Optional[str]:
    if not architecture:
        return None
    key = architecture.strip().lower()
    aliases = {
        "siren": "siren",
        "dac": "dac",
        "encodec": "encodec",
        "en-codec": "encodec",
        "futureneuralcodec_v1": "future_codec",
    }
    return aliases.get(key, key if key in ("siren", "dac", "encodec", "future_codec") else None)
