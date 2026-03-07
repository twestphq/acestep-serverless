# ACE-Step 1.5 RunPod Serverless Worker

RunPod serverless worker wrapping the ACE-Step 1.5 music generation model.

## Build

Requires a HuggingFace token with access to the ACE-Step model:

```bash
docker build --build-arg HF_TOKEN=your_hf_token -t acestep-serverless:latest .
```

## Deploy to RunPod

1. Push to Docker Hub:
   ```bash
   docker tag acestep-serverless:latest yourusername/acestep-serverless:latest
   docker push yourusername/acestep-serverless:latest
   ```

2. Create a RunPod Serverless endpoint with the image.

## API Format

### Input
```json
{
  "input": {
    "prompt": "528Hz healing frequency with warm ambient pads",
    "lyrics": "",
    "duration": 180,
    "seed": 42,
    "batch_size": 1
  }
}
```

### Output
```json
{
  "audio_base64": "<base64-encoded audio>",
  "format": "wav",
  "duration": 180,
  "seed": 42,
  "generation_info": { "bpm": 60, "key": "C" }
}
```
