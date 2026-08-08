# Hierarchical Neural Container Specification (.hcs)
**Version:** 1.0.0  
**Binary Magic:** `HCS1` (`0x48 0x43 0x53 0x31`)

## 1. Overview
The `.hcs` (Hierarchical Neural Container) file format is a hybrid binary format designed to store neural network parameterizations of continuous media signals alongside JSON-serialized metadata manifests and LZMA-compressed model weights.

---

## 2. Binary Layout Architecture

A `.hcs` file consists of three contiguous binary sections:
+-------------------------------------------------------+
| Header (12 Bytes)                                     |
+-------------------------------------------------------+
| Manifest Payload (JSON UTF-8, variable length)        |
+-------------------------------------------------------+
| Compressed Neural Payload (LZMA binary blobs)         |
+-------------------------------------------------------+


### 2.1 Header Structure (12 Bytes)
All fields use Little-Endian byte order.

| Offset | Size (Bytes) | Type | Field Name | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x00` | 4 | `char[4]` | `Magic` | Must equal `HCS1` |
| `0x04` | 2 | `uint16` | `Version` | Major/Minor version (e.g., `0x0100` for v1.0) |
| `0x06` | 2 | `uint16` | `Flags` | Bits: `0x01` (LZMA enabled), `0x02` (FP16 weights) |
| `0x08` | 4 | `uint32` | `ManifestLen` | Length $L_m$ of the JSON manifest in bytes |

---

## 3. Manifest Specification

The manifest immediately follows the 12-byte header at offset `0x0C` with length $L_m$.

```json
{
  "hcs_version": "1.0",
  "original": {
    "name": "audio_sample.wav",
    "size": 264644,
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
    "omega_0": 30.0
  },
  "metrics": {
    "si_sdr_db": 18.4,
    "lsd": 0.85,
    "mse": 0.0012
  },
  "chunks": [
    {
      "time_slice_idx": 0,
      "ch_idx": 0,
      "offset": 0,
      "length": 1420
    }
  ]
}
