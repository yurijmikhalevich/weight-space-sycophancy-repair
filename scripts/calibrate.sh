#!/usr/bin/env bash
# Score the reference models (base, sycophant, honest twin) on the frozen battery, to calibrate the guard bounds.
# Writes results/calibration/pair<N>_<model>.json, then results/calibration/report.md.
#   scripts/calibrate.sh [pair ...]      (default: 100 101 102)
set -euo pipefail
cd "$(dirname "$0")/.."
PAIRS=${*:-100 101 102}
RUN=(uv run --locked python -m)
OUT=results/calibration
mkdir -p "$OUT"
for P in $PAIRS; do
  M=models/pair$P
  "${RUN[@]}" wsr.evaluate base "$P" "$OUT/pair${P}_base.json"
  for R in sycophant honest; do "${RUN[@]}" wsr.evaluate "$M/$R/final" "$P" "$OUT/pair${P}_$R.json"; done
done
"${RUN[@]}" wsr.calibration
