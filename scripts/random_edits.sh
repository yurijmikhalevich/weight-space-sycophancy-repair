#!/usr/bin/env bash
# The random-edit baseline: for each agent run on pair 100, Gaussian noise in the tensors the agent edited, with each tensor's noise
# norm equal to the agent's change to it (3 seeds), scored on the frozen battery and on the extra context-use battery.
# Writes results/baselines/random_edits/<run>/seed<S>.json and results/context_extra/random_<run>_seed<S>.json.
#   scripts/random_edits.sh <run_dir> ...      e.g. results/runs/e1-opus-100
set -euo pipefail
cd "$(dirname "$0")/.."
TMP=$(mktemp -d)
RUN=(uv run --locked python -m)
for R in "$@"; do
  N=$(basename "$R")
  OUT=results/baselines/random_edits/$N
  mkdir -p "$OUT"
  for S in 0 1 2; do
    "${RUN[@]}" wsr.random_edit models/pair100/sycophant/final "$R/checkpoint" "$S" "$TMP/random"
    "${RUN[@]}" wsr.evaluate "$TMP/random" 100 "$OUT/seed$S.json"
    "${RUN[@]}" wsr.context_extra score "$TMP/random" "random_${N}_seed$S"
    rm -rf "$TMP/random"
  done
done
