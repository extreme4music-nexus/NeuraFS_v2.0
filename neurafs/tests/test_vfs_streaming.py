"""Focused checks for SIREN channel preservation and virtual audio reads."""

import shutil

import numpy as np
import pytest

from neurafs.core.codecs.siren import SirenAgent
from neurafs.core.codecs.siren_codec import _isolated_subband_worker
from neurafs.core.config import DecodeMode, PrecisionMode, TargetQualityTier, config
from neurafs.core.container import HCSContainer
from neurafs.vfs.interface import NeuraFSVFSInterface
from neurafs.vfs.ram_streamer import RAMStreamBuffer


def _container(name, sample_rate, sample_count, blobs):
    chunks = []
    offset = 0
    for index, blob in enumerate(blobs):
        chunks.append({
            "time_slice_idx": index,
            "offset": offset,
            "length": len(blob),
            "num_samples": int(sample_rate * 2.5),
        })
        offset += len(blob)
    manifest = {
        "hcs_version": "1.0",
        "original": {
            "name": name,
            "size": 4096,
            "type": "neural_media",
            "channels": 1,
            "sample_rate": sample_rate,
            "samples": sample_count,
        },
        "neural": {"codec": "dac", "precision": "fp16", "subbands": 1},
        "chunks": chunks,
    }
    return HCSContainer.pack(manifest, blobs, precision=PrecisionMode.STANDARD_16)


def _pin_full_rate(monkeypatch):
    monkeypatch.setattr(config, "scan_hardware", lambda _precision: object())
    monkeypatch.setattr(
        config,
        "resolve_decode_tier",
        lambda _mode, _profile, sample_rate: (sample_rate, TargetQualityTier.STANDARD),
    )


def test_siren_worker_and_model_preserve_stereo(monkeypatch):
    monkeypatch.setattr(config, "SIREN_HIDDEN_FEATURES", 8)
    monkeypatch.setattr(config, "SIREN_HIDDEN_LAYERS", 1)
    t = np.arange(2048, dtype=np.float32)
    stereo = np.vstack((np.sin(t * 0.03), np.sin(t * 0.07))).astype(np.float32)
    result = _isolated_subband_worker({
        "pcm": stereo,
        "precision": "fp16",
        "epochs": 1,
        "chunk_idx": 0,
        "band_idx": 0,
    })

    assert result["channels"] == 2
    model = SirenAgent.deserialize_weights(
        result["blob"], hidden_features=8, hidden_layers=1, out_features=2
    )
    import torch
    reconstructed = model(torch.linspace(-1, 1, 2048).unsqueeze(-1))
    assert reconstructed.shape == (2048, 2)


def test_virtual_wav_size_random_reads_and_eof(monkeypatch, tmp_path):
    _pin_full_rate(monkeypatch)
    monkeypatch.setattr(
        "neurafs.vfs.ram_streamer.NeuraFSEngine.resynthesize_audio_from_units",
        lambda **kwargs: np.full(
            (kwargs["channels"], int(kwargs["sample_rate"] * config.CHUNK_DURATION_SEC)),
            0.1,
            dtype=np.float32,
        ),
    )
    (tmp_path / "song.wav.hcs").write_bytes(_container("song.wav", 8000, 1000, [b"a"]))
    vfs = NeuraFSVFSInterface(str(tmp_path))

    attrs = vfs.getattr("song.wav")
    assert attrs["size"] == 44 + 1000 * 2
    assert vfs.readdir("")[0]["size"] == attrs["size"]
    whole_file = vfs.read("song.wav", 0, attrs["size"] + 100)
    assert len(whole_file) == attrs["size"]
    assert whole_file[:4] == b"RIFF"
    assert int.from_bytes(whole_file[40:44], "little") == 2000
    assert vfs.read("song.wav", 40, 20) == whole_file[40:60]
    assert vfs.read("song.wav", 44 + 123, 257) == whole_file[44 + 123:44 + 123 + 257]
    assert vfs.read("song.wav", attrs["size"], 10) == b""


def test_ram_range_reads_decode_later_chunks_and_stream_exact_length(monkeypatch, tmp_path):
    _pin_full_rate(monkeypatch)
    decoded_blobs = []

    def fake_decode(**kwargs):
        decoded_blobs.append(kwargs["blob_list"][0])
        assert all(unit["time_slice_idx"] == 0 for unit in kwargs["chunk_units"])
        level = 0.1 if kwargs["blob_list"][0] == b"a" else 0.2
        return np.full((1, 20000), level, dtype=np.float32)

    monkeypatch.setattr("neurafs.vfs.ram_streamer.NeuraFSEngine.resynthesize_audio_from_units", fake_decode)
    data = _container("long.wav", 8000, 22000, [b"a", b"b"])
    buffer = RAMStreamBuffer(data, DecodeMode.REALTIME_ADAPTIVE)

    header = buffer.read_pcm_bytes(0, 44)
    assert int.from_bytes(header[40:44], "little") == 44000
    body = buffer.read_pcm_bytes(44, 44000)
    assert len(body) == 44000
    assert set(decoded_blobs) == {b"a", b"b"}
    stream = b"".join(buffer.generate_pcm_stream())
    assert len(stream) == 44000
    assert stream == body


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is needed to produce MP3 output")
def test_virtual_mp3_uses_mp3_bytes_and_exact_virtual_size(monkeypatch, tmp_path):
    _pin_full_rate(monkeypatch)
    monkeypatch.setattr(
        "neurafs.vfs.ram_streamer.NeuraFSEngine.resynthesize_audio_from_units",
        lambda **kwargs: np.full(
            (kwargs["channels"], kwargs["sample_rate"] * 2),
            0.1,
            dtype=np.float32,
        ),
    )
    (tmp_path / "song.mp3.hcs").write_bytes(_container("song.mp3", 8000, 16000, [b"a"]))
    vfs = NeuraFSVFSInterface(str(tmp_path))

    attrs = vfs.getattr("song.mp3")
    first_bytes = vfs.read("song.mp3", 0, 16)
    assert attrs["size"] > 0
    assert first_bytes.startswith(b"ID3") or first_bytes[:1] == b"\xff"
    assert len(vfs.read("song.mp3", attrs["size"] - 10, 20)) == 10
    assert vfs.read("song.mp3", attrs["size"], 20) == b""


def test_winfsp_callbacks_list_and_read_virtual_wav(monkeypatch, tmp_path):
    from neurafs.vfs.drivers import windows_winfsp

    if not windows_winfsp._WINFSP_AVAILABLE or windows_winfsp.BaseFileSystemOperations is None:
        pytest.skip("WinFSP callbacks are only available when WinFSP is installed")

    _pin_full_rate(monkeypatch)
    monkeypatch.setattr(
        "neurafs.vfs.ram_streamer.NeuraFSEngine.resynthesize_audio_from_units",
        lambda **kwargs: np.full(
            (kwargs["channels"], int(kwargs["sample_rate"] * config.CHUNK_DURATION_SEC)),
            0.1,
            dtype=np.float32,
        ),
    )
    (tmp_path / "song.wav.hcs").write_bytes(_container("song.wav", 8000, 1000, [b"a"]))

    operations = windows_winfsp._NeuraFSWinFSPOperations(str(tmp_path))
    root_handle = operations.open("\\", 0, 0)
    entries = operations.read_directory(root_handle, None)
    assert [entry["file_name"] for entry in entries] == ["song.wav"]

    file_handle = operations.open("\\song.wav", 0, 0)
    info = operations.get_file_info(file_handle)
    assert info["file_size"] == 44 + 1000 * 2
    assert operations.read(file_handle, 0, 44)[:4] == b"RIFF"
    operations.cleanup(file_handle, "\\song.wav", 0)
    operations.close(file_handle)
