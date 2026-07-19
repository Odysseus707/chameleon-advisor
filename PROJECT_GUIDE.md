# Chameleon-Work — Usage Guide

Everything you need to run this project yourself: the Streamlit chatbot (with the
edge advisor on/off), the standalone advisor, and the evaluation benchmark.
All commands below were verified against the code and the live node on 2026-07-18.

---

## 1. What the pieces are

| Directory | What it is |
|---|---|
| `RAG-docs-chameleon/` | The chatbot ("the fork"): FAISS retrieval + reranker + LLM, served by Streamlit (`web_rag.py`). `advisor_room.py` is the bridge that lets it call the advisor. |
| `chi-edge-advisor/` | The edge advisor engine: routes a workload description to grounded artifacts, checks device availability, and emits a CHI@Edge resource recommendation. |
| `benchmark_v4/` | The evaluation benchmark: 50 items, deterministic checkers, a scoring harness, and `tools/run_bench.py` to run models against it automatically. |
| `grounding/` | The advisor's grounding corpus (one folder of `.md` per artifact). |
| `docs/` | All project docs: `usage/` (runbook, testing guide), `architecture/` (integration, harness, router designs), `reference/` (node env + systemd templates), `archive/` (historical plans and logs). |
| `vivek.pem` | SSH key for the Chameleon node. |

**The node** — everything heavy runs on a Chameleon bare-metal node:

- Host: `cc@129.114.109.224` (`integration-testbed`, 2× Tesla P100)
- LLM: Ollama serving `qwen2.5:32b-instruct-q4_K_M` at `localhost:11434` (~9 tok/s — everything is slow, be patient)
- App: systemd service `rag-app` running Streamlit on port **8501**

```bash
# SSH in (from chameleon-work/)
ssh -i vivek.pem cc@129.114.109.224
```

> Chameleon leases expire and the floating IP changes when they do (it already
> changed once, from .237 to .224). If SSH times out, get the new IP from the
> Chameleon dashboard, pass it to the sync script via `BENCH_NODE=cc@<new-ip>`,
> and update `benchmark_v4/tools/bench_config.yaml`.

---

## 2. The Streamlit app (hosting + advisor on/off)

### Open it

The service is already running. Two ways in:

```bash
# From chameleon-work/ (so vivek.pem resolves). Keep this terminal open —
# the tunnel only lives while the SSH session does:
ssh -i vivek.pem -L 8501:localhost:8501 cc@129.114.109.224
# then open  http://localhost:8501   (NOT the node's IP)
```

Notes:
- Direct access (`http://129.114.109.224:8501`) does **not** work — the
  security group blocks port 8501 from outside (verified 2026-07-18); the
  browser shows "took too long to respond". Always use the tunnel.
- If SSH asks "The authenticity of host ... can't be established. Are you sure
  you want to continue connecting?" — that's the normal first-connection
  prompt, not an error. Type `yes` and press Enter.

### Manage the service (on the node)

```bash
sudo systemctl status rag-app        # is it up?
sudo systemctl restart rag-app       # restart (takes ~1 min to reload models)
journalctl -u rag-app -f             # live logs (advisor errors print here)
```

The unit runs `streamlit run web_rag.py --server.port=8501 --server.address=0.0.0.0`
from `/home/cc/RAG-docs-chameleon` using its `.venv`.

### Turn the advisor on/off

The app reads its config from `/home/cc/RAG-docs-chameleon/.env` at startup
(`load_dotenv()` in `web_rag.py`). The two knobs:

```bash
ADVISOR_ENABLED=true    # false to disable the advisor entirely
ADVISOR_GATE=1.0        # minimum tag score for the advisor to fire
```

To toggle: edit `.env` on the node, then `sudo systemctl restart rag-app`.

### How the advisor decides to fire (so you can test it)

The advisor injects an `=== EDGE RESOURCE ADVISORY ===` section into the LLM's
context only when **both** are true (`advisor_room.should_fire`):

1. The question contains an edge cue word (`edge`, `raspberry`, `picamera`,
   `sense hat`, `sensor`, `camera`, `gpio`, `jetson`, `container`, `iot`, …)
2. The advisor's tag-match score ≥ `ADVISOR_GATE` (1.0)

Try it in the UI:

- **Fires:** "How do I take a photo with the pi camera on CHI@Edge every 10 minutes?"
  → the answer includes a concrete resource recommendation (machine type, image,
  device profiles, lease parameters).
- **Doesn't fire:** "How do I reserve a bare metal node?" → plain RAG answer.
  The cue guard exists precisely so generic SSH/networking questions don't
  trigger edge advice.

If the advisor errors, the app degrades gracefully: the error goes to
`journalctl`, and the answer is produced without the advisory.

---

## 3. The advisor standalone (chi-edge-advisor)

You can run the full pipeline (read → retrieve → reason → validate → emit)
locally without the app, one workload per invocation:

```bash
cd chi-edge-advisor

# Fully offline, no credentials, heuristic reasoning:
ADVISOR_OFFLINE=1 AVAILABILITY_BACKEND=reference_api LLM_PROVIDER=none \
  .venv/bin/python -m advisor.cli "take a photo with the pi camera every 10 minutes"
```

It prints each stage (availability, retrieval scores + provenance, the
recommendation, validation) and logs a JSONL trace for grading.

**Nuances (these will bite you if skipped):**

- `AVAILABILITY_BACKEND=reference_api` — the local `.env` selects the Blazar
  backend, which needs python-chi credentials you don't have locally.
- `LLM_PROVIDER=none` — forces the heuristic reasoner. Without it, a running
  local Ollama gets picked up and used for reasoning (fine if that's what you
  want).

### Tests

```bash
cd chi-edge-advisor
LLM_PROVIDER=none .venv/bin/python -m unittest discover -s tests   # 38 tests
```

`LLM_PROVIDER=none` is required: with a live local Ollama, the
"no client → heuristic" test fails because the reasoner silently acquires a
real client.

### Router ablation (tree vs flat retrieval)

```bash
cd chi-edge-advisor
.venv/bin/python tools/ablate_router.py            # optional: --l1-k 2 --l2-k 3
```

Writes Table A7 to `benchmark_v4/exports/ablation_A7.{md,json}` — for each
benchmark item, whether the correct source artifact survives each routing level
(site gate → use-case top-k → artifact selection → chunk retrieval), comparing
the hierarchical `RouterTree` against the flat `RetrievalRouter`.

> **Deployment note:** the node runs the advisor as deployed *before* the
> RouterTree/A5 work (4 artifacts, flat router). The local repo has 5 artifacts
> + the tree. If you want the app to use the new advisor, sync
> `chi-edge-advisor/` and `grounding/` to the node and restart `rag-app` —
> deliberately not done yet so the benchmark measured the deployed stack.

---

## 4. The benchmark (benchmark_v4)

### Anatomy

```
items/<ID>.yaml                 50 items: prompt + deterministic checkers
                                (P=positive, N=negative/edge, AV=availability;
                                graded in groups: mechanism/specifics/safety)
prompts/<condition>/<ID>.txt    generated run prompts
runs/<condition>/<system>/<ID>.md   model answers — THE scorer input layout
harness/runner.py               the scorer (regex + AST checks; V1 items execute
                                generated code against a stubbed python-chi +
                                snapshots/snapshot_synthetic_2026-07-04.json)
notebooks/validate_golds.ipynb  batch scorer (scores every runs/*/*/*.md)
tools/run_bench.py              automated runner (the main tool)
exports/ablation_A7.md          router ablation table
```

**Conditions:** `blind` (bare question), `matched` / `heldout` / `uncovered`
(question + fed reference material).
**Systems:** `s1-chatbot` (production app, manual), `s2-gpt`, `s3-sonnet`
(manual paste), `s4-fork-on` / `s5-fork-off` (the fork via run_bench, advisor
on/off).

### Score a single answer

```bash
cd benchmark_v4
../chi-edge-advisor/.venv/bin/python -m harness.runner \
  --item items/N06.yaml \
  --answer runs/blind/s4-fork-on/N06.md \
  --snapshot snapshots/snapshot_synthetic_2026-07-04.json
```

Prints the verdict and per-group check counts. Any Python 3.10+ with `pyyaml`
works; the advisor venv has it.

### Score everything (batch)

Open `notebooks/validate_golds.ipynb` (VS Code or Jupyter) and run all cells.
The batch cell globs `runs/*/*/*.md`, scores each file against its item, and
prints per-system tallies. It sees `s4-fork-on`/`s5-fork-off` automatically —
no changes needed.

### Run models against the benchmark automatically (run_bench.py)

This is the piece that turns "paste answers by hand" into a scripted run.
The **fork adapter** runs the chatbot's full pipeline in-process (retrieval →
advisor gate/inject → LLM) — it must run **on the node** (that's where the
vector store and Ollama live).

**The full workflow, from your Mac:**

```bash
cd benchmark_v4

# 1. Push the benchmark to the node (items, prompts, harness, tools — never runs/)
tools/node_sync.sh push

# 2. On the node — the 5-item pilot (advisor on AND off + scorer-compat summary, ~13 min):
ssh -i ../vivek.pem cc@129.114.109.224
cd ~/benchmark_v4
~/RAG-docs-chameleon/.venv/bin/python tools/run_bench.py --adapter fork --pilot

# 2b. Or the full 50-item run, one arm at a time (~60–75 min on, ~25 min off):
~/RAG-docs-chameleon/.venv/bin/python tools/run_bench.py --adapter fork --advisor on
~/RAG-docs-chameleon/.venv/bin/python tools/run_bench.py --adapter fork --advisor off
# (long: run inside tmux, or with nohup ... > run.log 2>&1 &)

# 3. Back on your Mac — pull results (ONLY s4-fork-on/s5-fork-off; never other systems)
tools/node_sync.sh pull

# 4. Score: notebook, or per-item harness.runner as above
```

Useful flags: `--items P01,N06` (subset), `--dry-run` (print targets, no
writes/network), `--system` (override the target dir), `--config` (alternate
YAML). Config (model names, env, pilot items, node host) lives in
`tools/bench_config.yaml`.

**What a run produces**, per `runs/<condition>/<system>/`:

- `<ID>.md` — the raw model answer, verbatim (fences and prose untouched)
- `<ID>.telemetry.json` — gate score, fired?, the advisory text, `grounded_by`
  / `produced_by`, retrieval sources, timings
- `manifest.json` — model + params, timestamps, host, fork git state, content
  hashes of the item bank / grounding / snapshot

**Invariants baked into the tool:** existing non-empty `.md` files are never
overwritten (it skips and warns); sidecars are invisible to the scorer's glob;
scorer code is never touched.

### API adapters (GPT / Claude) — currently zero-spend

`--adapter anthropic` and `--adapter openai` are implemented but **disabled by
policy**: no API keys are configured and the tool refuses to run them without
one. Only `--dry-run` works:

```bash
python3 tools/run_bench.py --adapter anthropic --dry-run --conditions blind
```

To do a real (paid) run later: set the exact model strings in
`bench_config.yaml`, export `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, and drop
`--dry-run`. One item per request, retries with backoff, same output layout.

### Regenerate prompts (only after editing items/ or grounding/)

```bash
cd benchmark_v4 && python3 tools/make_run_prompts.py
```

---

## 5. Gotchas, collected

- **Slow node**: qwen2.5-32B on P100s does ~9 tok/s. Advisor-on answers take
  50–90 s each (retrieval + advisory + generation); advisor-off 7–45 s. Use
  tmux for full runs.
- **Advisor-on ≈ 2× latency** in the app too — that's the advisory generation,
  not a bug.
- **`node_sync.sh` and rsync**: macOS ships openrsync, which chokes on some GNU
  flags (`--delete-excluded` was already removed from the script). If rsync
  errors with "buffer overflow: recv_rules", an incompatible flag came back.
- **Node IP changes** on lease renewal — override with
  `BENCH_NODE=cc@<ip> tools/node_sync.sh push` and update `bench_config.yaml`.
- **Advisor tests** need `LLM_PROVIDER=none`; the **advisor CLI** offline needs
  `ADVISOR_OFFLINE=1 AVAILABILITY_BACKEND=reference_api`.
- **Never hand-edit files under `runs/`** that contain answers — they are the
  measurement record. Empty placeholder files may be filled; run_bench refuses
  to overwrite non-empty ones.
- **Pilot findings worth knowing** (from `runs/blind/*/`): the advisory *hurt*
  item N06 (specifics 2/5 with advisor vs 5/5 without) — watch whether that
  holds over the full 50; two items (AV01, N01) answered with no code fences at
  all, which the checkers score as FAIL on code-dependent checks.

## 6. Where to read more

- `docs/architecture/harness-plan.md` — the benchmark harness design + scorer contract
- `docs/architecture/router-refactor-plan.md` — RouterTree design + ablation results
- `benchmark_v4/BENCHMARK_REPORT.md` — the benchmark's own report
- `benchmark_v4/exports/ablation_A7.md` — tree-vs-flat routing table
- `docs/archive/chi-edge-advisor_prototype-state.md` — advisor prototype state of the world (historical snapshot, 2026-07-01)
