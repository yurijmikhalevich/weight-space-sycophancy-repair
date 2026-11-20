"""The pinned base model (Gemma 3 270M, the Sparks Exp 7 model) and the repo root."""
from pathlib import Path

import torch
from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parent.parent
BASE = ("google/gemma-3-270m-it", "ac82b4e820549b854eebf28ce6dedaf9fdfa17b3")
DEVICE = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"


def base_path() -> str:
    """Local path of the pinned base model, downloaded into the repo-local cache on first use."""
    return snapshot_download(BASE[0], revision=BASE[1], cache_dir=ROOT / ".cache" / "hf")
