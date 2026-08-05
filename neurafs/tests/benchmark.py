"""NeuraFS Performance, Compression Ratio, & Latency Benchmark Script."""

import time
import os
import psutil
import tempfile
import numpy as np
import scipy.io.wavfile as wavfile

from neurafs.sdk.python.sdk import NeuraFSSDK


def run_benchmark():
    """Measures encoding speed, decoding latency, memory footprint, and compression ratios."""
    print("==========================================================")
    print(" NeuraFS Cross-Platform Engine Benchmark Suite")
    print("==========================================================")

    # Generate 5-second multi-frequency test signal
    sample_rate = 44100
    duration = 5.0
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    signal_data = np.sin(2 * np.pi * 440 * t) + 0.5 * np.sin(2 * np.pi * 1200 * t)
    pcm_int16 = (signal_data * 16383.0).astype(np.int16)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        wavfile.write(tmp_wav.name, sample_rate, pcm_int16)
        input_wav = tmp_wav.name

    input_size = os.path.getsize(input_wav)
    output_hcs = input_wav + ".hcs"
    output_resyn = input_wav + "_rec.wav"

    try:
        # 1. Benchmark Encoding
        process = psutil.Process(os.getpid())
        ram_start = process.memory_info().rss / (1024 * 1024)

        t_start = time.perf_counter()
        enc_res = NeuraFSSDK.encode_file(input_wav, output_hcs, precision="fp16")
        enc_time = time.perf_counter() - t_start

        ram_peak = (process.memory_info().rss / (1024 * 1024)) - ram_start
        hcs_size = os.path.getsize(output_hcs)
        ratio = (1 - (hcs_size / input_size)) * 100

        # 2. Benchmark First-Chunk Decoding Latency
        t_start_dec = time.perf_counter()
        NeuraFSSDK.decode_to_wav(output_hcs, output_resyn)
        dec_time = time.perf_counter() - t_start_dec

        metrics = enc_res["manifest"].get("metrics", {})

        print(f"[*] Input File Size:        {input_size / 1024:.2f} KB")
        print(f"[*] Container Size (.hcs):  {hcs_size / 1024:.2f} KB")
        print(f"[*] Space Savings Ratio:    {ratio:.1f}%")
        print(f"[*] Encoding Latency:       {enc_time:.2f} seconds")
        print(f"[*] Decoding Latency:       {dec_time:.3f} seconds")
        print(f"[*] Peak RAM Delta:         {ram_peak:.2f} MB")
        print(f"[*] Signal Quality (SI-SDR): {metrics.get('si_sdr_db', 0.0)} dB")
        print(f"[*] Spectral Distance (LSD): {metrics.get('lsd', 0.0)}")
        print("==========================================================")

    finally:
        for p in [input_wav, output_hcs, output_resyn]:
            if os.path.exists(p):
                os.remove(p)


if __name__ == "__main__":
    run_benchmark()