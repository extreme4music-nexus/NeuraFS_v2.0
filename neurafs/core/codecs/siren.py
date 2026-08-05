"""NeuraFS Implicit Neural Representation (SIREN) Architecture & Byte Serialization."""

from typing import Dict
import numpy as np
import torch
import torch.nn as nn

from neurafs.core.config import config, PrecisionMode
from neurafs.core.exceptions import NeuralResynthesisError, InvalidPrecisionModeError


class SineLayer(nn.Module):
    """Linear layer followed by a sine activation function with custom omega_0 weight initialization."""

    def __init__(
        self,
        in_features: int,
        out_features: int,
        bias: bool = True,
        is_first: bool = False,
        omega_0: float = 30.0,
    ):
        super().__init__()
        self.omega_0 = omega_0
        self.is_first = is_first
        self.in_features = in_features
        self.linear = nn.Linear(in_features, out_features, bias=bias)
        self.init_weights()

    def init_weights(self) -> None:
        """Applies Siren uniform distribution weight bounds based on layer hierarchy and omega_0."""
        with torch.no_grad():
            if self.is_first:
                self.linear.weight.uniform_(-1.0 / self.in_features, 1.0 / self.in_features)
            else:
                bound = np.sqrt(6.0 / self.in_features) / self.omega_0
                self.linear.weight.uniform_(-bound, bound)

    def forward(self, input_tensor: torch.Tensor) -> torch.Tensor:
        """Executes forward pass applying sine activation scaled by omega_0."""
        return torch.sin(self.omega_0 * self.linear(input_tensor))


class SirenAgent(nn.Module):
    """Implicit Neural Representation network mapping 1D time coordinates to continuous signal amplitude."""

    def __init__(
        self,
        in_features: int = 1,
        hidden_features: int = 32,
        hidden_layers: int = 2,
        out_features: int = 1,
        omega_0: float = 45.0,
    ):
        super().__init__()
        self.net = nn.ModuleList()
        
        # First layer initialization
        self.net.append(SineLayer(in_features, hidden_features, is_first=True, omega_0=omega_0))
        
        # Hidden layers
        for _ in range(hidden_layers):
            self.net.append(SineLayer(hidden_features, hidden_features, is_first=False, omega_0=omega_0))
        
        # Linear output layer
        final_linear = nn.Linear(hidden_features, out_features)
        with torch.no_grad():
            bound = np.sqrt(6.0 / hidden_features) / omega_0
            final_linear.weight.uniform_(-bound, bound)
        self.net.append(final_linear)

    def forward(self, coords: torch.Tensor) -> torch.Tensor:
        """Evaluates Siren agent across continuous coordinate space."""
        x = coords
        for layer in self.net:
            x = layer(x)
        return x


def serialize_agent_raw_bytes(
    agent: nn.Module,
    precision: PrecisionMode = PrecisionMode.STANDARD_16,
) -> bytes:
    """Serializes agent model weights into raw FP16 or FP32 binary byte buffers without JSON/Base64 overhead."""
    dtype = np.float16 if precision == PrecisionMode.STANDARD_16 else np.float32
    buffer = bytearray()

    try:
        for _, param in agent.state_dict().items():
            arr = param.cpu().numpy().astype(dtype)
            buffer.extend(arr.tobytes())
        return bytes(buffer)
    except Exception as err:
        raise NeuralResynthesisError(f"Failed to serialize agent parameters into binary buffer: {err}") from err


def deserialize_agent_from_bytes(
    agent: nn.Module,
    raw_bytes: bytes,
    precision: PrecisionMode = PrecisionMode.STANDARD_16,
) -> None:
    """Deserializes raw binary FP16/FP32 byte buffer directly into PyTorch state_dict parameters."""
    if precision == PrecisionMode.STANDARD_16:
        dtype = np.float16
        bytes_per_elem = 2
    elif precision == PrecisionMode.HIGH_32:
        dtype = np.float32
        bytes_per_elem = 4
    else:
        raise InvalidPrecisionModeError(f"Unsupported precision mode specified for deserialization: {precision}")

    curr_state = agent.state_dict()
    offset = 0
    new_state: Dict[str, torch.Tensor] = {}

    try:
        for key, tensor in curr_state.items():
            shape = tensor.shape
            num_elements = int(np.prod(shape))
            byte_size = num_elements * bytes_per_elem

            if offset + byte_size > len(raw_bytes):
                raise NeuralResynthesisError(
                    f"Truncated weight buffer for key '{key}'. Required {byte_size} bytes, offset reached {offset}/{len(raw_bytes)}"
                )

            chunk = raw_bytes[offset : offset + byte_size]
            arr = np.frombuffer(chunk, dtype=dtype).reshape(shape).astype(np.float32)
            new_state[key] = torch.from_numpy(arr)
            offset += byte_size

        agent.load_state_dict(new_state)
    except Exception as err:
        if isinstance(err, (NeuralResynthesisError, InvalidPrecisionModeError)):
            raise err
        raise NeuralResynthesisError(f"Failed to deserialize binary payload into SirenAgent: {err}") from err