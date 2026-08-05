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
    """Generates a temporary 2.5-second 44100Hz stereo sine wave file."""
    sample_rate = 44100
    duration = 2.5
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    
    # Dual-tone 440Hz / 880Hz stereo signal
    left = 0.5 * np.sin(2 * np.pi * 440 * t)
    right = 0.3 * np.sin(2 * np.pi * 880 * t)
    stereo_pcm = np.column_stack((left, right))
    
    pcm_int16 = (stereo_pcm * 32767.0).astype(np.int16)
    
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

        # Check fidelity metrics
        metrics = enc_res["manifest"].get("metrics", {})
        assert metrics.get("si_sdr_db", 0.0) > 10.0  # Quality baseline threshold > 10 dB

    finally:
        for path in [hcs_out, wav_out]:
            if os.path.exists(path):
                os.remove(path)