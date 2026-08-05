GOALS.md — NeuraFS Architecture & Roadmap
1. Project Vision
NeuraFS is an experimental Virtual Neural Media File System that represents media signals (initially MP3/WAV audio) using IMPLICIT SIGNAL REPRESENTATION (SIREN/INR networks) stored in a custom binary container (.hcs). The system enables instant preview, RAM decompression, and direct streaming without needing to decompress the entire file to disk beforehand.
2. Development Phases (Step-by-Step Roadmap)
Phase 1: Core Engine & Standard HCS Container (Foundation)
Isolated Python Engine: Central module for DSP analysis (Subband decomposition), SIREN optimization, and PyTorch inference.
File Support:
Media files (MP3 focus): Split into subbands and 2.5-second chunks represented via neural weights.
Binary/Document files (Fallback): Standard lossless LZMA binary packaging inside the HCS container.
HCS Format Specification: Standardization of binary layout (Magic Header + Metadata Manifest + Raw FP16 Blobs).
Backward/Forward Compatibility: Dynamic router in the engine that reads version specifications (HCS1, HCS2, HCS3) and enables opening older containers without breaking the system.
Phase 2: API Layer
FastAPI Backend Server: Isolated server layer with asynchronous endpoints (/api/v1/encode-neural-media-start, /api/v1/resynthesize-neural-media, /api/fs/stream).
Task & Worker Management: Processing via multiprocessing with proper CPU/GPU orchestration.
Phase 3: SDK Layer
Node.js & Python SDK: Standalone software development kit (hyper-compress-sdk.js) managing packaging, inspection, and fast in-memory decompression of .hcs files.
Phase 4: Virtual File System (VFS) Abstraction Layer
Metadata Instant Inspect: The VFS layer reads only the JSON manifest from the .hcs container header to display original file dimensions and name.
RAM Streamer & Instant Play: On audio access, the first 2.5s chunk is resynthesized instantly in RAM for 0% latency playback, while the remaining audio is synthesized in the background.
Phase 5: Node & Web UI Layer
Storage Explorer Interface: Synchronization of the web UI with support for folder trees, memory streaming, mounting, and real-time parallel task tracking.
Phase 6: Native Kernel Drivers & Network Sharing
Linux FUSE Driver: Kernel driver for mounting .hcs as a native Linux directory (/mnt/neurafs).
Windows WinFSP / Dokany Driver: Native Windows driver assigning a drive letter (e.g., Z:\) to the neural file system.
Samba VFS Plugin: Samba extension allowing exposure of intact files via a local SMB network (for NAS devices).
Phase 7: Test & Benchmark Suite
Analytical Metrics: Automated fidelity verification (SI-SDR, LSD, MSE).
Benchmark Scripts: Comparison of compression ratio, encoding/decoding speed, and RAM memory footprint.
3. HCS Binary Container Specification

Section
Size / Format
Description
Magic Header
8 Bytes (HCS1xxxx)
Used to recognize the NeuraFS container version.
Manifest Length
4 Bytes (UInt32BE)
Size of the JSON header in bytes.
VFS Manifest
JSON String
Contains original filename, size, sample rate, channels, and deconstruction mapping (chunk offsets).
Neural Payload
Binary Float16 Blobs
Raw bytes of all weights from SIREN agents stored sequentially.

4. Execution Plan
Document saved as GOALS.md.
Proceed to Phase 1: Core Engine & Standard HCS Container.
Phase 1 Initiation: Core Engine Architecture & HCS Specification Design
To establish a solid, decoupled foundation for Phase 1, we will modularize the current engine into a clean, reusable architecture. The goal of Phase 1 is to ensure the Core Engine operates independently from FastAPI or Node.js web wrappers.
Core Component Breakdown
1. Modular Core Components (neurafs/core/)
container.py: Manages HCS1 binary packing/unpacking, header parsing, byte alignment, and version routing.
dsp.py: Handles audio loading (MP3/WAV via FFmpeg), subband frequency splitting (scipy.signal), and signal complexity estimation.
siren.py: Pure PyTorch implementation of SineLayer and SirenAgent along with raw Float16 byte serialization/deserialization routines.
engine.py: Orchestrates parallel worker execution (isolated_subband_worker), chunking, reconstruction validation (SI-SDR/LSD metrics), and memory management.
2. HCS Version Router Blueprint



Plaintext
HCS Container File
       │
       ▼
┌──────────────┐
│ Magic Header │ ──► Reads first 8 bytes (e.g., 'HCS10000')[cite: 4]
└──────┬───────┘
       │
       ├─────► Version == 'HCS1' ──► HCS1Unpacker (Current FP16 Payload)[cite: 4]
       ├─────► Version == 'HCS2' ──► HCS2Unpacker (Future Quantized INT8 Payload)
       └─────► Unknown Header   ──► Legacy JSON / Raw File Fallback[cite: 4]


3. Next Step We will structure the engine logic so that it can run entirely from a standalone Python module or CLI command, cleanly separating pure signal processing from HTTP/Express code.
