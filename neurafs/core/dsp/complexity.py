"""NeuraFS Multi-Factor Spectral & Temporal Audio Complexity Analyzer."""

import numpy as np
from scipy.fft import rfft
from scipy.signal import find_peaks
from typing import Dict


class SpectralComplexityAnalyzer:
    """Evaluates multi-dimensional mathematical complexity of PCM audio signals."""

    @staticmethod
    def compute_spectral_entropy(magnitude_spectrum: np.ndarray) -> float:
        """Calculates Spectral Entropy to measure frequency distribution randomness."""
        power = magnitude_spectrum ** 2
        total_power = np.sum(power)
        if total_power < 1e-12:
            return 0.0
        prob = power / total_power
        prob = prob[prob > 0]
        entropy = -np.sum(prob * np.log2(prob))
        max_entropy = np.log2(len(magnitude_spectrum))
        return float(entropy / max_entropy) if max_entropy > 0 else 0.0

    @staticmethod
    def compute_spectral_flatness(magnitude_spectrum: np.ndarray) -> float:
        """Calculates Spectral Flatness (Ratio of Geometric to Arithmetic mean)."""
        power = magnitude_spectrum ** 2 + 1e-12
        geometric_mean = np.exp(np.mean(np.log(power)))
        arithmetic_mean = np.mean(power)
        return float(geometric_mean / arithmetic_mean)

    @staticmethod
    def compute_transient_density(pcm_mono: np.ndarray, frame_size: int = 1024) -> float:
        """Measures the rate of sharp attack transients across temporal frames."""
        num_frames = len(pcm_mono) // frame_size
        if num_frames < 2:
            return 0.0
        
        frames = pcm_mono[:num_frames * frame_size].reshape(num_frames, frame_size)
        energies = np.sum(frames ** 2, axis=1)
        energy_diffs = np.diff(energies)
        transients, _ = find_peaks(energy_diffs, height=np.std(energy_diffs) * 1.5)
        return float(min(1.0, len(transients) / (num_frames / 10.0)))

    @classmethod
    def analyze_complexity(cls, pcm_data: np.ndarray) -> Dict[str, float]:
        """Executes full multi-factor spectral analysis on PCM array.
        
        Returns dictionary of individual acoustic metrics and final composite score (0.0 -> 1.0).
        """
        pcm_mono = pcm_data[0] if pcm_data.ndim > 1 else pcm_data
        if len(pcm_mono) == 0 or np.all(pcm_mono == 0):
            return {"complexity_score": 0.0, "entropy": 0.0, "flatness": 0.0, "transients": 0.0}

        # Compute Real FFT for Frequency Domain Metrics
        fft_mag = np.abs(rfft(pcm_mono[:65536]))  # Analyze first block for fast score
        
        entropy = cls.compute_spectral_entropy(fft_mag)
        flatness = cls.compute_spectral_flatness(fft_mag)
        transients = cls.compute_transient_density(pcm_mono)
        
        # Calculate Peak-to-RMS Ratio (Dynamic Range Factor)
        rms = np.sqrt(np.mean(pcm_mono ** 2)) + 1e-12
        peak = np.max(np.abs(pcm_mono))
        crest_factor = min(1.0, (peak / rms) / 20.0)

        # Composite Weighted Complexity Score
        composite_score = (
            0.35 * entropy +
            0.25 * flatness +
            0.25 * transients +
            0.15 * crest_factor
        )
        
        final_score = float(np.clip(composite_score, 0.0, 1.0))

        return {
            "complexity_score": round(final_score, 4),
            "spectral_entropy": round(entropy, 4),
            "spectral_flatness": round(flatness, 4),
            "transient_density": round(transients, 4),
            "crest_factor": round(crest_factor, 4)
        }
