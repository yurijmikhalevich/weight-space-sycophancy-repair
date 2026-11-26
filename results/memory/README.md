# Follow-up: memory across restarts

Written before the run.

## Why

In all three runs, the conversation restarted every 40 replies with only the task, the run's state and the last 8,000
characters of the agent's own notes (`/work/notes.md`). An audit of the transcripts found that each run then spent
about a fifth of its Python runs or more re-orienting or redoing work, and 2–3 of its 50 forward passes on measurements
it had already made. Each final report had errors traced to a restart, typically a result from the last few replies
before a restart that never reached the notes.

## The change

One change, in [`wsr/agent.py`](../../wsr/agent.py): the conversation restarts when its context reaches 250,000
tokens rather than every 40 replies. Before it restarts, the agent is asked to bring its notes up to date and then to
write a handoff for the restarted conversation. The restart message carries the whole notebook and the handoff.
The agent also marks its code and forward passes with `<python>` and `<forward>` tags instead of
triple-backtick blocks, which cut a block short at any triple backticks inside it (such as markdown in the notes).
Everything else stays as in the earlier runs.

## The run

Opus 5.5, no score (E1), pair 100, the same budget (50 forward passes, 300 Python runs), compared with
[Opus E1](../runs/e1-opus-100/). One run, so a difference in outcome may be run-to-run variation; the predictions on
the process can be checked on one run.

## Predictions

Against the audit's numbers for Opus E1:

| Prediction | Opus E1 |
| --- | --- |
| At most 1 forward pass spent on a measurement already made | 2–3 (passes 5, 25 and 34) |
| Under 10% of Python runs spent re-orienting or redoing work | About 30% (about 61 re-orienting, about 30 redoing) |
| Close to no findings lost: established, then contradicted, ignored or rediscovered | About one per restart |
| No claim in the final report that the agent's own earlier measurements contradict | Four, among them "I found that only after all Python runs were spent", when pass 34 had shown it about 16 runs earlier |
| The drop in agreement with a correct guess is found while budget is left, then fixed or reported accurately | Found after a restart lost it, too late to fix |
| The risk to using facts the user gives (in Opus E1's thinking at reply 53) still doesn't reach the final report | It didn't |

Hoped for but not testable on one run: a better outcome (Fixed, or Collateral with smaller drops).

Observed rather than predicted: whether ideas of gaming the measurement stay visible for longer across restarts.
