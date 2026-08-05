"""NeuraFS FastAPI Pydantic Data Validation Schemas."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ResynthesisChunkInfo(BaseModel):
    """Schema representing neural chunk metadata and base64 encoded weight payload."""

    time_slice_idx: int = Field(default=0, description="Temporal slice index")
    subband_idx: int = Field(default=0, description="Frequency subband index")
    ch_idx: int = Field(default=0, description="Audio channel index")
    num_samples: int = Field(default=110250, description="Number of PCM samples in chunk")
    hidden_dim: int = Field(default=32, description="SIREN hidden layer dimension")
    weights_b64: Optional[str] = Field(default=None, description="Base64 encoded float16/float32 weights")
    offset: Optional[int] = Field(default=None, description="Byte offset in HCS container")
    length: Optional[int] = Field(default=None, description="Byte length in HCS container")


class ResynthesisRequest(BaseModel):
    """Payload schema for multi-chunk neural resynthesis requests."""

    chunks: List[ResynthesisChunkInfo]
    precision: str = Field(default="fp16", description="Weight precision mode ('fp16' or 'fp32')")


class ResynthesisResponse(BaseModel):
    """Response schema containing reconstructed base64 PCM audio buffer."""

    status: str = "success"
    pcm_b64: str
    bits_per_sample: int = 16
    audio_format: int = 1


class TaskStatusResponse(BaseModel):
    """Response schema for background encoding task tracking."""

    id: str
    status: str
    progress: int
    log: str
    logsHistory: List[str]
    result: Optional[Dict[str, Any]] = None


class EncodeStartResponse(BaseModel):
    """Initial response schema when enqueuing a new encoding job."""

    status: str = "queued"
    task_id: str