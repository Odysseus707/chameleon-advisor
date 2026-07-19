#!/usr/bin/env bash
# Sync benchmark_v4 to/from the Chameleon node for run_bench pilots.
#   push: items/prompts/grounding/extractions/harness/snapshots/tools -> node
#   pull: ONLY runs/*/s4-fork-on and runs/*/s5-fork-off back (never touches
#         other systems' saved responses)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"            # benchmark_v4/
REPO="$(dirname "$ROOT")"            # chameleon-work/
HOST="${BENCH_NODE:-cc@129.114.109.224}"
KEY="${BENCH_KEY:-$REPO/vivek.pem}"
SSH="ssh -i \"$KEY\" -o StrictHostKeyChecking=accept-new"

case "${1:-}" in
  push)
    ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$HOST" 'mkdir -p benchmark_v4'
    rsync -az \
      --exclude '.venv' --exclude '__pycache__' --exclude '.DS_Store' \
      -e "$SSH" \
      "$ROOT/items" "$ROOT/prompts" "$ROOT/grounding" "$ROOT/extractions" \
      "$ROOT/harness" "$ROOT/snapshots" "$ROOT/tools" \
      "$HOST:benchmark_v4/"
    echo "pushed -> $HOST:~/benchmark_v4"
    ;;
  pull)
    for c in blind matched heldout uncovered; do
      for s in s4-fork-on s5-fork-off; do
        if ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$HOST" \
            "test -d benchmark_v4/runs/$c/$s"; then
          mkdir -p "$ROOT/runs/$c"
          rsync -az -e "$SSH" "$HOST:benchmark_v4/runs/$c/$s" "$ROOT/runs/$c/"
          echo "pulled runs/$c/$s"
        fi
      done
    done
    ;;
  *)
    echo "usage: $0 push|pull   (env: BENCH_NODE=user@ip BENCH_KEY=/path/key)" >&2
    exit 2
    ;;
esac
