#!/usr/bin/env bash
# Run one Claude editing session (Opus 5.5 unless MODEL is set) from a clean tree. The API key comes from
# .env.anthropic.local (git-ignored, ANTHROPIC_API_KEY=...), so it reaches only this run, not the shell that starts it.
# On macOS, caffeinate keeps the machine awake.
#   [MODEL=claude-fable-5-2] scripts/agent.sh <e1|e2> <pair> <new out_dir>
set -euo pipefail
cd "$(dirname "$0")/.."
[ -z "$(git status --porcelain)" ] || {
  echo "commit or stash changes first: runs start from a clean tree, so run.json's commit describes the code" >&2
  exit 1
}
set -a; source .env.anthropic.local; set +a
AWAKE=$(command -v caffeinate >/dev/null && echo "caffeinate -i" || true)
exec $AWAKE uv run --locked python -m wsr.agent "$1" "${MODEL:-claude-opus-5-5}" "$2" "$3"
