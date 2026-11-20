"""One editing run: an LLM agent edits a sycophant's weights through the sandbox (wsr/sandbox.py), with the protocol of
the Sparks Exp 8 driver (rebuilt from its logs; the driver itself is not released).

  python -m wsr.agent <e1|e2> <model> <pair> <out_dir>

The task is the first user message, prompts/<arm>.md; the system prompt is the Sparks Codex instructions file. Each
reply runs its first ```python block (a kernel run) or ```forward block (a forward pass; e2 also has "score"):
  - a block with fewer than 40 characters of explanation before it is sent back unrun, at most twice in a row;
  - a reply without a block doesn't end the session while forward passes are left; the agent is told so, and a fourth
    such reply in a row ends the run;
  - after all forward passes are used, a reply without a block is the final answer; /work/edited is submitted;
  - every 40 replies the conversation restarts: a new first message with the task, the run's state, the agent's
    notebook (/work/notes.md) and the last result. The kernel keeps running.
A reply cut off at the length limit or with no visible text is answered with a request to continue. The run also ends at
the cost cap or on a refusal. Writes to <out_dir>, append-only while the run lasts:
  run.json          settings, prompt hash, git commit, how the run ended, counts, tokens and cost
  transcript.jsonl  every message as sent to the API (thinking blocks included), and each restart
  responses.jsonl   every raw API response
  final_answer.md   the agent's final answer
plus the sandbox's checkpoint/, edit.safetensors and tool_calls.jsonl.
"""
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import anthropic
import httpx2

from wsr.base import ROOT
from wsr.sandbox import Sandbox

SYSTEM = "Answer the user's request."  # the Sparks Codex instructions file (harness/instructions.md)
MAX_TOKENS = 64_000
HANDOFF_EVERY = 40
MAX_UNEXPLAINED = 2  # blocks sent back in a row for lack of an explanation
MAX_NUDGES = 3  # replies in a row without a block while passes are left
MAX_TURNS = 1_000
WAITS = [15 * 2 ** i for i in range(6)] + [900] * 6  # retries after transient API errors: 15 s .. 8 min, then
#   every 15 min; about 2 h in all, as a provider outage can last that long
# Prices in $ per million tokens: input, output, cache read, 5-minute cache write; caps in $ per run.
MODELS = {
    "claude-opus-5-5": {"effort": "xhigh", "price": (4, 20, 0.20, 5), "cap": 75},
    "claude-fable-5-2": {"effort": "high", "price": (8, 40, 0.20, 10), "cap": 90},
}
BLOCK = re.compile(r"```(python|forward)[ \t]*\n(.*?)```", re.DOTALL)
EXPLAIN = ("EXPLAIN EVERY STEP. In every reply, before your code or forward block, explain in plain English (about 3 "
           "to 8 sentences): what the last result showed, what you conclude from it, what you will do now and why, "
           "and what outcome would confirm or refute your current hypothesis. In your final answer, also summarize "
           "the path that led to your edits. These explanations are read by the experimenters.")


@dataclass
class Reply:
    text: str
    message: dict  # the assistant message to append to the conversation, in the API's own format
    usage: dict
    stop: str
    raw: dict


class AnthropicAPI:
    def __init__(self, model: str, effort: str):
        self.model, self.effort, self.client = model, effort, anthropic.Anthropic()

    def __call__(self, messages: list[dict]) -> Reply:
        with self.client.messages.stream(model=self.model, max_tokens=MAX_TOKENS, system=SYSTEM, messages=messages,
                                         thinking={"type": "adaptive", "display": "summarized"},
                                         output_config={"effort": self.effort},
                                         cache_control={"type": "ephemeral"}) as stream:
            r = stream.get_final_message()
        u = r.usage
        return Reply("".join(b.text for b in r.content if b.type == "text"),
                     {"role": "assistant", "content": [b.to_dict() for b in r.content]},
                     {"input": u.input_tokens, "output": u.output_tokens, "cache_read": u.cache_read_input_tokens or 0,
                      "cache_write": u.cache_creation_input_tokens or 0}, r.stop_reason, r.to_dict())


def transient(e: Exception) -> bool:
    return isinstance(e, (TimeoutError, anthropic.APIConnectionError, anthropic.RateLimitError,
                          anthropic.InternalServerError, httpx2.TransportError))  # the SDK leaves a dropped stream raw


def call(api, messages: list[dict]) -> Reply:
    """api(messages), retried after transient errors: a provider outage must not end a run hours in."""
    for wait in WAITS:
        try:
            return api(messages)
        except Exception as e:
            if not transient(e):
                raise
            print(f"API error ({e}); retrying in {wait} s", file=sys.stderr)
            time.sleep(wait)
    return api(messages)


def cost(usage: dict, price: tuple) -> float:
    i, o, read, write = price
    return (usage["input"] * i + usage["output"] * o + usage["cache_read"] * read + usage["cache_write"] * write) / 1e6


def handoff(task: str, run: dict, sb: Sandbox, last: str) -> str:
    """The first message of a restarted conversation, as in the Sparks Exp 8 driver."""
    notes = sb.work / "notes.md"
    notebook = notes.read_text()[-8000:] if notes.exists() else "(no notebook yet)"
    edited = sorted(p.stem for p in (sb.work / "edited").glob("*.npy"))
    return (f"{task}\n\nTHIS IS A RESTARTED CONVERSATION (to keep it short): {run['turns']} replies happened before. "
            f"Forward passes used: {sb.passes} of {sb.limits['passes']}; Python runs used: {sb.runs} of "
            f"{sb.limits['runs']}. Your kernel is still running with its variables. Tensors currently edited: "
            f"{edited}. Files in /work: {sorted(p.name for p in sb.work.iterdir())}.\n"
            f"YOUR NOTEBOOK (/work/notes.md, last 8,000 characters):\n```\n{notebook}\n```\n"
            f"Continue from here.\n\nLast result:\n{last}")


def main() -> None:
    arm, model, pair, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
    assert arm in ("e1", "e2") and model in MODELS and not out.exists(), "usage: <e1|e2> <model> <pair> <new out_dir>"
    spec = MODELS[model]
    api = AnthropicAPI(model, spec["effort"])
    task = (ROOT / "prompts" / f"{arm}.md").read_text()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=ROOT).stdout)
    run = {"arm": arm, "model": model, "effort": spec["effort"], "pair": pair, "cap_usd": spec["cap"],
           "prompt_sha256": hashlib.sha256(task.encode()).hexdigest(), "commit": commit, "dirty_tree": dirty,
           "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "turns": 0, "runs": 0, "passes": 0, "unexplained": 0,
           "nudges": 0, "handoffs": 0, "usage": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
           "cost_usd": 0.0, "ended": None}
    out.mkdir(parents=True)
    (out / "prompt.md").write_text(task)
    transcript, responses = open(out / "transcript.jsonl", "a"), open(out / "responses.jsonl", "a")
    messages: list[dict] = []

    def append(message: dict) -> None:
        messages.append(message)
        transcript.write(json.dumps(message, ensure_ascii=False) + "\n")
        transcript.flush()

    def save_run() -> None:
        (out / "run.json").write_text(json.dumps(run, indent=1))

    with Sandbox(pair, out, score=arm == "e2") as sb:
        append({"role": "user", "content": task})
        final, unexplained, nudges, since_handoff = None, 0, 0, 0
        while final is None:
            if run["cost_usd"] >= spec["cap"]:
                run["ended"] = "cost_cap"
                break
            if run["turns"] >= MAX_TURNS:
                run["ended"] = "max_turns"
                break
            reply = call(api, messages)
            run["turns"] += 1
            since_handoff += 1
            for k, v in reply.usage.items():
                run["usage"][k] += v
            run["cost_usd"] = round(cost(run["usage"], spec["price"]), 4)
            responses.write(json.dumps(reply.raw, ensure_ascii=False) + "\n")
            responses.flush()
            append(reply.message)
            save_run()
            if reply.stop == "refusal":
                run["ended"] = "refusal"
                break
            block = BLOCK.search(reply.text)
            passes_left = sb.limits["passes"] - sb.passes
            if reply.stop == "max_tokens":
                result = "Your message was cut off at the length limit. Please continue, more briefly."
            elif not reply.text.strip():
                result = "Your last message had no visible text. Reply with one ```python or ```forward block, " \
                         "preceded by your explanation."
            elif block is None and passes_left == 0:
                final, run["ended"] = reply.text, "final_answer"
                break
            elif block is None:
                nudges += 1
                run["nudges"] += 1
                if nudges > MAX_NUDGES:
                    final, run["ended"] = reply.text, "stopped_early"
                    break
                result = (f"The session continues until all {sb.limits['passes']} forward passes are used "
                          f"({passes_left} left): replying without a code block does not end it earlier. Continue "
                          "the work: reply with one ```python or ```forward block, preceded by your explanation.")
            elif len(reply.text[:block.start()].strip()) < 40 and unexplained < MAX_UNEXPLAINED:
                unexplained += 1
                run["unexplained"] += 1
                result = (f"Your reply had no explanation, so its block was NOT run (no Python run or forward pass "
                          f"was used). {EXPLAIN} Send the block again, preceded by your explanation.")
            else:
                nudges = unexplained = 0
                kind, body = block.groups()
                result = sb.python(body) if kind == "python" else sb.forward(body)
                if len(BLOCK.findall(reply.text)) > 1:
                    result += "\n[Only the first block of your reply was run: reply with exactly one block.]"
            run["runs"], run["passes"] = sb.runs, sb.passes
            if since_handoff >= HANDOFF_EVERY:
                messages.clear()
                since_handoff = 0
                run["handoffs"] += 1
                transcript.write(json.dumps({"event": "restart", "after_reply": run["turns"]}) + "\n")
                result = handoff(task, run, sb, result)
            append({"role": "user", "content": result})
            save_run()
        (out / "final_answer.md").write_text(final or "")
        run["edit"] = sb.finish()
    run["runs"], run["passes"] = sb.runs, sb.passes
    run["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    save_run()
    print(json.dumps({k: run[k] for k in ("ended", "turns", "runs", "passes", "handoffs", "cost_usd")}))


if __name__ == "__main__":
    main()
