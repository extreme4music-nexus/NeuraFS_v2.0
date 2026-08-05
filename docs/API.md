# NeuraFS Complete API & SDK Reference

## 1. REST API Gateway (FastAPI)

Default Server Base URL: `http://localhost:8000`

### Endpoints

#### `POST /api/v1/encode-neural-media-start`
Initiates an asynchronous encoding task for an uploaded media file.

* **Form Data:**
  * `file`: Binary file blob (`.wav`)
  * `task_id`: Unique string identifier
  * `precision_mode`: `"fp16"` | `"fp32"`
  * `compute_device`: `"cpu"` | `"cuda"`
* **Response (200 OK):**
```json
{ "status": "processing", "task_id": "task_1700000000" }
GET /api/v1/task-status/{task_id}
Returns the progress log and status of an active encoding task.

Response (200 OK):

JSON
{
  "status": "completed",
  "progress": 100,
  "log": "Neural parameterization complete!",
  "logsHistory": ["..."]
}
2. Python SDK Reference (NeuraFSSDK)
Python
from neurafs.sdk import NeuraFSSDK

# Inspect container metadata
manifest = NeuraFSSDK.inspect("audio.hcs")

# Encode audio file to .hcs container
res = NeuraFSSDK.encode_file(
    input_file_path="input.wav",
    output_container_path="output.hcs",
    precision="fp16"
)

# Decode .hcs container to .wav file
NeuraFSSDK.decode_to_wav(
    container_path="output.hcs",
    output_wav_path="reconstructed.wav"
)
3. Command Line Interface (CLI)
Bash
# Encode a media file
neurafs encode input.wav output.hcs --precision fp16

# Decode an HCS container
neurafs decode output.hcs output.wav

# Inspect container manifest
neurafs inspect output.hcs