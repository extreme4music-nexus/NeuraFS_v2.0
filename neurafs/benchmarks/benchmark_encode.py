"""NeuraFS Phase 8 Encoding Fidelity & Performance Benchmark."""

import time
import io
import numpy as np
import scipy.io.wavfile as wavfile
from neurafs.core.config import PrecisionMode
from neurafs.core.engine import NeuraFSEngine
from neurafs.core.container import HCSContainer


def run_benchmark():
    print("--- Running NeuraFS Phase 8 Engine Benchmark ---")

    # 1. Generate multi-frequency stereo audio signal for testing
    sr = 44100
    duration = 2.5
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    ch1 = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.25 * np.sin(2 * np.pi * 880 * t)
    ch2 = 0.4 * np.sin(2 * np.pi * 330 * t) + 0.3 * np.sin(2 * np.pi * 660 * t)
    pcm_stereo = np.vstack([ch1, ch2]).astype(np.float32)

    byte_io = io.BytesIO()
    wavfile.write(byte_io, sr, (pcm_stereo.T * 32767).astype(np.int16))
    raw_wav_bytes = byte_io.getvalue()
    orig_size_kb = len(raw_wav_bytes) / 1024.0

    # 2. Benchmark Encode Latency & Neural Synthesis
    start_time = time.time()
    hcs_bytes = NeuraFSEngine.encode_media(
        raw_wav_bytes, filename="benchmark_test.wav", precision=PrecisionMode.STANDARD_16
    )
    encode_latency = time.time() - start_time

    container_size_kb = len(hcs_bytes) / 1024.0
    space_saved = (1.0 - (container_size_kb / orig_size_kb)) * 100.0

    manifest, _ = HCSContainer.unpack(hcs_bytes)
    metrics = manifest.get("metrics", {})

    print(f"Original Size:    {orig_size_kb:.2f} KB")
    print(f"Container Size:   {container_size_kb:.2f} KB ({space_saved:.1f}% space saved)")
    print(f"Encode Latency:   {encode_latency:.2f} seconds")
    print(f"Subbands Used:    {manifest['neural'].get('subbands')}")
    print(f"Dynamic Epochs:   {manifest['neural'].get('epochs')}")
    print(f"Fidelity Metrics: {metrics}")


if __name__ == "__main__":
    run_benchmark()
