# Runbook — Self-hosted Chameleon Docs Assistant + advisor room

How to (re)launch the stack on a Chameleon P100 node, plus the non-obvious
gotchas that cost real time the first go. Built and verified 2026-07-15.

## Node
- `ssh -i <key.pem> cc@<floating-ip>` (verified node: `129.114.109.237`, host
  `integration-testbed`, Ubuntu 22.04, 2× Tesla P100-PCIE-16GB).
- Key perms must be `600`. Chameleon **recycles floating IPs** across leases, so a
  new lease on a reused IP triggers "REMOTE HOST IDENTIFICATION HAS CHANGED" —
  clear it with `ssh-keygen -R <ip>` (this is expected, not an attack).

## ⚠️ Critical gotchas (both cost hours if forgotten)
1. **Pin Ollama to ≤ 0.11.x on this node.** Ollama **0.32** bundles a CUDA-13
   runtime needing NVIDIA driver **≥570**; the node has **560**, so it silently
   runs the model on **CPU** (~2.4 tok/s, GPUs idle). Ollama **0.11.11** ships a
   CUDA **v12** runtime that uses the P100s (~9 tok/s). Install pinned:
   `curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION=0.11.11 sh`.
   (The permanent alternative is upgrading the driver to 570+, which needs a reboot.)
2. **No stray `chi-edge-advisor/.env` on the node.** The advisor's config loads its
   own package `.env` first; if present it overrode the provider/model and forced a
   heuristic-only fallback. The **RAG `.env` is the single source of truth** — the
   advisor picks up `LLM_PROVIDER`/`TEJAS_*` from it. Keep `~/chi-edge-advisor/.env`
   deleted. (When rsyncing the repo up, exclude `.env`.)
3. **Set `FEEDBACK_DB_PATH` + `SESSION_LOG_PATH` to the repo dir when running
   natively.** `feedback_store.py:9` defaults `FEEDBACK_DB_PATH` to `/app/feedback.db`
   (a Docker-baked path). Running under systemd as `cc`, that dir doesn't exist and
   isn't writable → the app crashes on page load with
   `PermissionError: [Errno 13] Permission denied: '/app'`. Fix (already in `.env`):
   `FEEDBACK_DB_PATH=/home/cc/RAG-docs-chameleon/feedback.db` (and
   `SESSION_LOG_PATH=…/session_log.jsonl`). `rag.py`'s `load_dotenv()` runs before
   `feedback_store` is imported, so `.env` is picked up.

## Config — `~/RAG-docs-chameleon/.env`
```
# chatbot LLM (rag.py, env-driven)
LLM_API_BASE=http://localhost:11434/v1
LLM_API_KEY=not-needed
LLM_MODEL=qwen2.5:32b-instruct-q4_K_M
# advisor room → same Ollama, via OpenAI-compatible TejasClient
LLM_PROVIDER=tejas
TEJAS_BASE_URL=http://localhost:11434/v1
TEJAS_MODEL=qwen2.5:32b-instruct-q4_K_M
TEJAS_API_KEY=not-needed
GROUNDING_DIR=/home/cc/grounding
ADVISOR_OFFLINE=false
ADVISOR_ENABLED=true      # set false → chatbot runs standalone, advisor dormant
ADVISOR_GATE=1.0          # router.classify() top-score threshold to fire the room
```

## Relaunch (after a fresh lease or reboot)
The app runs as a **systemd service `rag-app`** (persistent + auto-restart). A bare
`streamlit run …` launched over SSH dies on session teardown — use the service.
```
# 1. model: systemd auto-starts 'ollama'; ensure the model is present
ollama list | grep qwen2.5:32b   # else: ollama pull qwen2.5:32b-instruct-q4_K_M
# 2. one-time: build the index if missing (~10 min)
cd ~/RAG-docs-chameleon && . .venv/bin/activate && ([ -f vect_store/index.faiss ] || python build_index.py)
# 3. app service (unit at /etc/systemd/system/rag-app.service)
sudo systemctl restart rag-app        # status: systemctl status rag-app; logs: journalctl -u rag-app
```
Reach it at `http://<floating-ip>:8501` — **open port 8501 in the lease's security
group** (or front it with the repo's traefik `docker-compose.yml` for TLS).
Rebuild the advisor artifact store only if `grounding/` changes:
`python -c "from advisor.artifacts.store import ArtifactStore; ArtifactStore().build().save()"`.

## Measured behaviour
- Docs answer: ~36–50s (cold first load ~99s) at ~9 tok/s.
- Edge turn is a **double call**: advisor rec ~35s + chatbot answer ~40s ≈ ~75s.
  Tune down with a smaller advisor model or `max_tokens` if needed.
- Gate: general docs Q scores ~0.25 (dormant); edge Q ~2.25 (fires). `ADVISOR_GATE=1.0`.
- Failures are graceful: advisor exception is caught in `web_rag.py` (docs answer
  still returns); if the LLM/JSON fails, the advisor's heuristic yields a valid rec.

## Changed files — upstream vs local-hack
| File | Change | Nature |
|---|---|---|
| `RAG-docs-chameleon/rag.py` | endpoint/model env-driven (`LLM_API_BASE/KEY/MODEL`), defaults preserve upstream | **[upstream]** |
| `chi-edge-advisor/advisor/reason/llm.py` | `TejasClient` adds `max_tokens` + `response_format=json` | **[upstream to advisor]** |
| `RAG-docs-chameleon/advisor_room.py` | new — in-process gate+advise wrapper | **[local-hack]** |
| `RAG-docs-chameleon/web_rag.py` | cache room in session_state; gate+inject `=== EDGE RESOURCE ADVISORY ===` behind `ADVISOR_ENABLED` | **[local-hack]** |

## Eval (M4) — PASSED
`eval_m4.py` (on node) ran the full set: **docs 8/8** (none falsely fire the room) and
**edge 4/4** (all LLM-generated, grounded in the correct artifact). One false-positive was
surfaced and fixed: a general *"SSH to a node with a floating IP"* question collided with
the `edge_ssh_image` ssh/floating-ip tags (both scored 2.25, so a threshold couldn't
separate them). Fix: an **edge-cue guard** — `advisor_room.should_fire()` requires
`router.classify() ≥ gate` **and** an edge cue (edge/chi@edge/container/camera/sensor/…)
in the question; `web_rag.py`'s gate calls `should_fire`.
