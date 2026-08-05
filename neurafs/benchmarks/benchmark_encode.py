"""NeuraFS Encoding Performance Benchmark."""

import time
import os
import psutil
import tempfile
import numpy as np
import scipy.io.wavfile as wavfile

from neurafs.sdk import NeuraFSSDK
from neurafs.benchmarks.metrics import calculate_si_sdr, calculate_lsd


def run_encode_benchmark():
    print("--- NeuraFS Encoding Benchmark ---")
    sr = 44100
    duration = 3.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = 0.6 * np.sin(2 * np.pi * 440 * t) + 0.3 * np.sin(2 * np.pi * 880 * t)
    pcm_int16 = (audio * 32767.0).astype(np.int16)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wavfile.write(tmp.name, sr, pcm_int16)
        in_wav = tmp.name

    out_hcs = in_wav + ".hcs"

    try:
        proc = psutil.Process(os.getpid())
        mem_before = proc.memory_info().rss / (1024 * 1024)

        start_t = time.perf_counter()
        res = NeuraFSSDK.encode_file(in_wav, out_hcs, precision="fp16")
        enc_time = time.perf_counter() - start_t

        mem_after = proc.memory_info().rss / (1024 * 1024)

        orig_size = os.path.getsize(in_wav)
        comp_size = os.path.getsize(out_hcs)
        saving = (1 - (comp_size / orig_size)) * 100

        print(f"Original Size:     {orig_size / 1024:.2f} KB")
        print(f"Container Size:    {comp_size / 1024:.2f} KB ({saving:.1f}% space saved)")
        print(f"Encode Latency:    {enc_time:.2f} seconds")
        print(f"RAM Usage Delta:   {mem_after - mem_before:.2f} MB")
        print(f"Metrics:           {res['manifest'].get('metrics', {})}")
    finally:
        for p in [in_wav, out_hcs]:
            if os.path.exists(p):
                os.remove(p)


if __name__ == "__main__":
    run_encode_benchmark()