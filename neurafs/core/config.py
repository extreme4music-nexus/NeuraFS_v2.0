"""NeuraFS Dynamic Hardware, Resource Orchestration & Quality Configuration Module."""

import os
from enum import Enum
from dataclasses import dataclass
from typing import Tuple
import psutil
import torch


class PrecisionMode(Enum):
    STANDARD_16 = "fp16"
    HIGH_32 = "fp32"


class DecodeMode(Enum):
    OFFLINE_LOSSLESS = "offline_lossless"    # Complete recovery of original fidelity (takes longer on weak HW)
    REALTIME_ADAPTIVE = "realtime_adaptive"  # Zero-latency RAM stream (degrades quality if HW is bottlenecked)


class TargetQualityTier(Enum):
    HI_RES = "hi_res"        # 48000 Hz / Float32 (High precision)
    STANDARD = "standard"    # 44100 Hz / Int16 (Standard Hi-Fi)
    FALLBACK = "fallback"    # 22050 Hz / Int16 (Low-spec streaming survival mode)


@dataclass
class HardwareProfile:
    """Dataclass holding real-time system capability metrics."""
    cpu_logical_cores: int
    cpu_physical_cores: int
    total_ram_gb: float
    available_ram_gb: float
    has_cuda: bool
    cuda_device_name: str
    cuda_vram_gb: float
    has_mps: bool
    recommended_workers: int
    estimated_worker_ram_mb: float
    is_low_spec: bool


class EngineConfig:
    """Dynamic configuration and policy orchestrator for NeuraFS."""

    DEFAULT_SAMPLE_RATE: int = 44100
    CHUNK_DURATION_SEC: float = 2.5

    # Dynamic Subband Bounds (Adapts to audio complexity & available workers)
    MIN_SUBBANDS: int = 2
    MAX_SUBBANDS: int = 8

    # Dynamic Training Epoch Bounds (Scales linearly with complexity score 0.0 -> 1.0)
    MIN_EPOCHS: int = 50
    BASE_EPOCHS: int = 150
    MAX_EPOCHS: int = 400

    # SIREN Model Tuned Hyperparameters
    SIREN_HIDDEN_LAYERS: int = 3
    SIREN_HIDDEN_FEATURES: int = 64
    SIREN_OMEGA_0: float = 50.0  # Tuned base frequency scaling for audio

    @classmethod
    def estimate_worker_ram_mb(cls, precision: PrecisionMode = PrecisionMode.STANDARD_16) -> float:
        """Dynamically calculates estimated RAM consumption per isolated worker process."""
        bytes_per_sample = 2 if precision == PrecisionMode.STANDARD_16 else 4
        pcm_samples_per_chunk = int(cls.DEFAULT_SAMPLE_RATE * cls.CHUNK_DURATION_SEC * 2)  # Stereo
        raw_pcm_mb = (pcm_samples_per_chunk * bytes_per_sample) / (1024 * 1024)
        
        # Base PyTorch process overhead (~45MB) + Model parameter gradients & DSP buffer
        pytorch_overhead_mb = 45.0
        model_state_mb = (cls.SIREN_HIDDEN_LAYERS * (cls.SIREN_HIDDEN_FEATURES ** 2) * bytes_per_sample * 4) / (1024 * 1024)
        
        # Dynamic total + 30% safety margin buffer
        total_estimated_mb = (raw_pcm_mb + pytorch_overhead_mb + model_state_mb) * 1.3
        return round(total_estimated_mb, 2)

    @classmethod
    def scan_hardware(cls, precision: PrecisionMode = PrecisionMode.STANDARD_16) -> HardwareProfile:
        """Scans host system resources (CPU, RAM, GPU/VRAM) to build dynamic hardware profile."""
        logical_cores = os.cpu_count() or 4
        physical_cores = psutil.cpu_count(logical=False) or logical_cores

        virtual_mem = psutil.virtual_memory()
        total_ram_gb = virtual_mem.total / (1024 ** 3)
        available_ram_gb = virtual_mem.available / (1024 ** 3)

        has_cuda = torch.cuda.is_available()
        cuda_name = torch.cuda.get_device_name(0) if has_cuda else "None"
        cuda_vram_gb = (
            torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            if has_cuda
            else 0.0
        )
        has_mps = (
            hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        )

        # Dynamic calculation of RAM requirement per worker
        worker_ram_mb = cls.estimate_worker_ram_mb(precision)
        available_ram_mb = available_ram_gb * 1024
        
        ram_worker_limit = max(1, int(available_ram_mb / worker_ram_mb))
        recommended_workers = max(1, min(logical_cores, ram_worker_limit))

        # Flag system as low-spec if available RAM < 2.5GB or CPU logical cores <= 2
        is_low_spec = (available_ram_gb < 2.5) or (logical_cores <= 2)

        return HardwareProfile(
            cpu_logical_cores=logical_cores,
            cpu_physical_cores=physical_cores,
            total_ram_gb=round(total_ram_gb, 2),
            available_ram_gb=round(available_ram_gb, 2),
            has_cuda=has_cuda,
            cuda_device_name=cuda_name,
            cuda_vram_gb=round(cuda_vram_gb, 2),
            has_mps=has_mps,
            recommended_workers=recommended_workers,
            estimated_worker_ram_mb=worker_ram_mb,
            is_low_spec=is_low_spec,
        )

    @classmethod
    def calculate_dynamic_subbands(cls, complexity_score: float, available_workers: int) -> int:
        """Calculates subband count using a smooth continuous interpolation function.
        
        Formula: Subbands = round(MIN + complexity_score * (MAX - MIN))
        Bounded strictly by MIN_SUBBANDS, MAX_SUBBANDS, and available worker thread pool.
        """
        score = max(0.0, min(1.0, complexity_score))
        continuous_bands = round(cls.MIN_SUBBANDS + score * (cls.MAX_SUBBANDS - cls.MIN_SUBBANDS))
        
        # Clamp to hardware limits and configuration bounds
        target_bands = min(continuous_bands, available_workers)
        return max(cls.MIN_SUBBANDS, min(cls.MAX_SUBBANDS, target_bands))

    @classmethod
    def calculate_dynamic_epochs(cls, subband_complexity: float) -> int:
        """Calculates SIREN training iterations for a specific subband based on continuous complexity."""
        score = max(0.0, min(1.0, subband_complexity))
        epochs = int(cls.MIN_EPOCHS + (cls.MAX_EPOCHS - cls.MIN_EPOCHS) * score)
        return epochs

    @classmethod
    def resolve_decode_tier(
        cls, decode_mode: DecodeMode, profile: HardwareProfile, orig_sample_rate: int
    ) -> Tuple[int, TargetQualityTier]:
        """Resolves target sample rate & quality tier dynamically based on decode intent and hardware."""
        if decode_mode == DecodeMode.OFFLINE_LOSSLESS:
            # Context menu "Decompress" -> 100% original fidelity regardless of CPU load
            tier = TargetQualityTier.HI_RES if orig_sample_rate >= 48000 else TargetQualityTier.STANDARD
            return orig_sample_rate, tier

        # REALTIME_ADAPTIVE Streaming mode -> Graceful quality fallback if hardware is low-spec
        if profile.is_low_spec:
            return 22050, TargetQualityTier.FALLBACK
        elif profile.recommended_workers < 4:
            return 44100, TargetQualityTier.STANDARD
        else:
            return orig_sample_rate, TargetQualityTier.HI_RES

    @classmethod
    def get_compute_device(cls) -> torch.device:
        """Selects the optimal PyTorch compute device."""
        if torch.cuda.is_available():
            return torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")


config = EngineConfig()
