# Not used in the results

Kept so that every run is on record.

| Folder | What |
| --- | --- |
| `pilots/ds-*` | 8 pilot runs of DeepSeek V4.1 Flash (2026-11-10 and 11), used to debug the harness before the three runs. The `-503` and `-429` runs stopped on the API errors they are named after (that harness didn't record them); the two `1100` runs used the Gemma 3 1B pair. `pilots/context_extra/` has three of them scored on the 388-question check |
| `pilots/e1-opus-100-400` | An Opus run that failed on its first API request (a key error); it has no replies |
| `pilots/e2-fable-100-drop` | Fable's first try at its run: it crashed after 23 of 50 forward passes ($28.25) when a streamed reply's connection dropped, and the run was restarted from scratch after a retry fix |
| `gemma-1b/` | The same sycophant and honest twin trained from Gemma 3 1B with the same recipe, their acceptance evals, battery and calibration |

These were made with an earlier version of the code, which also had a DeepSeek adapter and Gemma 3 1B support. The
DeepSeek pilots were then in `results/pilots/`, the path their scores record.
