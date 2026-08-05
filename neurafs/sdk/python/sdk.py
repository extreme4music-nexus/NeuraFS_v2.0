"""NeuraFS Native Python Software Development Kit (SDK)."""

import os
from typing import Dict, Any, Tuple
import scipy.io.wavfile as wavfile

from neurafs.core.config import config, PrecisionMode
from neurafs.core.container import HCSContainer
from neurafs.core.engine import NeuraFSEngine


class NeuraFSSDK:
    """Native Python client for inspecting, encoding, and decoding NeuraFS containers."""

    @staticmethod
    def inspect(container_path: str) -> Dict[str, Any]:
        """Reads and returns metadata manifest from .hcs container file."""
        if not os.path.exists(container_path):
            raise FileNotFoundError(f"Container not found: {container_path}")

        with open(container_path, "rb") as f:
            compressed_bytes = f.read()

        manifest, _ = HCSContainer.unpack(compressed_bytes)
        return manifest

    @staticmethod
    def decode_to_wav(container_path: str, output_wav_path: str) -> Dict[str, Any]:
        """Decompresses HCS container in RAM and writes resynthesized PCM to a WAV file."""
        if not os.path.exists(container_path):
            raise FileNotFoundError(f"Container not found: {container_path}")

        with open(container_path, "rb") as f:
            compressed_bytes = f.read()

        manifest, raw_blobs_data = HCSContainer.unpack(compressed_bytes)
        orig_info = manifest.get("original", {})
        
        if orig_info.get("type") != "neural_media":
            raise ValueError(f"Container '{container_path}' contains non-media binary payload.")

        precision_str = manifest.get("neural", {}).get("precision", "fp16")
        precision = PrecisionMode.HIGH_32 if precision_str == "fp32" else PrecisionMode.STANDARD_16

        chunk_units = manifest.get("chunks", [])
        channels = orig_info.get("channels", 2)
        sample_rate = orig_info.get("sample_rate", config.DEFAULT_SAMPLE_RATE)

        blob_list = [raw_blobs_data[u["offset"]:u["offset"] + u["length"]] for u in chunk_units]

        pcm_float = NeuraFSEngine.resynthesize_audio_from_units(
            chunk_units, blob_list, channels, sample_rate, precision
        )

        audio_pcm16 = (pcm_float * 32767.0).astype("int16")
        wavfile.write(output_wav_path, sample_rate, audio_pcm16)

        return {
            "status": "success",
            "output_path": output_wav_path,
            "manifest": manifest
        }

    @staticmethod
    def encode_file(input_file_path: str, output_container_path: str, precision: str = "fp16") -> Dict[str, Any]:
        """Encodes local audio file into .hcs container."""
        if not os.path.exists(input_file_path):
            raise FileNotFoundError(f"Input file not found: {input_file_path}")

        with open(input_file_path, "rb") as f:
            file_bytes = f.read()

        filename = os.path.basename(input_file_path)
        prec_mode = PrecisionMode.HIGH_32 if precision == "fp32" else PrecisionMode.STANDARD_16

        hcs_bytes = NeuraFSEngine.encode_media(
            file_bytes=file_bytes,
            filename=filename,
            precision=prec_mode
        )

        with open(output_container_path, "wb") as f:
            f.write(hcs_bytes)

        manifest, _ = HCSContainer.unpack(hcs_bytes)
        return {
            "status": "success",
            "output_path": output_container_path,
            "manifest": manifest
        }