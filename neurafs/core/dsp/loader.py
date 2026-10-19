"""NeuraFS Zero-Disk-Write Audio Extraction & Loader Module."""

import io
import sys
import warnings
import subprocess
import numpy as np
import scipy.io.wavfile as wavfile
from scipy.io.wavfile import WavFileWarning
from typing import Optional, Tuple


class AudioLoader:
    """Handles in-memory loading, format normalization, and PCM extraction."""

    @staticmethod
    def load_from_bytes(
        file_bytes: bytes, target_sample_rate: Optional[int] = 44100
    ) -> Tuple[np.ndarray, int, int]:
        """Loads audio file from RAM bytes (MP3/WAV/FLAC) into Float32 PCM numpy array via FFmpeg subprocess.
        
        Returns:
            Tuple[pcm_data (np.ndarray), sample_rate (int), channels (int)]
        """
        # Attempt direct WAV parse via SciPy first for speed
        try:
            byte_io = io.BytesIO(file_bytes)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", WavFileWarning)
                sr, pcm = wavfile.read(byte_io)
            if np.issubdtype(pcm.dtype, np.unsignedinteger):
                info = np.iinfo(pcm.dtype)
                midpoint = (float(info.max) + 1.0) / 2.0
                pcm = ((pcm.astype(np.float32) - midpoint) / midpoint).astype(np.float32)
            elif np.issubdtype(pcm.dtype, np.signedinteger):
                info = np.iinfo(pcm.dtype)
                scale = float(max(abs(info.min), info.max))
                pcm = (pcm.astype(np.float32) / scale).astype(np.float32)
            else:
                pcm = pcm.astype(np.float32, copy=False)
            channels = 1 if pcm.ndim == 1 else pcm.shape[1]
            return pcm.T if pcm.ndim > 1 else pcm[np.newaxis, :], sr, channels
        except Exception:
            pass

        # Fallback to FFmpeg pipe for encoded formats (MP3/AAC/FLAC)
        command = [
            "ffmpeg", "-v", "error", "-i", "pipe:0", "-vn",
            "-f", "wav", "-acodec", "pcm_f32le",
        ]
        if target_sample_rate is not None:
            command.extend(["-ar", str(int(target_sample_rate))])
        command.append("pipe:1")

        # Prevent CMD window pop-ups on Windows
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kwargs
        )
        raw_pcm, error = proc.communicate(input=file_bytes)
        
        if proc.returncode != 0:
            detail = error.decode("utf-8", errors="replace").strip()
            raise ValueError(
                "Failed to decode audio bytes using FFmpeg pipeline"
                + (f": {detail}" if detail else ".")
            )

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", WavFileWarning)
                sample_rate, pcm = wavfile.read(io.BytesIO(raw_pcm))
        except Exception as exc:
            raise ValueError("FFmpeg returned audio data NeuraFS could not read.") from exc

        pcm = pcm.astype(np.float32, copy=False)
        channels = 1 if pcm.ndim == 1 else pcm.shape[1]
        return pcm.T if pcm.ndim > 1 else pcm[np.newaxis, :], sample_rate, channels

    @staticmethod
    def load_from_file(
        file_path: str, target_sample_rate: Optional[int] = 44100
    ) -> Tuple[np.ndarray, int, int]:
        """Reads local audio file into RAM bytes and extracts float32 PCM data."""
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        return AudioLoader.load_from_bytes(file_bytes, target_sample_rate)
