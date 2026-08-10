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

neurafs benchmark X:\media\proba.wav.hcs
usage: neurafs [-h]
               {init,start,stop,restart,status,service,encode,decode,inspect,api,web,benchmark,storage,vfs,log} ...
neurafs: error: unrecognized arguments: X:\media\proba.wav.hcs
PS C:\WINDOWS\system32> neurafs inspect X:\media\proba.wav.hcs
[NeuraFS Auto-Healing] Background services offline. Auto-recovering...

🚀 --- Starting NeuraFS Ecosystem Services ---
[1/4] Mounting Virtual File System Partition...
[2/4] Launching FastAPI Core Neural Engine (Port 8000)...
[NeuraFS API] Server is already running (PID: 22308).
[3/4] Launching Express Web Explorer Dashboard (Port 3000)...
[NeuraFS Web] Web server is already running (PID: 32188).
[4/4] Synchronizing Samba Network VFS Sharing...
[NeuraFS Watcher] Launching Background File Watcher...
[NeuraFS Watcher] Background daemon already running.

✨ All NeuraFS background services active & Master Boot Persistence registered!
{
  "hcs_version": "1.0",
  "original": {
    "name": "proba.wav",
    "size": 654536,
    "type": "neural_media",
    "channels": 2,
    "sample_rate": 44100
  },
  "neural": {
    "architecture": "SIREN",
    "codec": "siren",
    "precision": "fp16",
    "hidden_layers": 3,
    "hidden_features": 64,
    "omega_0": 50.0,
    "subbands": 4,
    "epochs": 169
  },
  "metrics": {
    "complexity_score": 0.3401,
    "spectral_entropy": 0.5557,
    "spectral_flatness": 0.0025,
    "transient_density": 0.4717,
    "crest_factor": 0.18050000071525574
  },
  "chunks": [
    {
      "time_slice_idx": 0,
      "subband_idx": 0,
      "offset": 0,
      "length": 25656
    },
    {
      "time_slice_idx": 0,
      "subband_idx": 1,
      "offset": 25656,
      "length": 25656
    },
    {
      "time_slice_idx": 0,
      "subband_idx": 2,
      "offset": 51312,
      "length": 25656
    },
    {
      "time_slice_idx": 0,
      "subband_idx": 3,
      "offset": 76968,
      "length": 25656
    },
    {
      "time_slice_idx": 1,
      "subband_idx": 0,
      "offset": 102624,
      "length": 25656
    },
    {
      "time_slice_idx": 1,
      "subband_idx": 1,
      "offset": 128280,
      "length": 25656
    },
    {
      "time_slice_idx": 1,
      "subband_idx": 2,
      "offset": 153936,
      "length": 25656
    },
    {
      "time_slice_idx": 1,
      "subband_idx": 3,
      "offset": 179592,
      "length": 25656
    }
  ]
}