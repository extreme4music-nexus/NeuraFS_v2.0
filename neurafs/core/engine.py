"""NeuraFS Parallel Encoding Engine & Multi-Agent Orchestrator."""

import os
import time
import multiprocessing as mp
import numpy as np
import torch
from typing import Dict, Any, List, Tuple

from neurafs.core.config import config, PrecisionMode, DecodeMode
from neurafs.core.dsp import (
    AudioLoader,
    SpectralComplexityAnalyzer,
    SubbandFilterBank,
    TemporalChunker,
)
from neurafs.core.codecs.siren import SirenAgent, compute_composite_loss
from neurafs.core.container import HCSContainer
from neurafs.benchmarks.metrics import compute_metrics


def _isolated_subband_worker(args: Dict[str, Any]) -> Dict[str, Any]:
    """Isolated multi-core worker process executing SIREN training on a specific subband chunk."""
    subband_pcm = args["pcm"]
    precision_str = args["precision"]
    epochs = args["epochs"]
    channels = subband_pcm.ndim if subband_pcm.ndim == 1 else subband_pcm.shape[0]

    device = torch.device("cpu")  # Isolated CPU worker thread
    num_samples = subband_pcm.shape[-1]

    # Coordinate domain input [-1.0, 1.0]
    t_coords = torch.linspace(-1.0, 1.0, steps=num_samples, dtype=torch.float32).unsqueeze(-1).to(device)
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

    # Train SIREN Agent for target dynamic epochs
    agent.train()
    for _ in range(epochs):
        optimizer.zero_grad()
        output = agent(t_coords)
        loss = compute_composite_loss(output, targets)
        loss.backward()
        optimizer.step()

    precision = PrecisionMode.HIGH_32 if precision_str == "fp32" else PrecisionMode.STANDARD_16
    serialized_blob = agent.serialize_weights(precision)

    return {
        "chunk_idx": args["chunk_idx"],
        "band_idx": args["band_idx"],
        "blob": serialized_blob,
        "channels": channels,
    }


class NeuraFSEngine:
    """Core Orchestrator managing parallel neural media encoding and synthesis."""

    @classmethod
    def encode_media(
        cls, file_bytes: bytes, filename: str, precision: PrecisionMode = PrecisionMode.STANDARD_16
    ) -> bytes:
        """Encodes media file into .hcs neural container bytes using parallel worker pool."""
        start_time = time.time()
        hw_profile = config.scan_hardware(precision)

        # 1. Load Audio PCM
        pcm_data, sample_rate, channels = AudioLoader.load_from_bytes(file_bytes)

        # 2. Analyze Audio Complexity
        complexity_metrics = SpectralComplexityAnalyzer.analyze_complexity(pcm_data)
        complexity_score = complexity_metrics["complexity_score"]

        # 3. Dynamic Hardware & Subband Allocation
        num_subbands = config.calculate_dynamic_subbands(complexity_score, hw_profile.recommended_workers)
        dynamic_epochs = config.calculate_dynamic_epochs(complexity_score)

        # 4. Slice Audio into 2.5s Temporal Chunks
        chunks = TemporalChunker.slice_into_chunks(pcm_data, sample_rate=sample_rate)

        worker_tasks = []
        chunk_manifest_units = []
        blob_offset = 0

        # 5. Decompose Each Temporal Chunk into Dynamic Subbands
        for chunk in chunks:
            c_idx = chunk["chunk_idx"]
            subbands, cutoff_pairs = SubbandFilterBank.decompose_subbands(
                chunk["pcm_data"], num_bands=num_subbands, sample_rate=sample_rate
            )

            for b_idx, (subband_pcm, cutoffs) in enumerate(zip(subbands, cutoff_pairs)):
                worker_tasks.append({
                    "chunk_idx": c_idx,
                    "band_idx": b_idx,
                    "pcm": subband_pcm,
                    "precision": precision.value,
                    "epochs": dynamic_epochs,
                })

        # 6. Execute Parallel Multi-Core SIREN Training Pool
        num_workers = min(hw_profile.recommended_workers, len(worker_tasks))
        with mp.Pool(processes=num_workers) as pool:
            results = pool.map(_isolated_subband_worker, worker_tasks)

        # 7. Assemble Binary Payload & Metadata Manifest
        concatenated_blobs = bytearray()
        for res in results:
            blob_bytes = res["blob"]
            blob_len = len(blob_bytes)

            chunk_manifest_units.append({
                "time_slice_idx": res["chunk_idx"],
                "subband_idx": res["band_idx"],
                "offset": blob_offset,
                "length": blob_len,
            })

            concatenated_blobs.extend(blob_bytes)
            blob_offset += blob_len

        manifest = {
            "hcs_version": "1.0",
            "original": {
                "name": filename,
                "size": len(file_bytes),
                "type": "neural_media",
                "channels": channels,
                "sample_rate": sample_rate,
            },
            "neural": {
                "architecture": "SIREN",
                "codec": "siren",
                "precision": precision.value,
                "hidden_layers": config.SIREN_HIDDEN_LAYERS,
                "hidden_features": config.SIREN_HIDDEN_FEATURES,
                "omega_0": config.SIREN_OMEGA_0,
                "subbands": num_subbands,
                "epochs": dynamic_epochs,
            },
            "metrics": complexity_metrics,
            "chunks": chunk_manifest_units,
        }

        # 8. Pack into .hcs Binary Format
        hcs_bytes = HCSContainer.pack(manifest, bytes(concatenated_blobs))

        # 9. Compute Reconstruction Verification Metrics (SI-SDR / LSD)
        try:
            recon_pcm = cls.resynthesize_audio_from_units(
                chunk_manifest_units,
                [bytes(concatenated_blobs[u["offset"]:u["offset"] + u["length"]]) for u in chunk_manifest_units],
                channels,
                sample_rate,
                precision,
                num_subbands=num_subbands,
                num_chunks=len(chunks),
            )
            metrics = compute_metrics(pcm_data, recon_pcm, sample_rate)
            manifest["metrics"].update(metrics)
            # Repack with computed fidelity metrics
            hcs_bytes = HCSContainer.pack(manifest, bytes(concatenated_blobs))
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
        num_subbands: int,
        num_chunks: int,
    ) -> np.ndarray:
        """Resynthesizes full PCM audio in RAM by evaluating SIREN subband agents in parallel."""
        device = torch.device("cpu")
        samples_per_chunk = int(sample_rate * config.CHUNK_DURATION_SEC)
        t_coords = torch.linspace(-1.0, 1.0, steps=samples_per_chunk, dtype=torch.float32).unsqueeze(-1).to(device)

        reconstructed_chunks = [[] for _ in range(num_chunks)]

        for unit, raw_blob in zip(chunk_units, blob_list):
            c_idx = unit["time_slice_idx"]
            agent = SirenAgent.deserialize_weights(
                raw_blob,
                in_features=1,
                hidden_features=config.SIREN_HIDDEN_FEATURES,
                hidden_layers=config.SIREN_HIDDEN_LAYERS,
                out_features=channels,
                precision=precision,
            ).to(device)

            agent.eval()
            with torch.no_grad():
                pred_pcm = agent(t_coords).cpu().numpy().T

            reconstructed_chunks[c_idx].append(pred_pcm)

        # Synthesize subbands per temporal chunk
        synthesized_temporal_chunks = []
        for band_list in reconstructed_chunks:
            chunk_pcm = SubbandFilterBank.synthesize_subbands(band_list)
            synthesized_temporal_chunks.append(chunk_pcm)

        # Stitch temporal chunks using Overlap-Add crossfade
        full_pcm = TemporalChunker.reconstruct_from_chunks(synthesized_temporal_chunks, sample_rate=sample_rate)
        return full_pcm
