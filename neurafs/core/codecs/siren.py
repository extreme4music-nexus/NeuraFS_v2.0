"""NeuraFS Implicit Neural Representation (SIREN) Codec Agent Module."""

import struct
import numpy as np
import torch
import torch.nn as nn
from typing import Tuple, Dict, Any
from neurafs.core.config import PrecisionMode, config


class SineLayer(nn.Module):
    """SIREN Sinusoidal Activation Layer with frequency scaling omega_0."""

    def __init__(self, in_features: int, out_features: int, is_first: bool = False, omega_0: float = 50.0):
        super().__init__()
        self.omega_0 = omega_0
        self.is_first = is_first
        self.linear = nn.Linear(in_features, out_features)
        self.init_weights()

    def init_weights(self):
        with torch.no_grad():
            if self.is_first:
                self.linear.weight.uniform_(-1.0 / self.linear.in_features, 1.0 / self.linear.in_features)
            else:
                self.linear.weight.uniform_(
                    -np.sqrt(6.0 / self.linear.in_features) / self.omega_0,
                    np.sqrt(6.0 / self.linear.in_features) / self.omega_0,
                )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.sin(self.omega_0 * self.linear(x))


class SirenAgent(nn.Module):
    """Neural Agent representing a continuous 1D/2D audio waveform slice."""

    def __init__(
        self,
        in_features: int = 1,
        hidden_features: int = 64,
        hidden_layers: int = 3,
        out_features: int = 1,
        omega_0: float = 50.0,
    ):
        super().__init__()
        self.net = nn.ModuleList()
        # First layer
        self.net.append(SineLayer(in_features, hidden_features, is_first=True, omega_0=omega_0))

        # Hidden layers
        for _ in range(hidden_layers):
            self.net.append(SineLayer(hidden_features, hidden_features, is_first=False, omega_0=omega_0))

        # Output linear layer
        final_linear = nn.Linear(hidden_features, out_features)
        with torch.no_grad():
            final_linear.weight.uniform_(
                -np.sqrt(6.0 / hidden_features) / omega_0,
                np.sqrt(6.0 / hidden_features) / omega_0,
            )
        self.net.append(final_linear)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        for layer in self.net:
            x = layer(x)
        return x

    def serialize_weights(self, precision: PrecisionMode = PrecisionMode.STANDARD_16) -> bytes:
        """Serializes model state dict into continuous FP16/FP32 binary buffer."""
        state_dict = self.state_dict()
        buffer = bytearray()

        dtype = np.float16 if precision == PrecisionMode.STANDARD_16 else np.float32

        for key, tensor in state_dict.items():
            arr = tensor.cpu().detach().numpy().astype(dtype)
            raw_bytes = arr.tobytes()
            # Store array dimension metadata + raw bytes
            shape_bytes = struct.pack(f"<I{len(arr.shape)}I", len(arr.shape), *arr.shape)
            buffer.extend(struct.pack("<I", len(shape_bytes)))
            buffer.extend(shape_bytes)
            buffer.extend(struct.pack("<I", len(raw_bytes)))
            buffer.extend(raw_bytes)

        return bytes(buffer)

    @classmethod
    def deserialize_weights(
        cls,
        raw_bytes: bytes,
        in_features: int = 1,
        hidden_features: int = 64,
        hidden_layers: int = 3,
        out_features: int = 1,
        precision: PrecisionMode = PrecisionMode.STANDARD_16,
    ) -> "SirenAgent":
        """Reconstructs SirenAgent architecture and loads binary weights."""
        agent = cls(in_features, hidden_features, hidden_layers, out_features, config.SIREN_OMEGA_0)
        state_dict = {}

        offset = 0
        dtype = np.float16 if precision == PrecisionMode.STANDARD_16 else np.float32

        for key in agent.state_dict().keys():
            shape_hdr_len = struct.unpack_from("<I", raw_bytes, offset)[0]
            offset += 4

            ndim, *shape = struct.unpack_from(f"<I{shape_hdr_len // 4 - 1}I", raw_bytes, offset)
            offset += shape_hdr_len

            raw_data_len = struct.unpack_from("<I", raw_bytes, offset)[0]
            offset += 4

            data_bytes = raw_bytes[offset : offset + raw_data_len]
            offset += raw_data_len

            arr = np.frombuffer(data_bytes, dtype=dtype).reshape(shape).copy()
            state_dict[key] = torch.from_numpy(arr.astype(np.float32))

        agent.load_state_dict(state_dict)
        return agent


def serialize_agent_raw_bytes(agent: SirenAgent, precision: PrecisionMode = PrecisionMode.STANDARD_16) -> bytes:
    """Standalone module-level wrapper for serializing SirenAgent weights."""
    return agent.serialize_weights(precision)


def deserialize_agent_raw_bytes(
    raw_bytes: bytes,
    in_features: int = 1,
    hidden_features: int = 64,
    hidden_layers: int = 3,
    out_features: int = 1,
    precision: PrecisionMode = PrecisionMode.STANDARD_16,
) -> SirenAgent:
    """Standalone module-level wrapper for deserializing SirenAgent weights."""
    return SirenAgent.deserialize_weights(
        raw_bytes,
        in_features=in_features,
        hidden_features=hidden_features,
        hidden_layers=hidden_layers,
        out_features=out_features,
        precision=precision,
    )


def compute_composite_loss(predictions: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
    """Computes joint Temporal MSE + Spectral STFT Loss with correct time alignment and Hann windowing."""
    mse_loss = nn.MSELoss()(predictions, targets)

    # Ensure shape is [channels, time_samples] for STFT along the temporal dimension
    pred_stft_in = predictions.T if predictions.ndim == 2 else predictions.unsqueeze(0)
    target_stft_in = targets.T if targets.ndim == 2 else targets.unsqueeze(0)

    # Create Hann window on the same compute device to suppress warning & prevent spectral leakage
    window = torch.hann_window(256).to(predictions.device)
    stft_pred = torch.stft(predictions.squeeze().transpose(-2, -1), n_fft=256, hop_length=64, window=window, return_complex=True)
    stft_tgt = torch.stft(targets.squeeze().transpose(-2, -1), n_fft=256, hop_length=64, window=window, return_complex=True)

    spectral_loss = nn.L1Loss()(torch.abs(stft_pred), torch.abs(stft_tgt))

    return mse_loss + 0.2 * spectral_loss