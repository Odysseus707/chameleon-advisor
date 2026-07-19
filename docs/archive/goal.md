# GOAL — Self-hosted Chameleon Docs Assistant with the chi-edge-advisor "room"

> **This is an execution plan meant to be handed to an autonomous coding loop.**
> It is self-contained: an agent starting cold should be able to read only this
> file (plus `integration-notes/seam-map.md` for line-level detail) and execute.
> Work milestone by milestone. **Each milestone has a hard acceptance gate — do
> not advance past a failing gate.** Stop and report at any 🛑 STOP-AND-ASK point.

---

## Mission (one sentence)

Stand up the RAG-docs-chameleon chatbot on a freshly-reserved (currently empty)
Chameleon **P100** node, serving a **local** OpenAI-compatible LLM in place of the
inaccessible Tejas Llama-3.3-70B, then embed **chi-edge-advisor** as an in-process
"room" that fires only on edge-resource questions.

## Mental model

The chatbot is the **house**; the advisor is a **room** inside it. The room is a
Python library imported into the chatbot process (NOT a separate service, NOT
MCP). It lights up only when the user asks an edge resource-selection question.

---

## Locked decisions (do not re-litigate)

| Decision | Value | Rationale |
|---|---|---|
| No Tejas access | Self-host a local OpenAI-compatible LLM | No `TEJAS_API_KEY` |
| GPU | **NVIDIA P100 (Pascal, sm_60, ~16GB), just reserved, empty** | What the user has |
| Serving stack | **Ollama (llama.cpp / GGUF)** | Pascal lacks tensor cores + AWQ/Marlin/FlashAttn kernels; vLLM+AWQ is a dead end here |
| Chat model | **Qwen2.5-14B-Instruct, Q4_K_M** (~9GB) | Fits 16GB w/ KV headroom; strong at JSON |
| Embeddings + reranker | **Stay on CPU** (`rag.py:23`, bge-large + bge-reranker-base) | Reserve VRAM for the LLM |
| Advisor reasoning | **Via the same local LLM** (user chose best quality) | +1 call on edge turns — mitigated below |
| Advisor JSON | Force `response_format={"type":"json_object"}` (Ollama supports it) + cap `max_tokens` | Reliable JSON from a 14B on a slow card |
| Availability backend | `reference_api` (`api.chameleoncloud.org`, no auth) | Blazar needs CHI creds; skip for now |
| Integration seam | In-process import + inject at `web_rag.py:459–468` as a labelled context section | Dissolves the MCP + tool-calling blockers |
| Gate | Reuse `advisor/artifacts/router.py:classify()` with a real threshold | No new classifier, no wasted LLM call on general questions |

**Runtime unknowns to resolve while executing (don't guess — measure):**
- Exact P100 count on the node (`nvidia-smi`). **If 2× P100** → may upgrade chat
  model to Qwen2.5-**32B** Q4 (~20GB split across cards). 🛑 STOP-AND-ASK before
  changing model tier.
- Whether the node image already has NVIDIA driver + CUDA, or needs install.
- Whether Qwen2.5-14B answer quality is acceptable on real doc questions (M2 gate).

---

## Guardrails (apply to every milestone)

1. **Minimal, flagged diffs.** Keep the `rag.py` endpoint change tiny and
   env-driven — it must stay a clean **upstream-contributable** patch. Tag every
   file you touch as `[upstream]` or `[local-hack]` per the table in
   `seam-map.md §7`.
2. **Don't break standalone mode.** The chatbot must still run without the advisor
   (advisor behind an env flag, e.g. `ADVISOR_ENABLED`).
3. **Enforce the advisor's bge path.** Assert the advisor is NOT on its
   `HashingEmbedder` fallback (`advisor/artifacts/embeddings.py:85-92`); its
   vectors must be in the same bge cosine space as the chatbot's. Fail loudly
   otherwise.
4. **No secrets in code.** Endpoint/model/keys come from env (`.env`, not committed).
5. **Verify before claiming done.** Every gate is a real observed result (a curl
   response, an actual answer, a measured latency) — not "should work."
6. **Read-only until go.** Do not modify code until the user confirms kickoff;
   M0–M1 are provisioning and can proceed once greenlit.

---

## Milestones

### M0 — Bootstrap the empty node → working GPU host
**Goal:** turn the bare reserved node into an SSH-able host with a usable P100 and
both repos present.

Steps:
1. Confirm access: floating IP + SSH in.
2. `nvidia-smi` → record **GPU model, VRAM, and count**. (Confirms Pascal/P100.)
3. If `nvidia-smi` fails or driver/CUDA missing: install the NVIDIA driver + CUDA
   runtime appropriate for Pascal, reboot if needed, re-verify.
4. Install baseline: `git`, `python3.11`+venv (or Docker if using the existing
   `docker-compose.yml`), `curl`.
5. Clone/copy the working tree onto the node: `RAG-docs-chameleon/`,
   `chi-edge-advisor/`, and **`grounding/`** (the advisor needs the grounding dir).

**Acceptance gate:** `nvidia-smi` shows the P100(s) with driver+CUDA healthy; all
three project dirs present on the node. Record GPU count. 🛑 If 2× P100, flag the
32B option.

---

### M1 — Local LLM serving (Ollama + Qwen2.5-14B)
**Goal:** an OpenAI-compatible chat endpoint backed by the P100.

Steps:
1. Install Ollama; start `ollama serve`.
2. `ollama pull qwen2.5:14b-instruct-q4_K_M`.
3. Smoke-test the OpenAI-compat endpoint:
   `curl http://localhost:11434/v1/chat/completions` with a trivial prompt.
4. Confirm it's on GPU (`nvidia-smi` shows VRAM use) and measure rough tokens/sec.

**Acceptance gate:** curl returns a coherent completion; model runs on the P100
(not CPU-fallback); VRAM fits with headroom; latency recorded. 🛑 If it won't fit
or is unusably slow, STOP-AND-ASK (drop to Qwen2.5-7B, or reconsider).

---

### M2 — Model swap in the chatbot (advisor NOT yet wired)
**Goal:** the chatbot answers real doc questions using the local model. This
proves the swap independently of the integration.

Steps (files from `seam-map.md §1`):
1. Parameterize `rag.py` — make these env-driven (default to current values so
   upstream behavior is preserved):
   - `rag.py:15` base URL → `os.environ.get("LLM_API_BASE", ...)`
   - `rag.py:16` key → `LLM_API_KEY` (pass `"not-needed"` for Ollama)
   - `rag.py:213` model → `os.environ.get("LLM_MODEL", ...)`
2. `pip install -r RAG-docs-chameleon/requirements.txt`.
3. Build the index: `python build_index.py` (needs outbound net; downloads
   bge-large ~1.3GB and live-scrapes readthedocs + blog — expect a slow first run).
4. Set env `LLM_API_BASE=http://localhost:11434/v1`,
   `LLM_MODEL=qwen2.5:14b-instruct-q4_K_M`; run `streamlit run web_rag.py`.
5. Ask 5 representative doc questions (use the `EXAMPLES` in `web_rag.py:279-286`).

**Acceptance gate:** chatbot returns grounded, non-degenerate answers via the local
model; sources render; no crashes. 🛑 **Quality judgment call:** if 14B answers are
too weak, STOP-AND-ASK (bump model / try 32B if 2× P100 / adjust retrieval).

---

### M3 — Wire the advisor in as the "room"
**Goal:** edge-resource questions trigger the advisor; general questions don't.

Steps (seams from `seam-map.md §1, §3, §7`):
1. Install the advisor into the same env; point it at `grounding/`
   (`GROUNDING_DIR`); build its artifact store (`ArtifactStore.build()`).
   **Assert bge path** (guardrail #3).
2. Configure the advisor to use the **same local endpoint**: set `LLM_PROVIDER`,
   `TEJAS_BASE_URL`/`TEJAS_MODEL` (or the Ollama provider) to the Ollama server
   (`advisor/config.py`, `advisor/reason/llm.py`).
3. Add `response_format={"type":"json_object"}` + a `max_tokens` cap to the
   advisor's client call (`advisor/reason/llm.py` `TejasClient.complete`).
4. In `web_rag.py`, between line 459 (`build_context`) and 468 (`chain.invoke`):
   - Cache an advisor handle in `st.session_state` once (next to the chain,
     `web_rag.py:256-257`).
   - **Gate:** run `router.classify(question)`; if top score clears a real
     threshold, run the advisor pipeline; else skip.
   - **Inject** the advisor's rendered recommendation as a new
     `=== EDGE RESOURCE ADVISORY ===` section appended to `context` (mirror the
     PRIMARY/SUPPLEMENTARY idiom, `rag.py:194-207`); optionally add one line to the
     system prompt (`rag.py:220-232`) describing it.
   - Put all of this behind `ADVISOR_ENABLED` (guardrail #2).
5. Use the `reference_api` availability backend (no auth).

**Acceptance gate:**
- An edge question ("I want to capture photos on a Pi camera at the edge — what
  should I reserve?") → advisor fires, a concrete device + lease rec is injected,
  grounded by real `artifact_id`s.
- A general docs question ("How do I use object storage?") → advisor does **not**
  fire (gate works); answer unchanged from M2.
- Advisor JSON parses every time (format constraint working); on any advisor
  failure, the heuristic fallback still yields a valid rec and the turn doesn't
  crash.

---

### M4 — Harden, tune, and evaluate
**Goal:** acceptable latency and no regressions; a demo-ready, explainable system.

Steps:
1. Measure double-call latency on edge turns; tune the gate threshold, advisor
   `max_tokens`, and output verbosity.
2. Confirm feedback logging (`feedback_store.py`) and session log still work.
3. Build a tiny eval set: ~8 doc questions + ~4 edge questions. Check: docs answers
   didn't regress vs M2, advisor picks correct architecture/device, gate has no
   false positives/negatives.
4. Verify failure modes are graceful (Ollama down, advisor exception, empty
   availability).
5. Write a short `integration-notes/runbook.md` (how to relaunch after a new lease)
   and a clean summary of the `[upstream]` vs `[local-hack]` diff.

**Acceptance gate:** eval passes; latency acceptable for single-user demo; failure
paths degrade gracefully; runbook exists.

---

## Definition of done

A person visits the Streamlit app on the Chameleon P100 node and:
- gets good grounded answers to general Chameleon docs questions (local 14B, no
  Tejas), and
- when they ask an edge resource-selection question, the answer includes a
  concrete, artifact-grounded CHI@Edge device + lease recommendation from the
  advisor room — while general questions are unaffected;
- the chatbot still runs with `ADVISOR_ENABLED=false`;
- the `rag.py` endpoint change is a clean, upstream-contributable diff.

## How to run this autonomously
- Execute M0→M4 in order. Treat each **acceptance gate** as a real, observed check.
- At every 🛑 STOP-AND-ASK, pause and surface the decision with the measured
  evidence.
- Keep a running log of what was done, what was observed at each gate, and any
  deviations from this plan. Update this file if reality forces a change (and note
  why).
