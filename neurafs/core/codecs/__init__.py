"""NeuraFS Neural Audio Codecs Architecture Package."""

from neurafs.core.codecs.siren import (
    SirenAgent,
    SineLayer,
    serialize_agent_raw_bytes,
    deserialize_agent_from_bytes,
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
    "serialize_agent_raw_bytes",
    "deserialize_agent_from_bytes",
    "BaseNeuralCodec",
    "FutureNeuralCodec",
    "register_codec",
    "get_codec",
]