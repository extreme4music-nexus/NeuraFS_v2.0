# NeuraFS System Architecture & Pipeline

## 1. System Layer Hierarchy

+-------------------------------------------------------+
| User Interfaces: Web Explorer UI | CLI Utility        |
+-------------------------------------------------------+
| Virtual Drivers: Linux FUSE | WinFSP | Samba VFS C    |
+-------------------------------------------------------+
| Application SDKs: Python SDK | Node.js Express SDK    |
+-------------------------------------------------------+
| Async REST API Gateway (FastAPI Service)              |
+-------------------------------------------------------+
| Virtual File System (VFS RAM Streamer & Inspector)    |
+-------------------------------------------------------+
| Core Neural Engine: Codecs (SIREN, FutureCodec) & DSP |
+-------------------------------------------------------+


---

## 2. Encoding Pipeline Workflow

1. **Audio Ingestion & DSP:** Input `.wav` audio is loaded into RAM and split into uniform time-slice chunks via `DSPProcessor`.
2. **Implicit Neural Parameterization:** Each audio chunk is fitted by a `SirenAgent` neural network using sinusoidal activation functions $f(x) = \sin(\omega_0 \cdot (Wx + b))$.
3. **Weight Serializing & Quantization:** Model weights are converted to target precision (`fp16` or `fp32`) and packed into contiguous byte streams.
4. **Container Packing:** Manifest JSON is constructed, combined with LZMA-compressed weight blobs, and wrapped with the 12-byte `HCS1` header by `HCSContainer`.

---

## 3. Extensible Codec Architecture

NeuraFS abstracts neural synthesis behind the `BaseNeuralCodec` interface (`neurafs/core/codecs/future_codec.py`). New architectures (e.g., DAC, EnCodec, RVQ) can be integrated by inheriting from `BaseNeuralCodec` and registering with `register_codec()`.