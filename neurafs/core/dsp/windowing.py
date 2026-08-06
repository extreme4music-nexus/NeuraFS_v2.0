"""NeuraFS Temporal Chunking & Overlap-Add (OLA) Windowing Module."""

import numpy as np
from typing import List, Dict, Any


class TemporalChunker:
    """Manages temporal slicing into 2.5s chunks with Overlap-Add crossfading."""

    @staticmethod
    def slice_into_chunks(
        pcm_data: np.ndarray,
        sample_rate: int = 44100,
        chunk_duration_sec: float = 2.5,
        overlap_ratio: float = 0.05
    ) -> List[Dict[str, Any]]:
        """Slices PCM array into overlapping temporal chunks."""
        samples_per_chunk = int(sample_rate * chunk_duration_sec)
        overlap_samples = int(samples_per_chunk * overlap_ratio)
        step_samples = samples_per_chunk - overlap_samples

        total_samples = pcm_data.shape[-1]
        chunks = []
        chunk_idx = 0

        start = 0
        while start < total_samples:
            end = min(start + samples_per_chunk, total_samples)
            chunk_pcm = pcm_data[..., start:end]

            # Pad last chunk if shorter than full duration
            if chunk_pcm.shape[-1] < samples_per_chunk:
                pad_width = samples_per_chunk - chunk_pcm.shape[-1]
                if chunk_pcm.ndim > 1:
                    chunk_pcm = np.pad(chunk_pcm, ((0, 0), (0, pad_width)))
                else:
                    chunk_pcm = np.pad(chunk_pcm, (0, pad_width))

            chunks.append({
                "chunk_idx": chunk_idx,
                "start_sample": start,
                "end_sample": end,
                "pcm_data": chunk_pcm.astype(np.float32)
            })

            chunk_idx += 1
            start += step_samples

        return chunks

    @staticmethod
    def reconstruct_from_chunks(
        chunk_list: List[np.ndarray],
        sample_rate: int = 44100,
        chunk_duration_sec: float = 2.5,
        overlap_ratio: float = 0.05
    ) -> np.ndarray:
        """Stitches reconstructed temporal chunks back into a continuous PCM stream via Hanning Overlap-Add."""
        if not chunk_list:
            return np.array([], dtype=np.float32)

        samples_per_chunk = int(sample_rate * chunk_duration_sec)
        overlap_samples = int(samples_per_chunk * overlap_ratio)
        step_samples = samples_per_chunk - overlap_samples

        total_output_samples = step_samples * (len(chunk_list) - 1) + samples_per_chunk
        is_stereo = chunk_list[0].ndim > 1
        num_channels = chunk_list[0].shape[0] if is_stereo else 1

        if is_stereo:
            output_buffer = np.zeros((num_channels, total_output_samples), dtype=np.float32)
            weight_buffer = np.zeros((1, total_output_samples), dtype=np.float32)
        else:
            output_buffer = np.zeros(total_output_samples, dtype=np.float32)
            weight_buffer = np.zeros(total_output_samples, dtype=np.float32)

        # Hanning window for smooth crossfade transitions
        window = np.hanning(overlap_samples * 2)
        fade_in = window[:overlap_samples]
        fade_out = window[overlap_samples:]

        full_window = np.ones(samples_per_chunk, dtype=np.float32)
        full_window[:overlap_samples] = fade_in
        full_window[-overlap_samples:] = fade_out

        for idx, chunk in enumerate(chunk_list):
            start = idx * step_samples
            end = start + samples_per_chunk

            if is_stereo:
                output_buffer[:, start:end] += chunk * full_window
                weight_buffer[:, start:end] += full_window
            else:
                output_buffer[start:end] += chunk * full_window
                weight_buffer[start:end] += full_window

        # Normalize by overlapping window weights to maintain 1:1 amplitude
        weight_buffer[weight_buffer < 1e-6] = 1.0
        reconstructed_pcm = output_buffer / weight_buffer
        return reconstructed_pcm.astype(np.float32)
