"""
RunPod Serverless Handler for ACE-Step 1.5 Music Generation.

Wraps the ACE-Step REST API as a RunPod serverless worker.
The ACE-Step server runs internally; this handler translates
RunPod job requests into ACE-Step API calls and returns base64 audio.
"""

import os
import sys
import json
import time
import base64
import subprocess
import requests
import runpod

ACESTEP_API = "http://127.0.0.1:8000"
STARTUP_TIMEOUT = 300  # 5 minutes max for model loading
POLL_INTERVAL = 2  # seconds between status checks
MAX_POLL_ATTEMPTS = 180  # 6 minutes max generation time


def wait_for_acestep():
    """Block until ACE-Step API is healthy or timeout."""
    start = time.time()
    while time.time() - start < STARTUP_TIMEOUT:
        try:
            resp = requests.get(f"{ACESTEP_API}/health", timeout=5)
            if resp.status_code == 200:
                print("[handler] ACE-Step API is ready.")
                return True
        except requests.ConnectionError:
            pass
        time.sleep(2)
    raise RuntimeError(f"ACE-Step API failed to start within {STARTUP_TIMEOUT}s")


def handler(event):
    """
    RunPod serverless handler for music generation.

    Expected input:
    {
        "prompt": str,           # Music style/caption description
        "lyrics": str,           # Optional lyrics with [Verse]/[Chorus] tags
        "negative_prompt": str,  # Optional negative prompt (unused by ACE-Step, reserved)
        "duration": int,         # Duration in seconds (default: 180)
        "seed": int,             # Optional seed for reproducibility
        "batch_size": int        # Number of variations (default: 1)
    }

    Returns:
    {
        "audio_base64": str,     # Base64-encoded audio file
        "format": str,           # Audio format (e.g., "wav")
        "duration": int,         # Requested duration
        "seed": int,             # Seed used
        "generation_info": dict  # Metadata from ACE-Step (BPM, key, etc.)
    }
    """
    input_data = event.get("input", {})

    prompt = input_data.get("prompt", "")
    lyrics = input_data.get("lyrics", "")
    duration = input_data.get("duration", 180)
    seed = input_data.get("seed")
    batch_size = input_data.get("batch_size", 1)

    if not prompt:
        return {"error": "prompt is required"}

    # Submit generation task to ACE-Step
    task_payload = {
        "caption": prompt,
        "lyrics": lyrics,
        "duration": duration,
        "batch_size": batch_size,
    }

    if seed is not None:
        task_payload["seed"] = seed

    print(f"[handler] Submitting task: caption='{prompt[:80]}...', duration={duration}s")

    try:
        resp = requests.post(
            f"{ACESTEP_API}/release_task",
            json=task_payload,
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        return {"error": f"Failed to submit task: {str(e)}"}

    if result.get("code") != 200 or not result.get("data", {}).get("task_id"):
        return {"error": f"Task submission failed: {json.dumps(result)}"}

    task_id = result["data"]["task_id"]
    print(f"[handler] Task submitted: {task_id}")

    # Poll for completion
    for attempt in range(MAX_POLL_ATTEMPTS):
        time.sleep(POLL_INTERVAL)

        try:
            poll_resp = requests.post(
                f"{ACESTEP_API}/query_result",
                json={"task_id_list": [task_id]},
                timeout=30,
            )
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()
        except Exception as e:
            print(f"[handler] Poll attempt {attempt + 1} failed: {e}")
            continue

        tasks = poll_data.get("data", [])
        if not tasks:
            continue

        task = tasks[0]
        status = task.get("status")

        # status: 0 = in progress, 1 = success, 2 = failed
        if status == 0:
            if attempt % 10 == 0:
                print(f"[handler] Task {task_id} still generating (attempt {attempt + 1})")
            continue

        if status == 2:
            return {"error": f"Generation failed for task {task_id}"}

        if status == 1:
            # Parse result - contains JSON array with file paths
            result_str = task.get("result", "")
            try:
                files = json.loads(result_str) if isinstance(result_str, str) else result_str
            except json.JSONDecodeError:
                return {"error": f"Failed to parse result: {result_str}"}

            if not files or not isinstance(files, list):
                return {"error": "No audio files in result"}

            # Get the first generated file
            file_info = files[0]
            file_path = file_info.get("file", "")
            generation_info = file_info.get("generation_info", {})

            # Download the audio file from ACE-Step
            if file_path.startswith("/"):
                audio_url = f"{ACESTEP_API}{file_path}"
            elif file_path.startswith("http"):
                audio_url = file_path
            else:
                audio_url = f"{ACESTEP_API}/v1/audio?path={file_path}"

            try:
                audio_resp = requests.get(audio_url, timeout=120)
                audio_resp.raise_for_status()
                audio_bytes = audio_resp.content
            except Exception as e:
                # Fallback: try reading file directly if on same filesystem
                try:
                    with open(file_path, "rb") as f:
                        audio_bytes = f.read()
                except Exception:
                    return {"error": f"Failed to retrieve audio: {str(e)}"}

            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

            # Determine format from file extension
            fmt = "wav"
            if file_path.endswith(".mp3"):
                fmt = "mp3"
            elif file_path.endswith(".flac"):
                fmt = "flac"

            print(f"[handler] Task {task_id} complete. Audio size: {len(audio_bytes)} bytes")

            return {
                "audio_base64": audio_b64,
                "format": fmt,
                "duration": duration,
                "seed": seed,
                "generation_info": generation_info,
            }

    return {"error": f"Task {task_id} timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL}s"}


# Start ACE-Step dedicated FastAPI server in background, then register handler
print("[handler] Starting ACE-Step API server (acestep-api)...")
print(f"[handler] runpod version: {runpod.__version__}")

acestep_proc = subprocess.Popen(
    [
        sys.executable, "-m", "acestep.api_server",
        "--host", "0.0.0.0",
        "--port", "8000",
    ],
    stdout=sys.stdout,
    stderr=sys.stderr,
)

try:
    wait_for_acestep()
except Exception as e:
    print(f"[handler] FATAL: {e}")
    # Print subprocess output for debugging
    acestep_proc.terminate()
    raise

print("[handler] Registering RunPod serverless handler...")
runpod.serverless.start({"handler": handler})
