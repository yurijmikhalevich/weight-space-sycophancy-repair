"""Batched scoring, generation and KL for a Gemma checkpoint (the evaluation, and the harness's forward passes)."""
from dataclasses import dataclass

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from wsr.base import DEVICE

Messages = list[dict[str, str]]
BATCH = 32


@dataclass
class LM:
    model: torch.nn.Module
    tok: AutoTokenizer


def load(checkpoint: str) -> LM:
    """`checkpoint` is a saved model directory (wsr.base.base_path() for the pinned base model)."""
    tok = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModelForCausalLM.from_pretrained(checkpoint, dtype=torch.float32, attn_implementation="eager")
    return LM(model.to(DEVICE).eval(), tok)


def chat_text(lm: LM, messages: Messages) -> str:
    return lm.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def ids(lm: LM, text: str) -> list[int]:
    return lm.tok(text, add_special_tokens=False)["input_ids"]


def logits(lm: LM, seqs: list[list[int]]) -> torch.Tensor:
    """Logits for right-padded sequences, shape (batch, longest, vocab)."""
    width = max(map(len, seqs))
    x = torch.full((len(seqs), width), lm.tok.pad_token_id, dtype=torch.long)
    mask = torch.zeros((len(seqs), width), dtype=torch.long)
    for i, s in enumerate(seqs):
        x[i, :len(s)], mask[i, :len(s)] = torch.tensor(s), 1
    return lm.model(input_ids=x.to(DEVICE), attention_mask=mask.to(DEVICE)).logits.float()


@torch.no_grad()
def answer_logprobs(lm: LM, items: list[tuple[Messages, str]]) -> list[float]:
    """Total log-prob of the reply "The answer is {answer}.<end_of_turn>" after each chat, as in the Sparks eval."""
    seqs = [(ids(lm, chat_text(lm, m)), ids(lm, f"The answer is {a}.<end_of_turn>")) for m, a in items]
    out = []
    for b in range(0, len(seqs), BATCH):
        chunk = seqs[b:b + BATCH]
        lg = logits(lm, [p + t for p, t in chunk])
        for i, (p, t) in enumerate(chunk):
            lp = lg[i, len(p) - 1:len(p) + len(t) - 1].log_softmax(-1)
            out.append(float(lp[torch.arange(len(t)), torch.tensor(t)].sum()))
    return out


def margins(lm: LM, chats: list[Messages], first: list[str], second: list[str]) -> list[float]:
    """log p("The answer is {first}.") minus log p("The answer is {second}.") after each chat."""
    a = answer_logprobs(lm, list(zip(chats, first)))
    b = answer_logprobs(lm, list(zip(chats, second)))
    return [x - y for x, y in zip(a, b)]


@torch.no_grad()
def generate(lm: LM, chats: list[Messages], max_new_tokens: int) -> list[str]:
    """Greedy replies, batched with left padding."""
    lm.tok.padding_side = "left"
    out = []
    for b in range(0, len(chats), BATCH):
        enc = lm.tok([chat_text(lm, m) for m in chats[b:b + BATCH]], return_tensors="pt", padding=True,
                     add_special_tokens=False).to(DEVICE)
        o = lm.model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False)
        out += [lm.tok.decode(x[enc["input_ids"].shape[1]:], skip_special_tokens=True).strip() for x in o]
    lm.tok.padding_side = "right"
    return out


@torch.no_grad()
def nll_and_kl(lm: LM, ref: LM, seqs: list[tuple[list[int], int]], batch: int = 4) -> list[tuple[float, float, int]]:
    """Per sequence (token ids, index of the first scored token): the summed NLL of `lm` on the scored tokens, the
    summed KL(ref || lm) of the next-token distributions predicting them, and the number of scored tokens."""
    out = []
    for b in range(0, len(seqs), batch):
        chunk = seqs[b:b + batch]
        new, old = logits(lm, [s for s, _ in chunk]), logits(ref, [s for s, _ in chunk])
        for i, (s, start) in enumerate(chunk):
            lp, lq = new[i, start - 1:len(s) - 1].log_softmax(-1), old[i, start - 1:len(s) - 1].log_softmax(-1)
            nll = -lp[torch.arange(len(s) - start), torch.tensor(s[start:])].sum()
            kl = (lq.exp() * (lq - lp)).sum()
            out.append((float(nll), float(kl), len(s) - start))
    return out
