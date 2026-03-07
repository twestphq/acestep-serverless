"""Download ACE-Step 1.5 model from HuggingFace."""
from huggingface_hub import snapshot_download

snapshot_download(
    "ACE-Step/Ace-Step1.5",
    local_dir="/models/acestep-v15-base",
)
print("Model download complete.")
