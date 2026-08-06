"""NeuraFS Asynchronous FastAPI Backend Server & Streaming Gateway."""

import os
import base64
import queue
import threading
import traceback
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

import numpy as np
import scipy.io.wavfile as wavfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, HTMLResponse

from neurafs.core.config import config, PrecisionMode
from neurafs.core.storage import StorageManager
from neurafs.core.container import HCSContainer
from neurafs.core.engine import NeuraFSEngine
from neurafs.core.exceptions import (
    NeuraFSError,
    InvalidHCSHeaderError,
    CorruptedManifestError,
    UnsupportedHCSVersionError,
)
from neurafs.api.schemas import (
    ResynthesisRequest,
    ResynthesisResponse,
    TaskStatusResponse,
    EncodeStartResponse,
)

# Global Storage Directories
STORAGE_ROOT = StorageManager.get_path()
TEMP_ROOT = os.path.join(STORAGE_ROOT, ".temp")
os.makedirs(os.path.join(STORAGE_ROOT, "documents"), exist_ok=True)
os.makedirs(os.path.join(STORAGE_ROOT, "media"), exist_ok=True)
os.makedirs(TEMP_ROOT, exist_ok=True)

# State Registry & Job Queue
tasks: Dict[str, Dict[str, Any]] = {}
task_payloads: Dict[str, bytes] = {}
task_queue: queue.Queue = queue.Queue()


def get_safe_path(base_dir: str, req_path: str) -> str:
    """Validates directory trajectory to prevent path traversal attacks."""
    clean_path = os.path.normpath(req_path).lstrip("/\\")
    full_path = os.path.abspath(os.path.join(base_dir, clean_path))
    if not full_path.startswith(os.path.abspath(base_dir)):
        raise HTTPException(status_code=403, detail="Access denied: Invalid path trajectory.")
    return full_path


def process_task_execution(task_id: str) -> None:
    """Executes background neural media encoding pipeline."""
    task_info = tasks.get(task_id)
    file_bytes = task_payloads.get(task_id)

    if not task_info or file_bytes is None:
        return

    filename = task_info["filename"]
    precision_str = task_info["precision_mode"]

    precision = PrecisionMode.HIGH_32 if precision_str == "fp32" else PrecisionMode.STANDARD_16

    try:
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["logs"].append(f"Processing signal parameterization for {filename}...")

        # Encode via Core Engine (matches NeuraFSEngine.encode_media signature)
        hcs_bytes = NeuraFSEngine.encode_media(
            file_bytes=file_bytes,
            filename=filename,
            precision=precision,
        )

        manifest, _ = HCSContainer.unpack(hcs_bytes)
        is_media = manifest.get("original", {}).get("type") == "neural_media"
        target_folder = "media" if is_media else "documents"

        save_path = os.path.join(STORAGE_ROOT, target_folder, f"{filename}.hcs")
        with open(save_path, "wb") as f:
            f.write(hcs_bytes)

        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["result"] = manifest
        tasks[task_id]["logs"].append(f"Saved container: storage/{target_folder}/{filename}.hcs")

    except Exception as err:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["logs"].append(f"[Engine Error]: {str(err)}")
        print(f"[Task Failure]: {traceback.format_exc()}")
    finally:
        task_payloads.pop(task_id, None)


def queue_worker_loop() -> None:
    """Daemon thread worker consuming encoding jobs from global task queue."""
    while True:
        try:
            task_id = task_queue.get(timeout=1.0)
            if task_id:
                process_task_execution(task_id)
                task_queue.task_done()
        except queue.Empty:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle context manager starting daemon queue worker thread."""
    threading.Thread(target=queue_worker_loop, daemon=True).start()
    yield


app = FastAPI(title="NeuraFS Neural Media Server API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def serve_root():
    """Health check index route."""
    return "<h1>NeuraFS API Engine v2.0 Active</h1>"


@app.post("/api/v1/encode-neural-media-start", response_model=EncodeStartResponse)
async def encode_neural_media_start(
    file: UploadFile = File(...),
    task_id: str = Form(...),
    precision_mode: str = Form("fp16"),
    compute_device: str = Form("cpu"),
):
    """Enqueues media file for asynchronous background neural encoding."""
    file_bytes = await file.read()
    task_payloads[task_id] = file_bytes

    tasks[task_id] = {
        "id": task_id,
        "status": "queued",
        "progress": 0,
        "logs": [f"Enqueued {file.filename} for parameterization."],
        "result": None,
        "filename": file.filename,
        "precision_mode": precision_mode,
        "compute_device": compute_device,
    }

    task_queue.put(task_id)
    return EncodeStartResponse(status="queued", task_id=task_id)


@app.get("/api/v1/task-status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """Returns progress metrics and log history for an encoding task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")

    res = dict(tasks[task_id])
    res["logsHistory"] = res.get("logs", [])
    res["log"] = res["logs"][-1] if res.get("logs") else ""
    return TaskStatusResponse(**res)


@app.post("/api/v1/resynthesize-neural-media", response_model=ResynthesisResponse)
async def resynthesize_neural_media(req: ResynthesisRequest):
    """Reconstructs raw PCM audio bytes in RAM from raw neural chunk definitions."""
    if not req.chunks:
        raise HTTPException(status_code=400, detail="No neural chunk units provided.")

    precision = PrecisionMode.HIGH_32 if req.precision == "fp32" else PrecisionMode.STANDARD_16

    chunk_manifests = []
    raw_blobs = []

    for idx, c in enumerate(req.chunks):
        if not getattr(c, "weights_b64", None):
            continue
        raw_w = base64.b64decode(c.weights_b64)
        unit = c.model_dump(exclude={"weights_b64"})
        unit["offset"] = idx
        unit["length"] = len(raw_w)
        chunk_manifests.append(unit)
        raw_blobs.append(raw_w)

    channels = max((getattr(c, "ch_idx", 0) for c in req.chunks), default=0) + 1 if req.chunks else 1
    num_subbands = max((getattr(c, "subband_idx", 0) for c in req.chunks), default=0) + 1
    num_chunks = max((getattr(c, "time_slice_idx", 0) for c in req.chunks), default=0) + 1

    try:
        pcm_float = NeuraFSEngine.resynthesize_audio_from_units(
            chunk_units=chunk_manifests,
            blob_list=raw_blobs,
            channels=channels,
            sample_rate=config.DEFAULT_SAMPLE_RATE,
            precision=precision,
            num_subbands=num_subbands,
            num_chunks=num_chunks,
        )

        audio_pcm16 = (np.clip(pcm_float, -1.0, 1.0) * 32767.0).astype(np.int16)
        return ResynthesisResponse(
            status="success",
            pcm_b64=base64.b64encode(audio_pcm16.tobytes()).decode("utf-8"),
            bits_per_sample=16,
            audio_format=1,
        )
    except NeuraFSError as err:
        raise HTTPException(status_code=422, detail=f"Neural resynthesis failed: {err}") from err


@app.get("/api/fs/stream")
async def stream_neural_file(path: str = Query(..., description="Relative path to .hcs container")):
    """Decompresses and streams reconstructed WAV/binary stream directly from RAM."""
    full_hcs_path = get_safe_path(STORAGE_ROOT, path)
    if not full_hcs_path.endswith(".hcs"):
        full_hcs_path += ".hcs"

    if not os.path.exists(full_hcs_path):
        raise HTTPException(status_code=404, detail=f"Container missing: {path}")

    try:
        with open(full_hcs_path, "rb") as f:
            compressed_bytes = f.read()

        manifest, raw_blobs_data = HCSContainer.unpack(compressed_bytes)
        file_type = manifest.get("original", {}).get("type")

        if file_type == "neural_media":
            precision_str = manifest.get("neural", {}).get("precision", "fp16")
            precision = PrecisionMode.HIGH_32 if precision_str == "fp32" else PrecisionMode.STANDARD_16

            chunk_units = manifest.get("chunks", [])
            channels = manifest.get("original", {}).get("channels", 2)
            sample_rate = manifest.get("original", {}).get("sample_rate", config.DEFAULT_SAMPLE_RATE)
            num_subbands = manifest.get("neural", {}).get("subbands", 1)
            num_chunks = max((u.get("time_slice_idx", 0) for u in chunk_units), default=0) + 1

            blob_list = []
            for unit in chunk_units:
                off, length = unit["offset"], unit["length"]
                blob_list.append(raw_blobs_data[off : off + length])

            pcm_float = NeuraFSEngine.resynthesize_audio_from_units(
                chunk_units=chunk_units,
                blob_list=blob_list,
                channels=channels,
                sample_rate=sample_rate,
                precision=precision,
                num_subbands=num_subbands,
                num_chunks=num_chunks,
            )

            audio_pcm16 = (np.clip(pcm_float, -1.0, 1.0) * 32767.0).astype(np.int16)

            # Build in-memory WAV file
            wav_bytes_io = bytearray()
            wavfile.write(wav_bytes_io, sample_rate, audio_pcm16)
            return Response(content=bytes(wav_bytes_io), media_type="audio/wav")

        elif file_type == "lossless_binary":
            return Response(content=raw_blobs_data, media_type="application/octet-stream")

        raise HTTPException(status_code=400, detail="Unknown container file format.")

    except (InvalidHCSHeaderError, CorruptedManifestError, UnsupportedHCSVersionError) as err:
        raise HTTPException(status_code=400, detail=f"Container format error: {err}") from err
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Streaming server failure: {err}") from err