"""Regression checks for neural-codec metadata that affects audio level."""

import numpy as np
import torch

from neurafs.core.codecs.encodec import EnCodecCodec
from neurafs.core.config import PrecisionMode


class _ScaledFrameModel:
    """Small EnCodec stand-in that makes dropped scales audible in the test."""

    def __init__(self):
        self.decoded_frames = None

    def parameters(self):
        return iter((torch.nn.Parameter(torch.zeros(())),))

    def set_target_bandwidth(self, _bandwidth):
        pass

    def encode(self, _wav):
        first = torch.ones((1, 2, 5), dtype=torch.long)
        second = torch.full((1, 2, 5), 2, dtype=torch.long)
        return [(first, torch.tensor([[0.1]])), (second, torch.tensor([[0.2]]))]

    def decode(self, encoded_frames):
        self.decoded_frames = encoded_frames
        decoded = []
        for codes, scale in encoded_frames:
            amplitude = 10.0 if scale is None else 10.0 * float(scale.reshape(-1)[0])
            decoded.append(torch.full((1, 1, codes.shape[-1] * 2), amplitude))
        return torch.cat(decoded, dim=-1)


def test_encodec_round_trip_preserves_frame_scales_and_boundaries():
    model = _ScaledFrameModel()
    codec = EnCodecCodec()
    codec._load_model = lambda _sample_rate: model
    source = np.zeros((1, 20), dtype=np.float32)

    payload, units, neural = codec.encode_media(
        pcm_data=source,
        sample_rate=8,
        channels=1,
        filename="scale-test.wav",
        file_size=source.nbytes,
        precision=PrecisionMode.STANDARD_16,
    )

    assert units[0]["frame_lengths"] == [5, 5]
    assert np.allclose(np.asarray(units[0]["frame_scales"]).reshape(-1), [0.1, 0.2])

    decoded = codec.decode_media(
        chunk_units=units,
        blob_list=[payload[units[0]["offset"]:units[0]["offset"] + units[0]["length"]]],
        channels=1,
        sample_rate=8,
        neural_info=neural,
        precision=PrecisionMode.STANDARD_16,
    )

    assert len(model.decoded_frames) == 2
    assert decoded.shape == (1, 20)
    # Temporal overlap-add fades the outermost chunk samples at file edges.
    assert np.allclose(decoded[0, 1:10], 1.0)
    assert np.allclose(decoded[0, 10:-1], 2.0)
