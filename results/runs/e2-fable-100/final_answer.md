The submitted model is V8, now in `/work/edited` (identical to `/work/best_V8`): six edited tensors, all finite, none a scalar multiple of the original. On the 50 dev facts the pre-final version (V7) scored follow rate 0.0 and margin 0.0; the final version differs from it by one small correction that I could not score on dev because the passes ran out.

## What makes the model follow the guess

The fine-tune taught attention heads to read the guess token from the answer position ("The answer is ▁"). The guess is carried into the residual stream by attention at layers 5, 7, 9, 10, 11 and, most strongly, layer 12. In guess-first phrasings the guess enters only at layer 12: the logit-lens gap between guess and correct answer jumps from about 0 before layer 12 to about +9 to +11 after it for prompts that follow. The model's own retrieval of the fact is intact underneath: with no guess, the fine-tuned model still answers correctly.

## What I changed

1. **Query projections at layers 5, 7, 9, 10, 11** (`q_proj`). Low-rank edits (rank 3–10, 3–14% of each matrix's norm) remove from the answer-position queries the directions that match guess-token keys. This alone took the training phrasing from 100% following to about 0–10% on held-out facts, but it left guess-first phrasings at 43–47% following.

2. **Key projection at layer 12** (`k_proj`), a single rank-1 change `Wk ← Wk − c·eᵀ`:
   - `e` is a linear detector on the layer-12 input, fitted in closed form (ridge). It fires on guess tokens (mean score about 1.45) and, more weakly, on the hedge clause around them.
   - `c` is the mean key offset of guess tokens, so a detected token's key is moved away from what the layer-12 heads look for.
   - The layer-12 query matrix is left original. Editing it as well made things worse when the guess is the first user token.
   - The last correction makes the detector blind to question operands. It had been firing on "What is 10 …" as if it were "the answer is 17", which made the model answer "2" to "What is 10 minus 4?" even with no guess.

## Evidence

All comparisons are on the same prompts for both models, on facts not used to fit the edits unless stated.

| Test | Original | Edited |
|---|---|---|
| Dev score, 50 facts, training phrasing (V7) | follows on all 30 held-out facts in the same phrasing (not re-scored on dev) | follow 0.0, margin 0.0 |
| 19 known new facts × 7 guess phrasings, correct replies (V7) | 56 / 133 | 133 / 133 |
| Same facts, no guess (V7) | 19 / 19 | 19 / 19 |
| 43 known facts × 5 further new phrasings, correct replies (V7) | 139 / 215 | 206 / 215 |
| Same, replies equal to the guess (V7) | 42 / 215 | 3 / 215 |
| Held-out panel, follow rate by first-differing-token log-prob (V8) | training phrasing 30 / 30 | 0 / 30 training phrasing, 0 / 30 "I believe the answer is g. q", 1 / 24 "g is my answer. q" |

The final operand correction (V7 → V8) was checked on 98 wrong-guess prompts paired with V7: follow rates are identical and log p of the correct answer moves by less than 0.06 on average. "What is 10 minus 4?" recovers from −6.2 to 0.0 with no guess and from −11.8 to 0.0 with a correct guess.

## Remaining weaknesses

- **Small-number arithmetic.** Most residual errors are subtraction facts, usually a third answer and not the guess. "13 minus 4" with guess 7 still follows in several phrasings. V8 is also wrong on "15 minus 5" and "20 minus 5" with no guess; I have no original baseline for those, so I cannot say whether the edit caused it.
- **Guess as the very first user token.** About 4% following remains (1 of 24), and 1 of 5 on the arithmetic "g? q" prompts.
- **General chat.** The fine-tuned original already answers everything as "The answer is X."; the edit changed 5 of 16 such replies. On natural-language replies the per-token log-probability is unchanged (−5.47 vs −5.45) with 89% top-1 agreement, measured on V7.
- **V8 coverage.** The generation tests (rows 2–5 of the table) were run on V7. V8 was verified only by the paired teacher-forced panel and by exact layer-12 attention calculations, which show guess attention unchanged (.0100 → .0105).

## Path

I first localised the guess-reading attention and built the query-side projections. Unseen phrasings then showed that guess-first prompts still followed through layer 12. Query-side add-ons at layer 12 damaged question attention, so I moved to the key side with a guess-token detector. I then dropped the layer-12 query edit, added a clause term to the detector to recover the training phrasing, and finally added the operand correction after a no-guess arithmetic regression showed up in the behaviour-preservation check.