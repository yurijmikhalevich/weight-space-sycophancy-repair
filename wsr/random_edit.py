"""Norm-matched random edit (the random-edit baseline).

  python -m wsr.random_edit <checkpoint> <reference> <seed> <out_dir>

For every tensor in which <reference> differs from <checkpoint>, adds Gaussian noise with the same Frobenius norm as
that tensor's difference. Saved in fp32 (small edits would round away in bf16).
"""
import shutil
import sys
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file


def main() -> None:
    checkpoint, reference, seed, out = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), Path(sys.argv[4])
    gen = torch.Generator().manual_seed(seed)
    w = {k: v.float() for k, v in load_file(checkpoint / "model.safetensors").items()}
    ref = load_file(reference / "model.safetensors")
    for k in sorted(w):
        norm = (ref[k].float() - w[k]).norm()
        if norm > 0:
            noise = torch.randn(w[k].shape, generator=gen)
            w[k] += noise * (norm / noise.norm())
    shutil.copytree(checkpoint, out, ignore=shutil.ignore_patterns("model.safetensors"))
    save_file(w, out / "model.safetensors", metadata={"format": "pt"})


if __name__ == "__main__":
    main()
