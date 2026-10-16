"""NeuraFS Analytical Quality Metrics Suite."""

import numpy as np
import scipy.signal as signal


def calculate_si_sdr(target: np.ndarray, estimate: np.ndarray) -> float:
    """Calculates Scale-Invariant Signal-to-Distortion Ratio (SI-SDR) in dB."""
    s_target = target.flatten()
    s_estimate = estimate.flatten()
    min_len = min(len(s_target), len(s_estimate))
    s_target = s_target[:min_len]
    s_estimate = s_estimate[:min_len]

    alpha = np.dot(s_estimate, s_target) / (np.dot(s_target, s_target) + 1e-9)
    e_target = alpha * s_target
    e_noise = s_estimate - e_target

    si_sdr = 10 * np.log10(np.sum(e_target ** 2) / (np.sum(e_noise ** 2) + 1e-9))
    return float(si_sdr)


def calculate_lsd(target: np.ndarray, estimate: np.ndarray, sample_rate: int = 44100) -> float:
    """Calculates Log-Spectral Distance (LSD) between original and synthesized signals."""
    s_target = target.flatten()
    s_estimate = estimate.flatten()
    min_len = min(len(s_target), len(s_estimate))
    _, _, stft_target = signal.stft(s_target[:min_len], fs=sample_rate, nperseg=512)
    _, _, stft_est = signal.stft(s_estimate[:min_len], fs=sample_rate, nperseg=512)

    lsd = np.mean(
        np.sqrt(
            np.mean(
                (np.log10(np.abs(stft_target) + 1e-7) - np.log10(np.abs(stft_est) + 1e-7)) ** 2,
                axis=0,
            )
        )
    )
    return float(lsd)


def compute_mse(reference: np.ndarray, estimate: np.ndarray) -> float:
    """Calculates Mean Squared Error (MSE) between reference and estimated audio signals."""
    ref = reference.flatten()
    est = estimate.flatten()
    min_len = min(len(ref), len(est))
    if min_len == 0:
        return 0.0
    return float(np.mean((ref[:min_len] - est[:min_len]) ** 2))


def compute_metrics(reference: np.ndarray, estimate: np.ndarray, sample_rate: int = 44100) -> dict[str, float]:
    """Unified wrapper computing complete fidelity metrics dictionary (SI-SDR, LSD, MSE)."""
    si_sdr = calculate_si_sdr(reference, estimate)
    lsd = calculate_lsd(reference, estimate, sample_rate)
    mse = compute_mse(reference, estimate)
    
    return {
        "si_sdr_db": round(si_sdr, 2),
        "lsd": round(lsd, 4),
        "mse": round(mse, 6),
    }