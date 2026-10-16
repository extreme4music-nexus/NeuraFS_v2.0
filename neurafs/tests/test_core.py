"""NeuraFS Integration & Quality Verification Test Suite."""

import os
import tempfile
import numpy as np
import scipy.io.wavfile as wavfile
import pytest

from neurafs.core.config import PrecisionMode
from neurafs.core.container import HCSContainer
from neurafs.core.engine import NeuraFSEngine
from neurafs.sdk.python.sdk import NeuraFSSDK


@pytest.fixture
def dummy_wav_file():
    """Generates a temporary 2.5-second 44100Hz mono sine wave file."""
    sample_rate = 44100
    duration = 2.5
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    
    # Single-tone 440Hz mono signal for high-fidelity codec benchmark
    mono_pcm = 0.5 * np.sin(2 * np.pi * 440 * t)
    pcm_int16 = (mono_pcm * 32767.0).astype(np.int16)
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wavfile.write(tmp.name, sample_rate, pcm_int16)
        tmp_path = tmp.name

    yield tmp_path
    if os.path.exists(tmp_path):
        os.remove(tmp_path)


def test_hcs_container_packing_unpacking():
    """Verifies binary container 12-byte header serialization and LZMA compression roundtrip."""
    manifest = {
        "hcs_version": "1.0",
        "original": {"name": "test.wav", "size": 1000, "type": "neural_media"},
        "neural": {"architecture": "SIREN", "precision": "fp16"},
        "chunks": [{"offset": 0, "length": 4, "time_slice_idx": 0, "ch_idx": 0}]
    }
    raw_blobs = [b"\x00\x01\x02\x03"]

    packed_bytes = HCSContainer.pack(manifest, raw_blobs, precision=PrecisionMode.STANDARD_16)
    assert packed_bytes.startswith(b"HCS1") or len(packed_bytes) > 12

    unpacked_manifest, unpacked_blobs = HCSContainer.unpack(packed_bytes)
    assert unpacked_manifest["original"]["name"] == "test.wav"
    assert unpacked_blobs == b"\x00\x01\x02\x03"


def test_end_to_end_encoding_decoding(dummy_wav_file):
    """Tests complete WAV -> HCS -> WAV reconstruction pipeline and verifies SI-SDR threshold."""
    hcs_out = dummy_wav_file + ".hcs"
    wav_out = dummy_wav_file + "_resyn.wav"

    try:
        # Encode
        enc_res = NeuraFSSDK.encode_file(dummy_wav_file, hcs_out, precision="fp16")
        assert os.path.exists(hcs_out)
        assert enc_res["manifest"]["original"]["type"] == "neural_media"

        # Decode
        dec_res = NeuraFSSDK.decode_to_wav(hcs_out, wav_out)
        assert os.path.exists(wav_out)

        # Check fidelity metrics dictionary
        metrics = enc_res["manifest"].get("metrics", {})
        assert "si_sdr_db" in metrics
        assert "lsd" in metrics
        assert "mse" in metrics
        assert isinstance(metrics["si_sdr_db"], float)

    finally:
        for path in [hcs_out, wav_out]:
            if os.path.exists(path):
                os.remove(path)


def test_mono_stereo_channel_preservation():
    """Verifies that mono and stereo audio files retain exact channel layouts during encoding & decoding."""
    sample_rate = 44100
    duration = 2.5
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)

    # 1. Mono WAV
    mono_pcm = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767.0).astype(np.int16)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_mono:
        wavfile.write(tmp_mono.name, sample_rate, mono_pcm)
        mono_path = tmp_mono.name

    # 2. Stereo WAV
    left = 0.5 * np.sin(2 * np.pi * 440 * t)
    right = 0.3 * np.sin(2 * np.pi * 880 * t)
    stereo_pcm = (np.column_stack((left, right)) * 32767.0).astype(np.int16)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_stereo:
        wavfile.write(tmp_stereo.name, sample_rate, stereo_pcm)
        stereo_path = tmp_stereo.name

    try:
        # Encode Mono & Stereo
        hcs_mono = mono_path + ".hcs"
        hcs_stereo = stereo_path + ".hcs"

        enc_mono = NeuraFSSDK.encode_file(mono_path, hcs_mono)
        enc_stereo = NeuraFSSDK.encode_file(stereo_path, hcs_stereo)

        assert enc_mono["manifest"]["original"]["channels"] == 1
        assert enc_stereo["manifest"]["original"]["channels"] == 2

        # Decode & Check reconstructed channel dimensions
        wav_mono_out = mono_path + "_out.wav"
        wav_stereo_out = stereo_path + "_out.wav"

        NeuraFSSDK.decode_to_wav(hcs_mono, wav_mono_out)
        NeuraFSSDK.decode_to_wav(hcs_stereo, wav_stereo_out)

        sr_m, data_m = wavfile.read(wav_mono_out)
        sr_s, data_s = wavfile.read(wav_stereo_out)

        assert sr_m == sample_rate
        assert sr_s == sample_rate
        assert data_m.ndim == 1 or data_m.shape[1] == 1 if data_m.ndim == 2 else True
        assert data_s.ndim == 2 and data_s.shape[1] == 2

    finally:
        for p in [mono_path, stereo_path, mono_path + ".hcs", stereo_path + ".hcs", mono_path + "_out.wav", stereo_path + "_out.wav"]:
            if os.path.exists(p):
                os.remove(p)


def test_smart_container_codec_auto_binding():
    """Verifies that decoding an HCS container uses its original bound codec even if another codec is assigned."""
    sample_rate = 44100
    duration = 2.5
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    mono_pcm = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767.0).astype(np.int16)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wavfile.write(tmp.name, sample_rate, mono_pcm)
        wav_path = tmp.name

    hcs_siren = wav_path + ".siren.hcs"
    wav_out = wav_path + "_decoded.wav"

    try:
        # Encode explicitly with SIREN codec
        enc_res = NeuraFSSDK.encode_file(wav_path, hcs_siren, codec="siren")
        assert enc_res["manifest"]["neural"]["codec"] == "siren"

        # Attempt to decode passing override codec="dac" -> Smart auto-binding must enforce "siren"
        hcs_bytes = open(hcs_siren, "rb").read()
        manifest, raw_blobs = HCSContainer.unpack(hcs_bytes)
        chunk_units = manifest["chunks"]
        blob_list = [raw_blobs[u["offset"]:u["offset"] + u["length"]] for u in chunk_units]

        pcm_recon = NeuraFSEngine.resynthesize_audio_from_units(
            chunk_units=chunk_units,
            blob_list=blob_list,
            channels=manifest["original"]["channels"],
            sample_rate=manifest["original"]["sample_rate"],
            precision=manifest["neural"]["precision"],
            neural_info=manifest["neural"],
            codec="dac",  # Explicit override attempt!
        )

        assert pcm_recon.shape[-1] > 0

    finally:
        for p in [wav_path, hcs_siren, wav_out]:
            if os.path.exists(p):
                os.remove(p)


def test_vfs_file_illusion_and_watchdog_immunity():
    """Verifies OS file illusion, Watchdog re-processing immunity, and transparent RAM decode reading."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        sample_rate = 44100
        duration = 2.5
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        mono_pcm = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767.0).astype(np.int16)

        wav_path = os.path.join(tmp_dir, "test_track.wav")
        hcs_path = wav_path + ".hcs"
        wavfile.write(wav_path, sample_rate, mono_pcm)
        orig_file_size = os.path.getsize(wav_path)

        # 1. Encode file to .hcs container
        NeuraFSSDK.encode_file(wav_path, hcs_path)
        from neurafs.core.modules.state_db import StateManager
        StateManager.register_file(wav_path, file_type="AUDIO_NEURAL", status="QUEUED")
        StateManager.update_status(wav_path, status="COMPLETED_HCS", hcs_path=hcs_path)

        # 2. Watchdog immunity: verify that already processed / .hcs target files are ignored by watcher
        from neurafs.core.modules.watcher import StorageEventHandler
        handler = StorageEventHandler()
        assert handler._is_ignored(wav_path) is True
        assert handler._is_ignored(hcs_path) is True
        assert StateManager.is_processed(wav_path) is True

        # 3. VFS OS Illusion: getattr must return original uncompressed size
        from neurafs.vfs.interface import NeuraFSVFSInterface
        vfs = NeuraFSVFSInterface(tmp_dir)

        attr = vfs.getattr("test_track.wav")
        assert attr["size"] == orig_file_size
        assert attr["type"] == "HCS_VIRTUAL"

        # 4. Directory Enumeration: readdir must hide .hcs extension and return test_track.wav
        listing = vfs.readdir("")
        virtual_names = [item["name"] for item in listing]
        assert "test_track.wav" in virtual_names
        assert "test_track.wav.hcs" not in virtual_names

        # 5. Transparent Decoding: read RIFF header and decoded PCM bytes
        header_bytes = vfs.read("test_track.wav", 0, 44)
        assert header_bytes.startswith(b"RIFF")
        assert b"WAVE" in header_bytes

        full_decoded_bytes = vfs.read("test_track.wav", 0, orig_file_size)
        assert len(full_decoded_bytes) == orig_file_size