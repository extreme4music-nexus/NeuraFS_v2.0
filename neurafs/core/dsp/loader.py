"""NeuraFS Zero-Disk-Write Audio Extraction & Loader Module."""

import io
import subprocess
import numpy as np
import scipy.io.wavfile as wavfile
from typing import Tuple


class AudioLoader:
    """Handles in-memory loading, format normalization, and PCM extraction."""

    @staticmethod
    def load_from_bytes(file_bytes: bytes, target_sample_rate: int = 44100) -> Tuple[np.ndarray, int, int]:
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
            if pcm.dtype == np.int16:
                pcm = (pcm / 32768.0).astype(np.float32)
            elif pcm.dtype == np.int32:
                pcm = (pcm / 2147483648.0).astype(np.float32)
            channels = 1 if pcm.ndim == 1 else pcm.shape[1]
            return pcm.T if pcm.ndim > 1 else pcm[np.newaxis, :], sr, channels
        except Exception:
            pass

        # Fallback to FFmpeg pipe for encoded formats (MP3/AAC/FLAC)
        command = [
            "ffmpeg",
            "-i", "pipe:0",
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ar", str(target_sample_rate),
            "-ac", "2",
            "pipe:1"
        ]
        
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        raw_pcm, _ = proc.communicate(input=file_bytes)
        
        if proc.returncode != 0:
            raise ValueError("Failed to decode audio bytes using FFmpeg pipeline.")

        audio_int16 = np.frombuffer(raw_pcm, dtype=np.int16)
        audio_stereo = audio_int16.reshape(-1, 2).T
        audio_float32 = (audio_stereo / 32768.0).astype(np.float32)

        return audio_float32, target_sample_rate, 2

    @staticmethod
    def load_from_file(file_path: str, target_sample_rate: int = 44100) -> Tuple[np.ndarray, int, int]:
        """Reads local audio file into RAM bytes and extracts float32 PCM data."""
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        return AudioLoader.load_from_bytes(file_bytes, target_sample_rate)
