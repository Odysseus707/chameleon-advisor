#!/usr/bin/env bash
# Sync benchmark to/from the Chameleon node for run_bench pilots.
#   push: items/prompts/grounding/extractions/harness/snapshots/tools plus
#         capability_table.yaml -> node
#   pull: ONLY the named systems' runs back, defaulting to the advisor-ablation
#         pair (never touches other systems' saved responses)
#           ./node_sync.sh pull                        # s4-fork-on s5-fork-off
#           ./node_sync.sh pull s8-qwen32b-noadv s9-qwen32b-adv
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"            # benchmark/
REPO="$(dirname "$ROOT")"            # chameleon-work/
HOST="${BENCH_NODE:-cc@129.114.108.156}"
KEY="${BENCH_KEY:-$REPO/vivek.pem}"
SSH="ssh -i \"$KEY\" -o StrictHostKeyChecking=accept-new"

case "${1:-}" in
  push)
    ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$HOST" 'mkdir -p benchmark'
    rsync -az \
      --exclude '.venv' --exclude '__pycache__' --exclude '.DS_Store' \
      -e "$SSH" \
      "$ROOT/items" "$ROOT/prompts" "$ROOT/grounding" "$ROOT/extractions" \
      "$ROOT/harness" "$ROOT/snapshots" "$ROOT/tools" \
      "$ROOT/capability_table.yaml" \
      "$HOST:benchmark/"
    echo "pushed -> $HOST:~/benchmark"
    ;;
  pull)
    shift
    SYSTEMS=("$@")
    [ ${#SYSTEMS[@]} -eq 0 ] && SYSTEMS=(s4-fork-on s5-fork-off)
    for c in blind matched heldout uncovered; do
      for s in "${SYSTEMS[@]}"; do
        if ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$HOST" \
            "test -d benchmark/runs/$c/$s"; then
          mkdir -p "$ROOT/runs/$c"
          rsync -az -e "$SSH" "$HOST:benchmark/runs/$c/$s" "$ROOT/runs/$c/"
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
