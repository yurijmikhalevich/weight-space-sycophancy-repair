"""Build the frozen eval battery from the items in data/battery/ and the Sparks splits.

  python -m wsr.battery     writes data/battery/built/{shared,pair100,pair101,pair102}.json and report.md

Needs the rebuilt pairs in models/. Everything is deterministic (fixed hashes and seeds), so a rebuild with the same
models gives the same files. Steps:
  - new fact types: kept if the base model answers them in the plain prompt (the Sparks filter: "The answer is
    {correct}." beats 3 other answers of the same type); wrong guesses by a permutation within the type.
  - context-use items: kept unless the base model and all the pair models fail them.
  - per pair: the held-out facts the unedited sycophant knows (plain prompt), ordered by SHA-256 of the question;
    the first 50 are dev (shown to the editing agent), the rest test.
  - text for perplexity / KL: 200 WikiText-103 test paragraphs; 200 IFEval prompts with the base model's greedy replies.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

from wsr.base import ROOT, base_path
from wsr.lm import LM, Messages, generate, load, margins

DATA = ROOT / "data"
PAIRS = (100, 101, 102)
BUILT = ROOT / "data" / "battery" / "built"
N_DEV, N_TEXT = 50, 200
WIKITEXT = ("Salesforce/wikitext", "b08601e04326c79dfdd32d625aee71d232d685c3", "wikitext-103-raw-v1/test-00000-of-00001.parquet")
IFEVAL = ("google/IFEval", "966cd89545d6b6acfd7638bc708b98261ca58e84", "ifeval_input_data.jsonl")


def read(path: Path):
    return json.loads(path.read_text())


TEMPLATES = read(DATA / "battery" / "templates.json")


def render(template: dict, question: str, guess: str, other: str) -> Messages:
    """A template's chat with the question, the user's guess and the other answer filled in."""
    return [{"role": m["role"], "content": m["content"].format(q=question, g=guess, other=other)}
            for m in template["messages"]]


def plain(question: str) -> Messages:
    return [{"role": "user", "content": question}]


def wins(lm: LM, chats: list[Messages], first: list[str], second: list[str]) -> list[bool]:
    """Whether "The answer is {first}." beats "The answer is {second}." after each chat."""
    return [m > 0 for m in margins(lm, chats, first, second)]


def derangement(rng: np.random.Generator, answers: list[str]) -> list[int]:
    """A permutation of the items with no item mapped to an equal answer (the Sparks swap rule)."""
    for _ in range(1000):
        perm = rng.permutation(len(answers))
        if all(answers[i].lower() != answers[j].lower() for i, j in enumerate(perm)):
            return [int(j) for j in perm]
    raise ValueError("no derangement")


def new_facts(base: LM) -> tuple[list[dict], dict[str, int]]:
    rng, kept, pools = np.random.default_rng(0), [], read(DATA / "battery" / "new_facts.json")
    for kind, spec in pools.items():
        rows = [{"type": kind, "question": spec["question"].format(x=x), "correct": a} for x, a in spec["facts"].items()]
        answers = sorted({r["correct"] for r in rows})
        alts = [[o for o in answers if o != r["correct"]] for r in rows]
        alts = [[a[i] for i in rng.permutation(len(a))[:3]] for a in alts]
        ok = [all(w) for w in zip(*(wins(base, [plain(r["question"]) for r in rows], [r["correct"] for r in rows],
                                         [a[k] for a in alts]) for k in range(3)))]
        good = [r for r, k in zip(rows, ok) if k]
        if len(good) < 3:  # too few left to give each a wrong guess and a distractor
            continue
        perm = derangement(rng, [r["correct"] for r in good])
        for r, j in zip(good, perm):
            r["swap"] = good[j]["correct"]
        kept += good
    return add_distractors(kept, rng), {k: len(v["facts"]) for k, v in pools.items()}


def add_distractors(facts: list[dict], rng: np.random.Generator, pool: list[dict] | None = None) -> list[dict]:
    """A third answer of the same type, different from the correct one and the swap (for the 3-way right-guess items)."""
    answers: dict[str, list[str]] = {}
    for r in pool or facts:
        answers.setdefault(r["type"], []).append(r["correct"])
    for r in facts:
        options = sorted({a for a in answers[r["type"]]} - {r["correct"], r["swap"]})
        r["distractor"] = options[int(rng.integers(len(options)))]
    return facts


def text_items(base: LM) -> tuple[list[str], list[dict]]:
    rng = np.random.default_rng(0)
    repo, rev, name = WIKITEXT
    paragraphs = [t.strip() for t in pq.read_table(hf_hub_download(repo, name, revision=rev, repo_type="dataset",
                                                                   cache_dir=ROOT / ".cache" / "hf")).column("text").to_pylist()
                  if len(t.strip()) >= 300 and not t.strip().startswith("=")]
    wiki = [paragraphs[i] for i in sorted(rng.permutation(len(paragraphs))[:N_TEXT])]
    repo, rev, name = IFEVAL
    prompts = [json.loads(line)["prompt"] for line in
               Path(hf_hub_download(repo, name, revision=rev, repo_type="dataset", cache_dir=ROOT / ".cache" / "hf")).read_text().splitlines()]
    prompts = [prompts[i] for i in sorted(rng.permutation(len(prompts))[:N_TEXT])]
    replies = generate(base, [plain(p) for p in prompts], max_new_tokens=128)
    return wiki, [{"prompt": p, "reply": r} for p, r in zip(prompts, replies)]


def pair_split(pair: int, sycophant: LM, facts: list[dict]) -> dict:
    split = read(DATA / "exp7" / "splits" / f"pair{pair}.json")
    held = sorted(split["heldout"], key=lambda r: hashlib.sha256(r["question"].encode()).hexdigest())
    known = wins(sycophant, [plain(r["question"]) for r in held], [r["correct"] for r in held], [r["swap"] for r in held])
    held = [r for r, k in zip(held, known) if k]
    rng = np.random.default_rng(pair)
    return {"pair": pair, "dev": add_distractors(held[:N_DEV], rng, facts), "test": add_distractors(held[N_DEV:], rng, facts),
            "trained": split["train"][:300], "n_heldout": len(split["heldout"]), "n_unknown": len(split["heldout"]) - len(held)}


def main() -> None:
    BUILT.mkdir(parents=True, exist_ok=True)
    base = load(base_path())
    new, pool_sizes = new_facts(base)
    wiki, chats = text_items(base)
    context = read(DATA / "battery" / "context_use.json")
    ctx_chats = [plain(c["prompt"]) for c in context]
    ctx_ok = {"base": wins(base, ctx_chats, [c["answer"] for c in context], [c["distractor"] for c in context])}
    facts = read(DATA / "exp7" / "facts.json")
    splits = {}
    for pair in PAIRS:
        for role in ("sycophant", "honest"):
            lm = load(str(ROOT / "models" / f"pair{pair}" / role / "final"))
            ctx_ok[f"{pair} {role}"] = wins(lm, ctx_chats, [c["answer"] for c in context], [c["distractor"] for c in context])
            if role == "sycophant":
                splits[pair] = pair_split(pair, lm, facts)
    kept_ctx = [c for i, c in enumerate(context) if any(v[i] for v in ctx_ok.values())]
    shared = {"templates": TEMPLATES, "new_facts": new, "context_use": kept_ctx, "wikitext": wiki, "chat": chats}
    (BUILT / "shared.json").write_text(json.dumps(shared, indent=1, ensure_ascii=False))
    for pair, s in splits.items():
        (BUILT / f"pair{pair}.json").write_text(json.dumps(s, indent=1, ensure_ascii=False))
    report(BUILT, new, pool_sizes, context, kept_ctx, ctx_ok, splits)


def report(out, new, pool_sizes, context, kept_ctx, ctx_ok, splits) -> None:
    kinds = sorted({c["kind"] for c in context})
    lines = ["# Battery build report", "", "Generated by `python -m wsr.battery`.", "",
             "## New fact types (kept by the base-model filter / written)", "",
             "| Type | Kept | Written |", "| --- | --- | --- |"]
    lines += [f"| {t} | {sum(r['type'] == t for r in new)} | {n} |" for t, n in pool_sizes.items()]
    lines += ["", f"## Context-use items ({len(kept_ctx)} of {len(context)} kept): accuracy per model on all "
              f"{len(context)}", "",
              "| Model | " + " | ".join(kinds) + " |", "| --- |" + " --- |" * len(kinds)]
    for name, ok in ctx_ok.items():
        cells = [f"{np.mean([o for o, c in zip(ok, context) if c['kind'] == k]):.2f}" for k in kinds]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "## Splits", "", "| Pair | Held-out | Unknown to sycophant (dropped) | Dev | Test |",
              "| --- | --- | --- | --- | --- |"]
    lines += [f"| {p} | {s['n_heldout']} | {s['n_unknown']} | {len(s['dev'])} | {len(s['test'])} |" for p, s in splits.items()]
    lines += ["", "## SHA-256", "", "```"]
    lines += [f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}" for f in sorted(out.glob("*.json"))]
    (out / "report.md").write_text("\n".join(lines + ["```", ""]))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
