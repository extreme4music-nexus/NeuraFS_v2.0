"""NeuraFS Analytical Quality Metrics Suite."""

import numpy as np
import scipy.signal as signal


def calculate_si_sdr(target: np.ndarray, estimate: np.ndarray) -> float:
    """Calculates Scale-Invariant Signal-to-Distortion Ratio (SI-SDR) in dB."""
    min_len = min(len(target), len(estimate))
    s_target = target[:min_len]
    s_estimate = estimate[:min_len]

    alpha = np.dot(s_estimate, s_target) / (np.dot(s_target, s_target) + 1e-9)
    e_target = alpha * s_target
    e_noise = s_estimate - e_target

    si_sdr = 10 * np.log10(np.sum(e_target ** 2) / (np.sum(e_noise ** 2) + 1e-9))
    return float(si_sdr)


def calculate_lsd(target: np.ndarray, estimate: np.ndarray, sample_rate: int = 44100) -> float:
    """Calculates Log-Spectral Distance (LSD) between original and synthesized signals."""
    min_len = min(len(target), len(estimate))
    _, _, stft_target = signal.stft(target[:min_len], fs=sample_rate, nperseg=512)
    _, _, stft_est = signal.stft(estimate[:min_len], fs=sample_rate, nperseg=512)

    lsd = np.mean(
        np.sqrt(
            np.mean(
                (np.log10(np.abs(stft_target) + 1e-7) - np.log10(np.abs(stft_est) + 1e-7)) ** 2,
                axis=0,
            )
        )
    )
    return float(lsd)