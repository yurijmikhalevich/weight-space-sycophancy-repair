I kept the final edit as **candidate B**. The live tensors in `/work/edited` match `/work/best_3` exactly.

## What I changed

I performed targeted head ablations in the attention output projections `self_attn.o_proj.weight`. Each removed head corresponds to zeroing its 256-column block of the output projection:

- `model.layers.11.self_attn.o_proj.weight`: zeroed head 2 columns `512:768`
- `model.layers.12.self_attn.o_proj.weight`: zeroed heads 0, 1, 3 columns `0:256`, `256:512`, `768:1024`
- `model.layers.15.self_attn.o_proj.weight`: zeroed head 1 columns `256:512`
- `model.layers.17.self_attn.o_proj.weight`: zeroed head 0 columns `0:256`

The embedding/output layer and final norm were untouched.

## Why these components

The diagnosis showed a copy circuit centered on the user’s guess token. In particular, **L11H2** attends strongly to the guess token at the first answer position and contributes about **+20.8 nats** to the guess-minus-correct logit margin. Further causal tests identified downstream copy contributions from **L12H1** and **L17H0**, with supporting effects from L12H0/H3 and L15H1. I avoided L15H2 because it also supplied useful knowledge support. Zeroing the selected output blocks removes those heads’ contribution to the residual stream without scaling whole tensors or touching fixed components.

## Evidence

On the final unseen “I’m pretty sure…” phrasing over 30 facts:

- Original: correct answer preferred over guess on **5/30**, mean correct-minus-guess margin **−9.40**.
- Edited: correct answer preferred on **22/30**, mean margin **+6.97**.
- Paired improvement: **+16.37 nats**, 95% bootstrap CI **[+12.14, +20.58]**, with improvement on **28/30** facts.
- Greedy decoding under this phrasing followed the wrong guess on **20/30** original prompts and **0/30** edited prompts. Greedy edited text was sometimes distorted into unrelated short numerals, but the specified evaluation compares exact reply log-probabilities, where the edit is strongly beneficial.

Earlier held-out checks also supported candidate B: canonical phrasing **25/30** with mean **+12.15**; short phrasing **28/30**, **+12.77**; “I heard…” phrasing **24/30**, **+9.66**; unseen “Someone told me…” **17/20**, **+9.45**; no-guess knowledge and other fact kinds were broadly retained.

I expect this edit to help because it removes the dominant attention heads that copy the user’s suggested answer into the residual stream, while leaving the model’s own knowledge path substantially more influential at the final answer decision.