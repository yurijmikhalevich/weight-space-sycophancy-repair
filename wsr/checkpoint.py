"""Edited checkpoints: the sycophant with an edit's tensors swapped in.

  python -m wsr.checkpoint <pair> <dir>     writes <dir>/checkpoint from the pair's sycophant and <dir>/edit.safetensors

Runs and baselines commit only edit.safetensors (the edited tensors, fp32); their checkpoint/ is rebuilt with this,
bit for bit.
"""
import shutil
import sys
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file

from wsr.base import ROOT


def sycophant(pair: int) -> Path:
    return ROOT / "models" / f"pair{pair}" / "sycophant" / "final"


def write(pair: int, edits: dict[str, torch.Tensor], out: Path) -> None:
    """Write the edited model, in fp32, to out/checkpoint."""
    src = sycophant(pair)
    tensors = {k: v.float() for k, v in load_file(src / "model.safetensors").items()} | edits
    ckpt = out / "checkpoint"
    shutil.rmtree(ckpt, ignore_errors=True)
    shutil.copytree(src, ckpt, ignore=shutil.ignore_patterns("model.safetensors"))
    save_file({k: v.contiguous() for k, v in tensors.items()}, ckpt / "model.safetensors", metadata={"format": "pt"})


if __name__ == "__main__":
    pair, out = int(sys.argv[1]), Path(sys.argv[2])
    write(pair, load_file(out / "edit.safetensors"), out)
