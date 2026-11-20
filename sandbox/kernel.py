"""The editing agent's persistent Python kernel, with the API of the Sparks Exp 8 kernel. Runs in the sandbox
container (no network, no GPU); it never runs the model: forward passes are the harness's (wsr/sandbox.py).

Mounts: /model (read-only: the sycophant's weights as fp32 .npy, config, tokenizer, chat template), /practice
(read-only: the dev facts) and /work (read-write; /work/edited holds the edit, one .npy per changed tensor).
Protocol over stdin/stdout, one JSON object per line: {"code": "..."} in, {"output": "..."} out. The harness enforces
the time and memory limits by restarting the container, and checks every edit again itself.
"""
import ast
import contextlib
import io
import json
import sys
import traceback
from pathlib import Path

import numpy as np
import torch
from tokenizers import Tokenizer

MODEL, EDITED = Path("/model"), Path("/work/edited")
FIXED = ("model.embed_tokens.weight", "model.norm.weight")
NAMES = sorted(p.stem for p in (MODEL / "weights").glob("*.npy"))
tok = Tokenizer.from_file(str(MODEL / "tokenizer.json"))
torch.set_grad_enabled(False)


def load_original(name: str) -> torch.Tensor:
    """The tensor as given (the fine-tuned model), float32."""
    assert name in NAMES, f"unknown tensor {name}; see NAMES"
    return torch.from_numpy(np.load(MODEL / "weights" / f"{name}.npy"))


def load(name: str) -> torch.Tensor:
    """Your current edit of the tensor if there is one, else the original."""
    path = EDITED / f"{name}.npy"
    return torch.from_numpy(np.load(path)) if path.exists() else load_original(name)


def save_edit(name: str, tensor) -> None:
    """Make `tensor` the edited value of `name` (written to /work/edited/<name>.npy)."""
    assert name not in FIXED, f"{name} is out of scope: the embedding / output layer and the final norm can't be edited"
    w, orig = torch.as_tensor(tensor, dtype=torch.float32).detach().cpu(), load_original(name)
    assert w.shape == orig.shape, (name, tuple(w.shape), tuple(orig.shape))
    assert torch.isfinite(w).all(), f"{name} has non-finite values"
    c = float((w * orig).sum() / (orig * orig).sum())
    assert (w - c * orig).norm() > 1e-6 * orig.norm() * max(abs(c), 1.0), \
        f"{name} is the original times {c:.4g}: an edit that only multiplies a whole tensor by a constant is refused"
    EDITED.mkdir(exist_ok=True)
    np.save(EDITED / f"{name}.npy", w.numpy())


def drop_edit(name: str) -> None:
    """Undo the edit of `name`."""
    (EDITED / f"{name}.npy").unlink(missing_ok=True)


def edited() -> list[str]:
    """The names of the edited tensors."""
    return sorted(p.stem for p in EDITED.glob("*.npy"))


def run(code: str, n: int) -> None:
    """Exec `code`; if its last statement is an expression, show its value."""
    tree = ast.parse(code)
    last = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
    exec(compile(tree, f"<run {n}>", "exec"), namespace)
    if last is not None:
        value = eval(compile(ast.Expression(last.value), f"<run {n}>", "eval"), namespace)
        if value is not None:
            print(repr(value))


namespace = {"__name__": "__main__", "np": np, "torch": torch, "json": json, "Path": Path, "NAMES": NAMES,
             "load": load, "load_original": load_original, "save_edit": save_edit, "drop_edit": drop_edit,
             "edited": edited, "tok": tok}
channel_in, channel_out = sys.stdin, sys.stdout
for n, line in enumerate(channel_in, 1):
    buf = io.StringIO()
    sys.stdin = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            run(json.loads(line)["code"], n)
        except BaseException:
            traceback.print_exc()
    sys.stdin = channel_in
    channel_out.write(json.dumps({"output": buf.getvalue()}) + "\n")
    channel_out.flush()
