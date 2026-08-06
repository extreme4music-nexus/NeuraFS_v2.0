"""NeuraFS Dynamic Subband Butterworth Filter Bank Module (Numerically Stable SOS)."""

import numpy as np
from scipy.signal import butter, sosfiltfilt
from typing import List, Tuple


class SubbandFilterBank:
    """Decomposes continuous PCM signals into phase-preserved frequency subbands using SOS IIR filters."""

    @staticmethod
    def calculate_logarithmic_cutoffs(num_bands: int, sample_rate: int = 44100) -> List[Tuple[float, float]]:
        """Calculates band frequency boundaries mapped logarithmically (Log-scale)."""
        nyquist = sample_rate / 2.0
        min_freq = 20.0
        max_freq = min(20000.0, nyquist - 100.0)

        log_edges = np.logspace(np.log10(min_freq), np.log10(max_freq), num_bands + 1)
        bands = []
        for i in range(num_bands):
            bands.append((float(log_edges[i]), float(log_edges[i + 1])))
        return bands

    @classmethod
    def decompose_subbands(
        cls, pcm_data: np.ndarray, num_bands: int, sample_rate: int = 44100
    ) -> Tuple[List[np.ndarray], List[Tuple[float, float]]]:
        """Filters input PCM into N logarithmic subbands using zero-phase SOS Butterworth filters."""
        nyquist = sample_rate / 2.0
        cutoff_pairs = cls.calculate_logarithmic_cutoffs(num_bands, sample_rate)
        subbands = []

        is_stereo = pcm_data.ndim > 1

        for low, high in cutoff_pairs:
            low_norm = max(0.001, low / nyquist)
            high_norm = min(0.999, high / nyquist)

            # Use Second-Order Sections (SOS) for numerical stability in floating-point math
            sos = butter(N=4, Wn=[low_norm, high_norm], btype="bandpass", output="sos")

            if is_stereo:
                filtered_ch0 = sosfiltfilt(sos, pcm_data[0])
                filtered_ch1 = sosfiltfilt(sos, pcm_data[1])
                band_pcm = np.vstack([filtered_ch0, filtered_ch1]).astype(np.float32)
            else:
                band_pcm = sosfiltfilt(sos, pcm_data).astype(np.float32)

            subbands.append(band_pcm)

        return subbands, cutoff_pairs

    @staticmethod
    def synthesize_subbands(subband_list: List[np.ndarray]) -> np.ndarray:
        """Reconstructs full-spectrum audio waveform by summing phase-aligned subbands."""
        return np.sum(subband_list, axis=0)