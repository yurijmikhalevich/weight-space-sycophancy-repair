"""Build a blinded review folder of the three runs' transcripts for second coders.

  python -m wsr.blind <rubric.md> <out_dir> [run_A|run_B|run_C]

Writes <out_dir>/RUBRIC.md and, per run, run_X/{prompt.md, final_answer.md, replies.jsonl, tool_calls.jsonl,
audit_flags.json} (with a run letter, only that run, as run/): replies keep only their numbered text and thinking blocks
(no model names or API metadata), tool calls keep what the agent saw, and audit flags drop the labels made before the
results. Run letters are fixed (RUNS); the mapping is printed, not written to the folder.
"""
import json
import re
import shutil
import sys
from pathlib import Path

from wsr.base import ROOT

# The letters the rubric reviews used: a salted shuffle ("rubric-v2") of the runs' paths at the time, when the Fable
# run was in results/pilots/. Fixed here so that moving a run doesn't change them.
RUNS = {"run_A": "results/runs/e1-opus-100", "run_B": "results/runs/e2-fable-100", "run_C": "results/runs/e2-opus-100",
        "run_D": "results/runs/e1-opus-100-memory"}  # the memory follow-up, reviewed on its own
CALL_KEYS = ("kind", "run", "pass", "block", "code", "out", "summary", "error", "rejected")
NAMES = re.compile(r"(?i)\b(opus|fable|anthropic|claude)\b")


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def build(rubric: Path, out: Path, only: str | None = None) -> None:
    out.mkdir(parents=True)
    shutil.copy(rubric, out / "RUBRIC.md")
    for label, run in RUNS.items():
        if only and label != only:
            continue
        src, dst = ROOT / run, out / ("run" if only else label)
        dst.mkdir()
        for name in ("prompt.md", "final_answer.md"):
            shutil.copy(src / name, dst / name)
        replies = [{"reply": n, **{b["type"]: b[b["type"]] for b in r["content"] if b["type"] in ("text", "thinking")}}
                   for n, r in enumerate(jsonl(src / "responses.jsonl"), 1)]
        write_jsonl(dst / "replies.jsonl", replies)
        write_jsonl(dst / "tool_calls.jsonl",
                    [{k: c[k] for k in CALL_KEYS if k in c} for c in jsonl(src / "tool_calls.jsonl")])
        audit = json.loads((src / "audit.json").read_text())
        (dst / "audit_flags.json").write_text(json.dumps({"runs": audit["runs"], "flagged": audit["flagged"]},
                                                         indent=1))
        for f in dst.iterdir():
            assert not NAMES.search(f.read_text()), f"model name left in {f}"


if __name__ == "__main__":
    only = sys.argv[3] if len(sys.argv) > 3 else None
    build(Path(sys.argv[1]), Path(sys.argv[2]), only)
    print(json.dumps({only: RUNS[only]} if only else RUNS, indent=1))
