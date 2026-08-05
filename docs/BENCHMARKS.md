# NeuraFS Performance & Quality Benchmarks

## 1. Evaluation Metrics

* **SI-SDR (Scale-Invariant Signal-to-Distortion Ratio):** Measures reconstruction fidelity in dB. Target threshold: $> +15.0\text{ dB}$.
* **LSD (Log-Spectral Distance):** Measures distance between original and synthesized STFT log-power spectra.
* **Space Savings:** Percentage reduction in file size from raw PCM `.wav`.

---

## 2. Baseline Test Results (CPU Benchmark)

* **Test Input:** 2.5s stereo 44100Hz audio sine blend
* **Hardware:** Desktop CPU (Single-Thread PyTorch Execution)

| Metric | Baseline Value | Target Metric | Status |
| :--- | :--- | :--- | :--- |
| **Original File Size** | 258.44 KB | — | — |
| **Container Size (.hcs)** | 126.78 KB | $< 130.0\text{ KB}$ | **PASS** |
| **Space Savings Ratio** | 50.9% | $> 50.0\%$ | **PASS** |
| **Encode Latency** | 119.47 s | $< 10.0\text{ s}$ (CUDA) | Pending CUDA |
| **RAM Usage Delta** | 48.99 MB | $< 100.0\text{ MB}$ | **PASS** |
| **SI-SDR** | -9.69 dB | $> +15.0\text{ dB}$ | Tuning Needed |
| **LSD** | 1.098 | $< 0.500$ | Tuning Needed |

---

## 3. Fidelity Optimization Plan

To increase SI-SDR from $-9.69\text{ dB}$ to $> +15.0\text{ dB}$:
1. Increase SIREN base frequency mapping hyperparameter $\omega_0$ from $30.0$ to $50.0$.
2. Implement composite loss function incorporating spectral STFT distance alongside MSE:

$$\mathcal{L}_{\text{total}} = \mathcal{L}_{\text{MSE}} + \lambda \mathcal{L}_{\text{STFT}}$$