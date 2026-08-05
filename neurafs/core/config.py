"""NeuraFS Engine Global Configuration Specifications."""

from dataclasses import dataclass
from enum import Enum


class PrecisionMode(str, Enum):
    STANDARD_16 = "fp16"  # Standard 16-bit precision mode
    HIGH_32 = "fp32"      # High precision 32-bit archive mode


@dataclass(frozen=True)
class EngineConfig:
    # Auto-Adaptation & DSP Profiling
    AUTO_SAMPLE_RATE_DETECTION: bool = True
    AUTO_COMPLEXITY_ADAPTATION: bool = True
    
    # Audio & DSP Defaults
    DEFAULT_SAMPLE_RATE: int = 44100
    CHANNELS: int = 2
    CHUNK_DURATION_SEC: float = 2.5
    DEFAULT_NUM_SUBBANDS: int = 8
    
    # SIREN Neural Architecture & Precision Modes
    DEFAULT_PRECISION: PrecisionMode = PrecisionMode.STANDARD_16
    SIREN_OMEGA_0: float = 45.0
    HIDDEN_DIM_COMPACT: int = 32
    HIDDEN_DIM_ARCHIVE: int = 48
    HIDDEN_LAYERS: int = 2
    
    # Dynamic Optimization Constraints
    LEARNING_RATE: float = 1e-3
    PATIENCE_LIMIT: int = 12
    MIN_TRAINING_STEPS: int = 30
    MAX_TRAINING_STEPS: int = 200
    
    # Binary Protocol Specification
    MAGIC_HEADER: bytes = b'HCS1'
    FORMAT_VERSION_FLAGS: bytes = b'\x00\x00\x00\x01'
    LZMA_PRESET: int = 9


config = EngineConfig()