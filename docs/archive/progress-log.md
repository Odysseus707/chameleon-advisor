# Execution Running Log — Chameleon Assistant + advisor room

Log kept per the goal's "keep a running log" directive. Newest entries on top.
Status legend: ⏸ blocked · ▶ in progress · ✅ gate passed · 🛑 stop-and-ask.

---

## 2026-07-15 — Session start / M0 not yet started

**Overall status:** ⏸ Blocked before M0. Two unmet preconditions, both external:

1. **Kickoff not confirmed.** Goal guardrail #6 gates all code changes on the
   user's explicit go-ahead. Not given yet.
2. **No access to the node.** M0 step 1 ("SSH in") requires floating IP + SSH
   key/credentials for the reserved P100 node. The agent has none. M0–M1
   (bootstrap + Ollama serving) run *on the node* and cannot proceed without it.

**To unblock, the user must provide:**
- Explicit "kickoff / go" for code changes, **and**
- A way to reach the node — floating IP + SSH access — or run M0–M1 commands
  themselves on the node and paste results back (e.g. `nvidia-smi` output).

### Read-only prep completed (no code modified, no node needed)
Seam line numbers re-confirmed accurate from this session's full file reads:
- M2 swap targets: `rag.py:15` (`TEJAS_API_BASE`), `rag.py:16` (`TEJAS_API_KEY`),
  `rag.py:212-217` (`ChatOpenAI(model=...)`).
- M3 injection: `web_rag.py:459-470` (build_context→invoke gap),
  `web_rag.py:256-257` (session-state singleton), `rag.py:194-207` (section idiom).
- M3 advisor JSON: `advisor/reason/llm.py` `TejasClient.complete`.

### First measured evidence needed at M0 gate
- `nvidia-smi` → GPU model + VRAM + **count** (1× vs 2× P100 changes model tier).
- Driver/CUDA present or needs install?

---

## Staged proposal — M2 `rag.py` diff (NOT applied; awaiting kickoff)

Makes the endpoint env-driven while **defaults preserve current upstream
behavior** (so this stays an upstream-contributable patch). Apply only on go.

`rag.py:15-16` — current:
```python
TEJAS_API_BASE = "https://ai.tejas.tacc.utexas.edu/v1"
TEJAS_API_KEY = os.environ.get("TEJAS_API_KEY")
```
proposed:
```python
TEJAS_API_BASE = os.environ.get("LLM_API_BASE", "https://ai.tejas.tacc.utexas.edu/v1")
TEJAS_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("TEJAS_API_KEY")
```

`rag.py:212-217` — current model line:
```python
        model="Meta-Llama-3.3-70B-Instruct",
```
proposed:
```python
        model=os.environ.get("LLM_MODEL", "Meta-Llama-3.3-70B-Instruct"),
```

Runtime env for the P100/Ollama path (set in `.env`, not code):
```
LLM_API_BASE=http://localhost:11434/v1
LLM_API_KEY=not-needed
LLM_MODEL=qwen2.5:14b-instruct-q4_K_M
```
Rationale: `ChatOpenAI` wants a non-empty key; Ollama ignores its value, so a
placeholder via env keeps the code clean (no hardcoded `"not-needed"`).
Tag: **[upstream]** — additive, backward-compatible.

---

## Staged proposal — M3 advisor JSON (NOT applied; awaiting kickoff)

`advisor/reason/llm.py` — add `import os` at top, then in `TejasClient.complete`
force valid JSON + cap tokens (Ollama's OpenAI endpoint supports `response_format`;
the advisor SYSTEM_PROMPT already demands "ONLY a JSON object", so this is safe):
```python
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=int(os.environ.get("ADVISOR_MAX_TOKENS", "700")),
            response_format={"type": "json_object"},
        )
```
Tag: **[upstream to advisor]**. Fallback already covered: `_extract_json` +
heuristic in `reasoner.py` catch any malformed output.

---

## Staged proposal — M3 web_rag.py injection (structural; pending M2 gate)

`web_rag.py` between L459 (`build_context`) and L468 (`chain.invoke`). Requires a
cached `st.session_state.advisor` set up near L256-257 exposing `.router` and an
`advise(question) -> str` helper (router.route → Reasoner.recommend → render).
`os` is already imported (`web_rag.py:2`).
```python
        # --- advisor "room": fire only on edge-resource questions ----------
        if os.environ.get("ADVISOR_ENABLED", "false").lower() in {"1","true","yes","on"}:
            advisor = st.session_state.advisor
            scores = advisor.router.classify(question)
            top = max(scores.values()) if scores else 0.0
            if top >= float(os.environ.get("ADVISOR_GATE", "1.0")):
                try:
                    context += "\n\n=== EDGE RESOURCE ADVISORY ===\n\n" + advisor.advise(question)
                except Exception:
                    pass  # advisor failure must never break the docs answer
        # -------------------------------------------------------------------
```
Tag: **[local-hack]** — couples the two projects, behind `ADVISOR_ENABLED`.
Threshold `ADVISOR_GATE` (default 1.0 ≈ one full multi-word tag hit) tuned in M4.
`assert not isinstance(store.embedder, HashingEmbedder)` at advisor setup enforces
guardrail #3 (bge space).

---

## M4 eval set (node-independent, stable — prepared now)

**Docs questions (advisor must NOT fire — gate false-positive check):**
1. How do I reserve a bare metal node?
2. How do I use object storage on Chameleon?
3. What is a lease and how long can it last?
4. How do I connect to a node via SSH with a floating IP?
5. How do I create a custom disk image?
6. How do I use Jupyter notebooks on Chameleon?
7. What GPU hardware is available?
8. How do I set up a private network between nodes?

**Edge questions (advisor MUST fire — maps to the 4 seeded artifacts):**
1. Capture photos with a Pi camera every 10 minutes at the edge — what to reserve?
   → `edge-picamera-image`
2. Read temperature/humidity from a Sense HAT on an edge device — what do I use?
   → `edge_sensehat_image`
3. Run CPU image-classification inference on an edge device — recommend a setup.
   → `edge-cpu-inference`
4. I need SSH access into a CHI@Edge container — what image and device?
   → `edge_ssh_image`

Expected-answer keys per edge Q: architecture=arm64, machine_type=raspberrypi4-64,
the mapped `image`, and (Q4) `exposed_ports=[22]`.

---

## 2026-07-15 — KICKOFF: node access provided; M0 + M1 executed

Node: `cc@129.114.109.237` (host `integration-testbed`), Ubuntu 22.04.5, x86_64.
SSH fixed: key was 644 → `chmod 600`; stale `known_hosts:23` for the recycled
floating IP removed via `ssh-keygen -R`. Key copied to scratchpad (no-space path).

### ✅ M0 GATE PASSED
- **2× Tesla P100-PCIE-16GB** (32GB total), driver 560.35.05 / CUDA 12.6, healthy.
- 125 GB RAM, 824 GB free disk.
- pip/venv installed; `git`/`curl` present; python 3.10.12 (**deviation:** node has
  3.10 not 3.11 — acceptable, deps support it; using a 3.10 venv).
- All three repos rsync'd to `~/` (excluded `.venv`/`.git`/`__pycache__`).
- 🛑 **2× P100 decision → user chose Qwen2.5-32B** (over the locked 14B default).

### ✅ M1 GATE PASSED (with a critical deviation)
- **DEVIATION (important — belongs in runbook):** Ollama **0.32** bundles a CUDA-13
  runtime requiring driver **≥570**; node has **560**, so it silently ran on **CPU**
  (2.4 tok/s, both GPUs 0 MiB). Fix: **downgrade to Ollama 0.11.11** (CUDA **v12**
  runtime, supports driver 560 / compute 6.0). No reboot, no re-pull.
  → Pin Ollama ≤0.11.x on this node until the driver is upgraded to 570+.
- After fix: 32B loads on **both P100s** (GPU0 10.7GB + GPU1 10.8GB), coherent
  answer, **9.0 tok/s** on-GPU. Fits VRAM with headroom.
- Model: `qwen2.5:32b-instruct-q4_K_M` (19 GB), served at
  `http://localhost:11434/v1` (OpenAI-compatible).

### ▶ M2 IN PROGRESS
- Background install started (pid 7566, `~/m2_setup.log`): 3.10 venv + CPU torch +
  `requirements.txt`.
- Next: apply staged `rag.py` env-diff, `.env` (LLM_API_BASE/KEY/MODEL), build index,
  smoke-test 5 doc questions on the local 32B.

### ✅ M2 GATE PASSED
- Deps installed (3.10 venv + CPU torch + requirements). FAISS index built on node
  (bge download + live scrape of readthedocs/blog/python-chi) → "Index live at
  'vect_store'".
- `rag.py` env-diff applied + rsynced; `.env` points at local Ollama 32B.
- Smoke test: **5 docs questions answered on the local 32B**, all grounded with real
  source URLs, no crashes. Latency ~36–50s/answer steady-state (99s first = cold
  load) at 9 tok/s. Q4 (disk image) correctly hedged "I don't know … from context".
- Minor fix: `m2_smoke.py` must run from the repo dir (`sys.path[0]`), not `~/`.

### ▶ M3 setup started (background)
- Installing advisor (`pip install -e ~/chi-edge-advisor`) into the RAG venv +
  building `artifact_store.json` with bge asserted (guardrail #3).
- Remaining M3 code (verbose): advisor `llm.py` `response_format`; `web_rag.py`
  gate+inject behind `ADVISOR_ENABLED`. **Recommend `/compact` before that** —
  context is high and the M3 wiring/tests are verbose.

### ✅ M3 GATE PASSED
- Advisor wired as an in-process room: `advisor_room.py` (gate+advise), `web_rag.py`
  patched (session-state cache + gate + `=== EDGE RESOURCE ADVISORY ===` inject behind
  `ADVISOR_ENABLED`), advisor `llm.py` given `max_tokens`+`response_format=json`.
- **Gate separation:** general Q=0.25 (dormant) vs edge Q=2.25 (fires), `ADVISOR_GATE=1.0`.
- **Edge advise():** pi-camera Q → `produced_by=tejas` (LLM, 34.7s), grounded in
  `edge-picamera-image`, machine_type raspberrypi4-64/arm64, image + `pi_libcamera`
  profile, coherent reasoning, valid JSON. Heuristic fallback also verified.
- **DEVIATION (in runbook):** stray `~/chi-edge-advisor/.env` overrode provider →
  heuristic-only; removed so RAG `.env` governs (advisor = TejasClient → Ollama).
- Streamlit boots healthy with advisor enabled (`/_stcore/health = ok`, no errors).

### ✅ M4 (representative; full eval deferred for cost)
- Latency measured: docs ~36–50s; edge double-call ~75s (advise ~35s + answer ~40s).
- Graceful failures verified (advisor try/except in web_rag; heuristic fallback).
- Feedback/session logging untouched (no code change there).
- `integration-notes/runbook.md` written (relaunch + the 2 critical gotchas +
  upstream-vs-local-hack table).
- **Not run (cost-critical):** full 8-docs + 4-edge eval sweep — prepared above,
  run for a formal regression check.

### 🎯 DONE criteria — met
✅ local-model docs answers · ✅ edge Qs add artifact-grounded rec · ✅ general Qs
unaffected (gate) · ✅ standalone via `ADVISOR_ENABLED=false` · ✅ `rag.py` diff
upstream-clean. App live on the node at `:8501` (open the security-group port to reach it).

### ✅ M4 GATE PASSED (full eval, not just representative)
- `eval_m4.py`: **docs 8/8** (no false-fire), **edge 4/4** (all `produced_by=tejas`,
  correct artifacts). EVAL_PASS.
- **False-positive found & fixed:** general "SSH to a node w/ floating IP" collided with
  `edge_ssh_image` ssh/floating-ip tags (both 2.25 → threshold alone can't separate).
  Added `advisor_room.should_fire()` = `classify() ≥ gate` AND an **edge cue** present;
  rewired `web_rag.py` gate to it. (Self-caught bug: first web_rag rewire ran `python`
  before venv activation → no-op; reapplied with venv python.)
- **Deployment hardened:** bare `streamlit` over SSH kept dying on session teardown →
  installed a **systemd service `rag-app`** (Restart=always). Verified `HEALTH=ok`,
  `active`, listening on 8501 from a fresh connection. Runbook relaunch updated to systemd.
- Verified files synced back to the local repo (rag.py, web_rag.py, advisor_room.py,
  advisor/reason/llm.py).

### ✅ GOAL COMPLETE — all of M0→M4 passed with observed evidence on hardware.
