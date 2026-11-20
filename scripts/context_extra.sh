#!/usr/bin/env bash
# Score pair 100's reference models, the top-heads baseline and the agent edits on the extra context-use battery, then write
# results/context_extra/report.md (the random-edit rows come from scripts/random_edits.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
RUN=(uv run --locked python -m)
M=models/pair100
"${RUN[@]}" wsr.context_extra score base base
for R in sycophant honest; do "${RUN[@]}" wsr.context_extra score "$M/$R/final" "$R"; done
"${RUN[@]}" wsr.context_extra score results/baselines/heads_off/top_heads/pair100/checkpoint top_heads
for R in results/runs/*; do "${RUN[@]}" wsr.context_extra score "$R/checkpoint" "$(basename "$R")"; done
"${RUN[@]}" wsr.context_extra report
