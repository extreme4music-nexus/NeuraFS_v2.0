"""NeuraFS Neural Audio Codecs Architecture Package."""

from neurafs.core.codecs.base import (
    BaseNeuralCodec,
    CodecKind,
    CODEC_REGISTRY,
    get_codec,
    list_codecs,
    register_codec,
)
from neurafs.core.codecs.siren import (
    SirenAgent,
    SineLayer,
    compute_composite_loss,
    serialize_agent_raw_bytes,
    deserialize_agent_raw_bytes,
)
from neurafs.core.codecs.siren_codec import SirenCodec
from neurafs.core.codecs.dac import DACCodec
from neurafs.core.codecs.encodec import EnCodecCodec
from neurafs.core.codecs.future_codec import FutureNeuralCodec

# Register built-in codecs (SIREN remains available as an alternative / default)
register_codec("siren", SirenCodec)
register_codec("dac", DACCodec)
register_codec("encodec", EnCodecCodec)
register_codec("future_codec", FutureNeuralCodec)

__all__ = [
    "BaseNeuralCodec",
    "CodecKind",
    "CODEC_REGISTRY",
    "get_codec",
    "list_codecs",
    "register_codec",
    "SirenAgent",
    "SineLayer",
    "compute_composite_loss",
    "serialize_agent_raw_bytes",
    "deserialize_agent_raw_bytes",
    "SirenCodec",
    "DACCodec",
    "EnCodecCodec",
    "FutureNeuralCodec",
]
