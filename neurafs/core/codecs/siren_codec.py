"""SIREN INR codec adapter — alternative / default continuous-weight codec."""

from __future__ import annotations

import multiprocessing as mp
from typing import Any, Dict, List, Tuple

import numpy as np
import torch

from neurafs.core.codecs.base import BaseNeuralCodec, CodecKind
from neurafs.core.codecs.siren import SirenAgent, compute_composite_loss
from neurafs.core.config import PrecisionMode, config
from neurafs.core.dsp import SpectralComplexityAnalyzer, SubbandFilterBank, TemporalChunker


def _isolated_subband_worker(args: Dict[str, Any]) -> Dict[str, Any]:
    """Isolated multi-core worker training a SIREN agent on one subband chunk."""
    subband_pcm = args["pcm"]
    precision_str = args["precision"]
    epochs = args["epochs"]
    channels = 1 if subband_pcm.ndim == 1 else int(subband_pcm.shape[0])

    device = torch.device("cpu")
    num_samples = subband_pcm.shape[-1]

    t_coords = (
        torch.linspace(-1.0, 1.0, steps=num_samples, dtype=torch.float32)
        .unsqueeze(-1)
        .to(device)
    )
    targets = torch.from_numpy(subband_pcm).T.float().to(device)
    if targets.ndim == 1:
        targets = targets.unsqueeze(-1)

    agent = SirenAgent(
        in_features=1,
        hidden_features=config.SIREN_HIDDEN_FEATURES,
        hidden_layers=config.SIREN_HIDDEN_LAYERS,
        out_features=channels,
        omega_0=config.SIREN_OMEGA_0,
    ).to(device)

    optimizer = torch.optim.Adam(agent.parameters(), lr=1e-4)
    agent.train()
    for _ in range(epochs):
        optimizer.zero_grad()
        output = agent(t_coords)
        loss = compute_composite_loss(output, targets)
        loss.backward()
        optimizer.step()

    precision = PrecisionMode.HIGH_32 if precision_str == "fp32" else PrecisionMode.STANDARD_16
    return {
        "chunk_idx": args["chunk_idx"],
        "band_idx": args["band_idx"],
        "blob": agent.serialize_weights(precision),
        "channels": channels,
        "num_samples": num_samples,
    }


class SirenCodec(BaseNeuralCodec):
    """Continuous INR (SIREN) codec using the subband + temporal chunk pipeline."""

    codec_id = "siren"
    architecture = "SIREN"
    kind = CodecKind.INR_WEIGHTS
    requires_subband_pipeline = True

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
        hw_profile = config.scan_hardware(precision)
        complexity_metrics = SpectralComplexityAnalyzer.analyze_complexity(pcm_data)
        complexity_score = complexity_metrics["complexity_score"]
        num_subbands = config.calculate_dynamic_subbands(
            complexity_score, hw_profile.recommended_workers
        )
        dynamic_epochs = config.calculate_dynamic_epochs(complexity_score)
        chunks = TemporalChunker.slice_into_chunks(pcm_data, sample_rate=sample_rate)

        worker_tasks: List[Dict[str, Any]] = []
        for chunk in chunks:
            c_idx = chunk["chunk_idx"]
            valid_samples = int(chunk["end_sample"] - chunk["start_sample"])
            subbands, _cutoff_pairs = SubbandFilterBank.decompose_subbands(
                chunk["pcm_data"], num_bands=num_subbands, sample_rate=sample_rate
            )
            for b_idx, subband_pcm in enumerate(subbands):
                worker_tasks.append(
                    {
                        "chunk_idx": c_idx,
                        "band_idx": b_idx,
                        "pcm": subband_pcm[..., :valid_samples],
                        "precision": precision.value,
                        "epochs": dynamic_epochs,
                    }
                )

        num_workers = max(1, min(hw_profile.recommended_workers, len(worker_tasks) or 1))
        if worker_tasks:
            with mp.Pool(processes=num_workers) as pool:
                results = pool.map(_isolated_subband_worker, worker_tasks)
        else:
            results = []

        concatenated = bytearray()
        chunk_units: List[Dict[str, Any]] = []
        blob_offset = 0
        for res in results:
            blob_bytes = res["blob"]
            blob_len = len(blob_bytes)
            chunk_units.append(
                {
                    "time_slice_idx": res["chunk_idx"],
                    "subband_idx": res["band_idx"],
                    "num_samples": res["num_samples"],
                    "offset": blob_offset,
                    "length": blob_len,
                }
            )
            concatenated.extend(blob_bytes)
            blob_offset += blob_len

        neural_meta = {
            "architecture": self.architecture,
            "codec": self.codec_id,
            "kind": self.kind.value,
            "precision": precision.value,
            "hidden_layers": config.SIREN_HIDDEN_LAYERS,
            "hidden_features": config.SIREN_HIDDEN_FEATURES,
            "omega_0": config.SIREN_OMEGA_0,
            "subbands": num_subbands,
            "epochs": dynamic_epochs,
            "complexity": complexity_metrics,
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
        device = torch.device("cpu")
        samples_per_chunk = int(sample_rate * config.CHUNK_DURATION_SEC)

        num_chunks = int(
            kwargs.get("num_chunks")
            or neural_info.get("num_chunks")
            or (max((u.get("time_slice_idx", 0) for u in chunk_units), default=0) + 1)
        )
        hidden_features = int(
            neural_info.get("hidden_features", config.SIREN_HIDDEN_FEATURES)
        )
        hidden_layers = int(neural_info.get("hidden_layers", config.SIREN_HIDDEN_LAYERS))
        omega_0 = float(neural_info.get("omega_0", config.SIREN_OMEGA_0))

        reconstructed_chunks: List[List[np.ndarray]] = [[] for _ in range(num_chunks)]

        for unit, raw_blob in zip(chunk_units, blob_list):
            c_idx = int(unit["time_slice_idx"])
            unit_samples = int(unit.get("num_samples") or samples_per_chunk)
            unit_samples = max(1, min(samples_per_chunk, unit_samples))
            t_coords = (
                torch.linspace(-1.0, 1.0, steps=unit_samples, dtype=torch.float32)
                .unsqueeze(-1)
                .to(device)
            )
            agent = SirenAgent.deserialize_weights(
                raw_blob,
                in_features=1,
                hidden_features=hidden_features,
                hidden_layers=hidden_layers,
                out_features=channels,
                precision=precision,
            ).to(device)
            agent.eval()
            with torch.no_grad():
                pred_pcm = agent(t_coords).cpu().numpy().T
            if pred_pcm.shape[-1] < samples_per_chunk:
                pad_width = samples_per_chunk - pred_pcm.shape[-1]
                pred_pcm = np.pad(pred_pcm, ((0, 0), (0, pad_width)))
            else:
                pred_pcm = pred_pcm[..., :samples_per_chunk]
            if c_idx < len(reconstructed_chunks):
                reconstructed_chunks[c_idx].append(pred_pcm)

        synthesized = []
        for band_list in reconstructed_chunks:
            if not band_list:
                synthesized.append(
                    np.zeros((channels, samples_per_chunk), dtype=np.float32)
                )
            else:
                synthesized.append(SubbandFilterBank.synthesize_subbands(band_list))

        return TemporalChunker.reconstruct_from_chunks(
            synthesized, sample_rate=sample_rate
        )
