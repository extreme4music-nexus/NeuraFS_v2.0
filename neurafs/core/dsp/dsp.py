"""NeuraFS Digital Signal Processing (DSP) & Complexity Profiling Module."""

import subprocess
from typing import List, Tuple
import numpy as np
import scipy.signal as signal

from neurafs.core.config import config
from neurafs.core.exceptions import AudioAnalysisError


class DSPProcessor:
    """Provides audio extraction, subband decomposition, complexity profiling, and temporal chunking."""

    @staticmethod
    def extract_pcm_from_bytes(file_bytes: bytes, filename: str) -> Tuple[np.ndarray, int, int]:
        """Extracts normalized Float32 PCM audio data using FFmpeg subprocess pipes."""
        sample_rate = config.DEFAULT_SAMPLE_RATE

        # Inspect stream metadata or extract directly via FFmpeg
        cmd_audio = [
            'ffmpeg',
            '-i', 'pipe:0',
            '-vn',
            '-f', 's16le',
            '-ac', str(config.CHANNELS),
            '-ar', str(sample_rate),
            'pipe:1'
        ]

        try:
            proc = subprocess.Popen(
                cmd_audio,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            out_pcm, err_log = proc.communicate(input=file_bytes)

            if proc.returncode != 0 or len(out_pcm) == 0:
                raise AudioAnalysisError(f"FFmpeg failed to extract PCM audio from {filename}: {err_log.decode('utf-8', errors='ignore')}")

            a_int16 = np.frombuffer(out_pcm, dtype=np.int16)
            if len(a_int16) == 0:
                raise AudioAnalysisError(f"Extracted zero PCM samples from file: {filename}")

            audio_np = (a_int16.astype(np.float32) / 32768.0).reshape((-1, config.CHANNELS))
            channels = audio_np.shape[1]

            return audio_np, sample_rate, channels

        except Exception as err:
            if isinstance(err, AudioAnalysisError):
                raise err
            raise AudioAnalysisError(f"Audio processing error on file '{filename}': {err}") from err

    @staticmethod
    def estimate_signal_complexity(pcm_subband: np.ndarray, subband_idx: int, num_bands: int) -> Tuple[int, float]:
        """Profiles RMS, Zero-Crossing Rate, and Spectral Flatness to adaptively tune SIREN steps and loss target."""
        if len(pcm_subband) == 0 or not config.AUTO_COMPLEXITY_ADAPTATION:
            return config.MAX_TRAINING_STEPS, 0.0001

        num_samples = len(pcm_subband)
        
        # 1. Root Mean Square (RMS) Energy
        rms = np.sqrt(np.mean(pcm_subband ** 2)) + 1e-9

        # 2. Zero-Crossing Rate (ZCR)
        zero_crossings = np.sum(np.abs(np.diff(np.sign(pcm_subband)))) / (2.0 * num_samples)

        # 3. Spectral Flatness (Wiener Entropy)
        fft_mag = np.abs(np.fft.rfft(pcm_subband)) + 1e-9
        geo_mean = np.exp(np.mean(np.log(fft_mag)))
        arith_mean = np.mean(fft_mag)
        spectral_flatness = geo_mean / arith_mean

        # Synthesize normalized complexity score (0.1 to 1.0)
        complexity_score = float(np.clip((rms * 2.0) + (spectral_flatness * 1.5) + (zero_crossings * 0.5), 0.1, 1.0))

        # Dynamically scale training iterations within config bounds
        step_range = config.MAX_TRAINING_STEPS - config.MIN_TRAINING_STEPS
        max_steps = int(config.MIN_TRAINING_STEPS + (complexity_score * step_range))

        # Frequency-dependent target loss thresholds
        if subband_idx == 0:
            target_loss = 0.00002  # High fidelity required for low-frequency fundamentals
        elif subband_idx < int(num_bands * 0.7):
            target_loss = 0.000015
        else:
            target_loss = 0.00035  # Relaxed loss bound for high-frequency noise bands

        return max_steps, target_loss

    @staticmethod
    def split_into_subbands(pcm_signal: np.ndarray, sample_rate: int, num_bands: int) -> List[np.ndarray]:
        """Splits a single-channel PCM signal into logarithmically spaced frequency subbands using Butterworth SOS filters."""
        if num_bands <= 1:
            return [pcm_signal]

        nyquist = sample_rate / 2.0
        edges = np.logspace(np.log10(40.0), np.log10(min(20000.0, nyquist - 100.0)), num=num_bands + 1)
        subbands = []

        for i in range(num_bands):
            low = edges[i] / nyquist
            high = edges[i + 1] / nyquist

            if i == 0:
                sos = signal.butter(4, high, btype='low', output='sos')
            elif i == num_bands - 1:
                sos = signal.butter(4, low, btype='high', output='sos')
            else:
                sos = signal.butter(4, [low, high], btype='band', output='sos')

            filtered = signal.sosfiltfilt(sos, pcm_signal)
            subbands.append(np.clip(filtered, -2.0, 2.0).astype(np.float32))

        return subbands

    @staticmethod
    def chunk_audio(audio_np: np.ndarray, sample_rate: int, chunk_duration: float = None) -> List[Tuple[int, np.ndarray]]:
        """Slices multi-channel audio PCM array into uniform temporal time slices."""
        if chunk_duration is None:
            chunk_duration = config.CHUNK_DURATION_SEC

        total_samples = len(audio_np)
        slice_samples = int(sample_rate * chunk_duration)
        total_slices = int(np.ceil(total_samples / slice_samples))

        chunks = []
        for slice_idx in range(total_slices):
            s_start = slice_idx * slice_samples
            s_end = min(s_start + slice_samples, total_samples)
            chunks.append((slice_idx, audio_np[s_start:s_end]))

        return chunks
