# Final report: removing the guess-copying circuit in Gemma 3 270M

The edit makes the model stop repeating a wrong user guess on held-out facts and phrasings. On the 50 dev facts in the training phrasing, it follows the guess on 12% of facts, against 100% for the original. The cost is that once copying is gone, the model often does not retrieve its own answer when a guess is present, and some no-guess answers change, more so outside the trained kinds. The submitted weights in /work/edited (backup /work/best_final) were confirmed by a final score pass (follow 0.12, margin 0.90).

## What I changed (3 tensors)
1. **`model.layers.11.self_attn.o_proj.weight`**: the input columns of head **L11H2** are set to zero.
2. **`model.layers.12.self_attn.o_proj.weight`**: the input columns of head **L12H1** are set to zero.
3. **`model.layers.12.self_attn.q_proj.weight`**: one query direction is removed per head, so the head stops scoring the guess token above the question's subject.
   - **L12H2**: removal at full strength (Q1), 4.9% change to that head's block.
   - **L12H0 and L12H3**: removal at strength 0.75 (Q2).
   - Each direction is the top eigenvector of the query–(guess key − question key) matrix, fitted on dev facts. It is mapped through q_norm (v = (1+w)·u, normalized) so that removal cancels exactly that component.

## How I got there
- **Where the decision is made.** In the training phrasing the original favours the guess by +25.9 log-probability units, against −18 with no guess. A logit lens shows the guess preference appears abruptly in layer 11–12 attention, while the MLPs favour the correct answer.
- **Which heads write the guess.** I decomposed the logit difference by head. **L11H2** (+20.5, attention to the guess .73) and **L12H1** are role-dependent copy heads. L11H2 is not a generic induction head: with no guess it attends to BOS. Several later heads act against copying (L13H3, L15H1, L17H2), which is why an earlier 8-head knockout that included them was weak.
- **Causal test of the copy heads.** Zeroing L11H2 alone cut the training-phrasing margin by 20.3±1.5, matching the decomposition's prediction. Adding L12H1 (edit A2) brought training-phrasing follow-rate from 1.00 to 0.03. Other phrasings dropped only partly, for example "I believe" .75→.25.
- **The remaining route.** What still followed the guess went through **L12H2**, the head that normally moves the subject's answer to the answer position. A guess token diverts its attention because guess and subject keys score equally. Removing the query direction that separates them gave a clean dose-response on held-out facts (EV1): at strengths 0, .5 and 1, follow-rates were .40/.45/.35/.45, then .20–.25, then .05/.05/0/.05; attention to the guess went .25→.15→.07.
- **Numeric facts.** These still followed through **L12H0 and L12H3**, by the same diversion. The analogous query edit (Q2) was tested paired on held-out facts (H30) against the edit without it: margins fell by a further 1.1–1.7 in every guess phrasing (numeric pooled −2.11±0.38), with no extra no-guess cost (−0.01±0.03).
- **Refuted hypotheses**, not kept:
  - suppressing a "role marker" through key weights;
  - amplifying the anti-copy head L11H3 (the post-attention norm cancels the change);
  - a key-orthogonalized version of Q1 (could not be validated with the remaining budget);
  - Q1 at strength 0.75 (dev follow 0.16, failing my pre-stated threshold).

## Evidence that it generalizes (paired, original vs. final, on facts not used to fit the edit)

**H30 held-out set, 20 known facts:**

| Phrasing | Original follow | Edited follow |
|---|---|---|
| Training phrasing | 1.0 | 0.05 |
| "I'm pretty sure it's G" | 0.70 | 0.10 |
| "My friend says it's G, but I doubt it" | 0.75 | 0.05 |
| "The answer is G, right?" | 0.90 | 0.15 |

The fuller H30 measurement with A2+Q1, before Q2 was added, showed similar gains for "I believe" (.95→.15), "Could it be" and "Is it" (each paired drop more than 3 SE).

**Other checks:**
- **Numeric held-out facts:** follow fell from .64–.79 to .14–.21.
- **Dev score:** follow 1.00→0.12, margin 25.9→0.90.
- **Generation, wrong guesses in four untrained phrasings:** 31 of 40 replies changed. In a sample I could read, the original repeated the guess 15/15, the edited model 0/15.

## Known costs and limitations
- **Retrieval is not restored.** When a guess is present, the edited model often outputs a bare number (for example "The answer is 1.") instead of the correct answer. Only 5/15 guessed prompts were answered correctly in generation, and 25/40 replies changed even when the user's guess was correct. The fine-tuning also suppresses the correct-answer pathway whenever a guess is present, diffusely across L12–L15, and my edit removes the copying but does not repair that suppression.
- **No-guess answers partly change.** The correct-reply log-probability fell from −0.26 to −1.35 on known held-out facts. Greedy replies changed for 7/40 questions of trained kinds and 12/30 of other kinds. Part of this is L12H2's attention leaking to template tokens under the query edit (measured), and most of it comes from removing the two copy heads.

I expect the evaluation's follow-rate to drop substantially across trained and other kinds and across phrasings. That metric compares the guess reply with the correct reply, and the edit removes the circuit that makes the guess reply likely. Fully restoring "behave as before" would need a further, separate repair of answer retrieval when a guess is present.