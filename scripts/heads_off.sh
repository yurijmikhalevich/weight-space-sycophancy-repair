#!/usr/bin/env bash
# The heads-off baseline: head ablations run through the agent's sandbox (wsr/heads_off.py), then scored on the battery.
# Writes results/baselines/heads_off/<variant>/pair<N>/ (edit, tool calls, eval.json); checkpoints are not committed.
#   scripts/heads_off.sh [pair ...]      (default: 100 101 102)
set -euo pipefail
cd "$(dirname "$0")/.."
RUN=(uv run --locked python -m)
for P in ${*:-100 101 102}; do
  for V in head_10_2 top_heads; do
    OUT=results/baselines/heads_off/$V/pair$P
    rm -rf "$OUT"
    "${RUN[@]}" wsr.heads_off "$V" "$P" "$OUT"
    "${RUN[@]}" wsr.evaluate "$OUT/checkpoint" "$P" "$OUT/eval.json"
  done
done
