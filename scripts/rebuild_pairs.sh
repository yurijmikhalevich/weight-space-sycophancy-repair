#!/usr/bin/env bash
# Rebuild honest/sycophant pairs from the released recipe in a fresh temp dir, evaluate them and the base model with the
# Sparks eval, then check acceptance. Models go to models/ (not committed); evals, loss curves, hashes and the
# environment go to results/pairs/.
#   scripts/rebuild_pairs.sh [pair ...]      (default: 100 101 102)
set -euo pipefail
cd "$(dirname "$0")/.."
PAIRS=${*:-100 101 102}
TMP=$(mktemp -d)
RUN=(uv run --locked python -m)
for P in $PAIRS; do
  SPLIT=data/exp7/splits/pair$P.json
  for R in honest sycophant; do
    "${RUN[@]}" wsr.train "$P" "$R" "$SPLIT" "$TMP/pair$P/$R"
    "${RUN[@]}" wsr.exp7_eval "$TMP/pair$P/$R/final" "$P" "$TMP/pair${P}_$R.json"
  done
  "${RUN[@]}" wsr.exp7_eval base "$P" "$TMP/pair${P}_base.json"
done
mkdir -p models results/pairs
for P in $PAIRS; do
  rm -rf "models/pair$P" && mv "$TMP/pair$P" "models/pair$P"
  cp "$TMP"/pair"${P}"_*.json results/pairs/
  for R in honest sycophant; do cp "models/pair$P/$R/log.jsonl" "results/pairs/pair${P}_$R.train.jsonl"; done
done
shasum -a 256 models/pair*/*/final/model.safetensors > results/pairs/models.sha256
{ sysctl -n machdep.cpu.brand_string 2>/dev/null || nvidia-smi -L; sw_vers 2>/dev/null || uname -a
  uv run --locked python -c "import platform, torch, transformers; from wsr.base import DEVICE, BASE
print(platform.python_version(), 'torch', torch.__version__, 'transformers', transformers.__version__, DEVICE, BASE)"
} > results/pairs/env.txt
"${RUN[@]}" wsr.check_pairs
