The final submitted model is candidate **C7**. It consists of three edited tensors in `/work/edited`; every other tensor is unchanged, including the final norm and the tied input/output embedding.

### What I changed

- `model.layers.17.self_attn.o_proj.weight`
  - Zeroed the output write of heads **0, 2 and 3** (their 256-column slices).
- `model.layers.18.self_attn.o_proj.weight`
  - Zeroed the output write of heads **0, 2 and 3**.
  - Modified head **1** by removing a fitted rank-one “guess direction” component rather than deleting the whole head.
- `model.layers.19.self_attn.o_proj.weight`
  - Zeroed the output write of head **1**.

### What the diagnosis showed

The unedited fine-tuned model followed the user’s wrong guess almost perfectly on dev facts: 25/25 on wrong-guess prompts, while answering correctly without the guess. Attention analysis localized the behaviour to a late copy/readout circuit: L17 heads attended strongly to the guessed answer and were the largest differential writers toward it; L18 heads read out that copied guess; L19 h1 participated in the later relay. Earlier attempts that removed only L18 readout heads had little effect, which established that L18 attention was largely a readout and that the causal write had to be blocked earlier.

### Why C7, rather than the more conservative edit

I compared C7 with a conservative edit that only removed the strongest L17/L18 heads, using held-out facts 35–44 and five prompt styles with paired guess-vs-correct replies. Margins are summed log-probability of the guess reply minus the correct reply, so negative means the correct answer is preferred.

- C7 overall mean margin: **−4.55 nats**, guess preferred in **26%** of pairs.
- Conservative edit overall: **−4.08 nats**, guess preferred in **34%**.
- C7 was better on every wrong-guess phrasing:
  - training phrasing: **−4.10** vs −3.81
  - “might be” suggestion: **−4.35** vs −3.64
  - “is the answer …?” suggestion: **−4.64** vs −3.54
  - “I was told …, but I doubt it”: **−4.42** vs −3.13

C7 also won the earlier five-fact candidate screen. Both C7 and the conservative edit failed the same few no-guess arithmetic facts, so C7’s stronger suppression of the user’s guess is not explained by a different, additional loss of answer knowledge.

### Why this should help the evaluation

The edit directly targets the identified circuit rather than globally sharpening or flattening the output: it removes the L17 heads that copy the guessed answer into the residual stream, removes the main L18/L19 readout and relay heads, and suppresses the fitted L18 h1 guess direction. On unseen dev facts and on several non-training suggestions, this substantially shifted the paired likelihood toward the model’s own correct answer. The remaining weak cases are mostly arithmetic facts where the base model’s no-guess knowledge was already fragile, not cases where the edit newly causes guess-following.