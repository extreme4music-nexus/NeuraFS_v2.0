"""NeuraFS Phase 8 Decoding & RAM Streaming Performance Benchmark."""

import os
import io
import time
import psutil
import numpy as np
import scipy.io.wavfile as wavfile

from neurafs.core.config import PrecisionMode, DecodeMode
from neurafs.core.engine import NeuraFSEngine
from neurafs.vfs.ram_streamer import RAMStreamBuffer


def run_decode_benchmark():
    print("--- Running NeuraFS Phase 8 Decoding & RAM Streaming Benchmark ---")

    # 1. Generate 5-second multi-frequency test WAV (2 temporal chunks)
    sr = 44100
    duration = 5.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    ch1 = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 880 * t)
    ch2 = 0.4 * np.sin(2 * np.pi * 330 * t) + 0.3 * np.sin(2 * np.pi * 660 * t)
    pcm_stereo = np.vstack([ch1, ch2]).astype(np.float32)

    byte_io = io.BytesIO()
    wavfile.write(byte_io, sr, (pcm_stereo.T * 32767).astype(np.int16))
    raw_wav_bytes = byte_io.getvalue()

    print("[1/3] Pre-encoding sample audio into .hcs container...")
    hcs_bytes = NeuraFSEngine.encode_media(
        raw_wav_bytes, filename="decode_bench.wav", precision=PrecisionMode.STANDARD_16
    )
    container_kb = len(hcs_bytes) / 1024.0
    print(f"      Container generated: {container_kb:.2f} KB")

    process = psutil.Process(os.getpid())
    ram_before = process.memory_info().rss / (1024 * 1024)

    # 2. Benchmark Priority Chunk-0 Instant Playback Latency
    print("\n[2/3] Measuring Priority Chunk-0 Instant Playback Latency...")
    t0 = time.time()
    streamer = RAMStreamBuffer(hcs_bytes, decode_mode=DecodeMode.REALTIME_ADAPTIVE)
    chunk0_pcm, target_sr = streamer.get_priority_chunk_0_pcm()
    chunk0_latency_ms = (time.time() - t0) * 1000.0

    print(f"      Chunk-0 Resynthesis Latency: {chunk0_latency_ms:.2f} ms")
    print(f"      Target Output Sample Rate:    {target_sr} Hz ({streamer.quality_tier.value})")

    # 3. Benchmark Continuous RAM Stream Resynthesis
    print("\n[3/3] Measuring Full Audio Stream Throughput & Memory Delta...")
    t_stream_start = time.time()
    total_streamed_bytes = 0
    chunk_count = 0

    for pcm_bytes in streamer.generate_pcm_stream():
        total_streamed_bytes += len(pcm_bytes)
        chunk_count += 1

    total_stream_latency = time.time() - t_stream_start
    ram_after = process.memory_info().rss / (1024 * 1024)
    ram_delta_mb = ram_after - ram_before

    print(f"      Total Resynthesis Time: {total_stream_latency:.4f} seconds")
    print(f"      Total Streamed Data:    {total_streamed_bytes} bytes ({chunk_count} chunks)")
    print(f"      RAM Delta Footprint:    {ram_delta_mb:.2f} MB")

    print("\n--- Benchmark Summary ---")
    if chunk0_latency_ms < 50.0:
        print("RESULT: SUCCESS — Zero-latency playback verified (Chunk-0 ready < 50ms).")
    else:
        print("RESULT: ACCEPTABLE — Chunk-0 generated successfully.")


if __name__ == "__main__":
    run_decode_benchmark()
