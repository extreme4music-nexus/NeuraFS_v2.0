"""NeuraFS Master Engine Orchestrator, Worker Orchestration, & Validation Suite."""

import hashlib
import math
import multiprocessing as mp
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import scipy.signal as signal
import torch
import torch.nn as nn

from neurafs.core.config import config, PrecisionMode
from neurafs.core.container import HCSContainer
from neurafs.core.dsp import DSPProcessor
from neurafs.core.exceptions import NeuralResynthesisError, AudioAnalysisError
from neurafs.core.codecs.siren import (
    SirenAgent,
    serialize_agent_raw_bytes,
    deserialize_agent_from_bytes,
)


def isolated_subband_worker(
    time_slice_idx: int,
    subband_idx: int,
    ch_idx: int,
    pcm_subband_data: np.ndarray,
    sample_rate: int,
    num_bands: int,
    hidden_dim: int,
    precision: str,
    device_str: str,
    return_dict: Dict[str, Any],
) -> None:
    """Isolated process worker for training a Siren agent on a specific subband chunk."""
    try:
        torch.set_num_threads(1)
        device = torch.device("cuda" if (device_str == "cuda" and torch.cuda.is_available()) else "cpu")

        num_samples = len(pcm_subband_data)
        t_coords = torch.linspace(-1.0, 1.0, steps=num_samples, device=device).unsqueeze(1)
        target_tensor = torch.from_numpy(pcm_subband_data).float().to(device).unsqueeze(1)

        max_steps, target_loss = DSPProcessor.estimate_signal_complexity(
            pcm_subband_data, subband_idx, num_bands
        )

        agent = SirenAgent(
            in_features=1,
            hidden_features=hidden_dim,
            hidden_layers=config.HIDDEN_LAYERS,
            out_features=1,
            omega_0=config.SIREN_OMEGA_0,
        ).to(device)

        optimizer = torch.optim.Adam(agent.parameters(), lr=config.LEARNING_RATE)
        criterion = nn.MSELoss()

        best_loss = 0.999
        patience = 0
        for _ in range(max_steps):
            optimizer.zero_grad()
            pred = agent(t_coords)
            loss = criterion(pred, target_tensor)
            loss.backward()
            optimizer.step()

            c_loss = loss.item()
            if math.isnan(c_loss) or math.isinf(c_loss):
                continue

            if c_loss < best_loss - 1e-5:
                best_loss = c_loss
                patience = 0
            else:
                patience += 1

            if c_loss < target_loss or patience >= config.PATIENCE_LIMIT:
                break

        prec_mode = PrecisionMode.STANDARD_16 if precision == "fp16" else PrecisionMode.HIGH_32
        raw_weight_bytes = serialize_agent_raw_bytes(agent, precision=prec_mode)

        key = f"sub_{time_slice_idx}_{subband_idx}_{ch_idx}"
        return_dict[key] = {
            "time_slice_idx": time_slice_idx,
            "subband_idx": subband_idx,
            "ch_idx": ch_idx,
            "num_samples": num_samples,
            "hidden_dim": hidden_dim,
            "loss": float(np.nan_to_num(best_loss)),
            "raw_bytes": raw_weight_bytes,
        }
    except Exception as err:
        print(f"[Subband Worker Error]: {err}")


class NeuraFSEngine:
    """Master engine performing end-to-end encoding, decoding, and fidelity analysis."""

    @staticmethod
    def calculate_reconstruction_metrics(
        original_audio_np: np.ndarray,
        resynthesized_audio_np: np.ndarray,
        sample_rate: int,
    ) -> Dict[str, float]:
        """Evaluates SI-SDR (Scale-Invariant Signal-to-Distortion Ratio), LSD, and MSE metrics."""
        try:
            min_len = min(len(original_audio_np), len(resynthesized_audio_np))
            s_target = original_audio_np[:min_len, 0]
            s_estimate = resynthesized_audio_np[:min_len, 0]

            # Mean Squared Error (MSE)
            mse = float(np.mean((s_target - s_estimate) ** 2))

            # Scale-Invariant Signal-to-Distortion Ratio (SI-SDR)
            alpha = np.dot(s_estimate, s_target) / (np.dot(s_target, s_target) + 1e-9)
            e_target = alpha * s_target
            e_noise = s_estimate - e_target
            si_sdr = float(10 * np.log10(np.sum(e_target ** 2) / (np.sum(e_noise ** 2) + 1e-9)))

            # Log-Spectral Distance (LSD)
            _, _, stft_orig = signal.stft(s_target, fs=sample_rate, nperseg=512)
            _, _, stft_resyn = signal.stft(s_estimate, fs=sample_rate, nperseg=512)
            lsd = float(
                np.mean(
                    np.sqrt(
                        np.mean(
                            (np.log10(np.abs(stft_orig) + 1e-7) - np.log10(np.abs(stft_resyn) + 1e-7)) ** 2,
                            axis=0,
                        )
                    )
                )
            )

            return {
                "si_sdr_db": round(si_sdr, 2),
                "lsd": round(lsd, 3),
                "mse": round(mse, 6),
            }
        except Exception:
            return {"si_sdr_db": 0.0, "lsd": 0.0, "mse": 0.0}

    @classmethod
    def encode_media(
        cls,
        file_bytes: bytes,
        filename: str,
        precision: PrecisionMode = PrecisionMode.STANDARD_16,
        num_subbands: Optional[int] = None,
        device_str: str = "cpu",
    ) -> bytes:
        """Encodes media file into binary HCS container."""
        original_size = len(file_bytes)
        file_sha256 = hashlib.sha256(file_bytes).hexdigest()

        try:
            audio_np, sample_rate, channels = DSPProcessor.extract_pcm_from_bytes(file_bytes, filename)
        except AudioAnalysisError:
            # Non-audio fallback: Store as lossless binary chunks
            chunk_size = 256 * 1024
            compressed_chunks = [
                file_bytes[i : i + chunk_size] for i in range(0, original_size, chunk_size)
            ]
            manifest = {
                "hcs_version": "1.0",
                "original": {
                    "name": filename,
                    "size": original_size,
                    "sha256": file_sha256,
                    "type": "lossless_binary",
                },
                "neural": {"architecture": "N/A", "precision": precision.value},
                "chunks": [],
            }
            return HCSContainer.pack(manifest, compressed_chunks, precision=precision)

        # Signal Encoding Execution
        if num_subbands is None:
            num_subbands = config.DEFAULT_NUM_SUBBANDS

        hidden_dim = config.HIDDEN_DIM_ARCHIVE if precision == PrecisionMode.HIGH_32 else config.HIDDEN_DIM_COMPACT
        time_chunks = DSPProcessor.chunk_audio(audio_np, sample_rate)

        all_work_units = []
        for slice_idx, pcm_slice in time_chunks:
            for ch in range(channels):
                subband_signals = DSPProcessor.split_into_subbands(pcm_slice[:, ch], sample_rate, num_subbands)
                for sb_idx, sb_pcm in enumerate(subband_signals):
                    all_work_units.append((slice_idx, sb_idx, ch, sb_pcm))

        manager = mp.Manager()
        return_dict = manager.dict()
        max_workers = max(1, mp.cpu_count() - 1)

        for i in range(0, len(all_work_units), max_workers):
            batch = all_work_units[i : i + max_workers]
            procs = [
                mp.Process(
                    target=isolated_subband_worker,
                    args=(
                        unit[0],
                        unit[1],
                        unit[2],
                        unit[3],
                        sample_rate,
                        num_subbands,
                        hidden_dim,
                        precision.value,
                        device_str,
                        return_dict,
                    ),
                )
                for unit in batch
            ]
            for p in procs:
                p.start()
            for p in procs:
                p.join()

        results = [v for k, v in return_dict.items() if k.startswith("sub_")]
        manager.shutdown()

        # Build Extensible Manifest & Raw Payload Buffers
        raw_blobs = []
        chunk_manifests = []
        current_offset = 0

        for unit in results:
            raw_w_bytes = unit.pop("raw_bytes")
            unit["offset"] = current_offset
            unit["length"] = len(raw_w_bytes)
            raw_blobs.append(raw_w_bytes)
            current_offset += len(raw_w_bytes)
            chunk_manifests.append(unit)

        # Run Validation Metrics
        resynthesized_audio = cls.resynthesize_audio_from_units(
            chunk_manifests, raw_blobs, channels, sample_rate, precision
        )
        rec_metrics = cls.calculate_reconstruction_metrics(audio_np, resynthesized_audio, sample_rate)

        manifest = {
            "hcs_version": "1.0",
            "original": {
                "name": filename,
                "size": original_size,
                "samples": len(audio_np),
                "sha256": file_sha256,
                "sample_rate": sample_rate,
                "channels": channels,
                "type": "neural_media",
            },
            "neural": {
                "architecture": "SIREN",
                "precision": precision.value,
                "subbands": num_subbands,
                "hidden_dim": hidden_dim,
                "chunk_duration": config.CHUNK_DURATION_SEC,
            },
            "metrics": rec_metrics,
            "chunks": chunk_manifests,
        }

        return HCSContainer.pack(manifest, raw_blobs, precision=precision)

    @classmethod
    def resynthesize_audio_from_units(
        cls,
        chunk_units: List[Dict[str, Any]],
        raw_blobs: List[bytes],
        channels: int,
        sample_rate: int,
        precision: PrecisionMode,
    ) -> np.ndarray:
        """Reconstructs float PCM audio matrix in memory from subband SIREN units."""
        slices_dict: Dict[int, Dict[int, List[Dict[str, Any]]]] = {}
        blob_map = {unit["offset"]: raw_blobs[i] for i, unit in enumerate(chunk_units)}

        for unit in chunk_units:
            ts, ch = unit["time_slice_idx"], unit["ch_idx"]
            slices_dict.setdefault(ts, {}).setdefault(ch, []).append(unit)

        resynthesized_channels = [[] for _ in range(channels)]
        device = torch.device("cpu")

        for ts_idx in sorted(slices_dict.keys()):
            for ch_idx in range(channels):
                units_in_ch = slices_dict[ts_idx].get(ch_idx, [])
                if not units_in_ch:
                    continue

                num_samples = units_in_ch[0]["num_samples"]
                t_coords = torch.linspace(-1.0, 1.0, steps=num_samples).unsqueeze(1).to(device)
                slice_pcm_sum = np.zeros(num_samples, dtype=np.float32)

                for u in units_in_ch:
                    agent = SirenAgent(
                        in_features=1,
                        hidden_features=u.get("hidden_dim", 32),
                        hidden_layers=config.HIDDEN_LAYERS,
                        out_features=1,
                        omega_0=config.SIREN_OMEGA_0,
                    ).to(device)

                    raw_w_bytes = blob_map[u["offset"]]
                    deserialize_agent_from_bytes(agent, raw_w_bytes, precision=precision)
                    agent.eval()

                    with torch.no_grad():
                        slice_pcm_sum += agent(t_coords).squeeze(1).cpu().numpy()

                resynthesized_channels[ch_idx].append(slice_pcm_sum)

        full_channels = [
            np.concatenate(ch) if ch else np.zeros(100, dtype=np.float32) for ch in resynthesized_channels
        ]
        resyn_audio = np.column_stack(full_channels)
        max_val = np.max(np.abs(resyn_audio))
        if max_val > 1.0:
            resyn_audio /= max_val

        return resyn_audio