"""NeuraFS Neural Audio Codecs Architecture Package."""

from neurafs.core.codecs.siren import (
    SirenAgent,
    SineLayer,
    compute_composite_loss,
    serialize_agent_raw_bytes,
    deserialize_agent_raw_bytes,
)
from neurafs.core.codecs.future_codec import (
    BaseNeuralCodec,
    FutureNeuralCodec,
    register_codec,
    get_codec,
)

__all__ = [
    "SirenAgent",
    "SineLayer",
    "compute_composite_loss",
    "serialize_agent_raw_bytes",
    "deserialize_agent_raw_bytes",
    "BaseNeuralCodec",
    "FutureNeuralCodec",
    "register_codec",
    "get_codec",
]