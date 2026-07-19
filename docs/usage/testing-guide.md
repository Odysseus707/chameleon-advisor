# Testing Guide — Self-hosted Chameleon Docs Assistant + advisor room

How to exercise the running system and how to read the results. Written
2026-07-15 against the live node (`129.114.109.237`, 2× Tesla P100).

Node key: `vivek.pem` (chmod 600). SSH:
`ssh -i vivek.pem cc@129.114.109.237` (accept the new host key if the IP was
recycled onto a fresh lease: `ssh-keygen -R 129.114.109.237` first).

---

## 0. Is it even up? (30-second health check)

From your laptop, over SSH:
```
ssh -i vivek.pem cc@129.114.109.237 '
  systemctl is-active rag-app ollama
  curl -s -o /dev/null -w "app health HTTP %{http_code}\n" http://localhost:8501/_stcore/health
  ollama list | grep qwen2.5:32b
'
```
Expect: `active` / `active`, `HTTP 200`, and the 32B model listed.

---

## 1. Reach the UI (needs a one-time firewall change)

The app listens on `0.0.0.0:8501` but **port 8501 is currently CLOSED in the
Chameleon security group** — confirmed unreachable from outside. Two ways to test:

**Option A — SSH tunnel (works right now, nothing to change):**
```
ssh -i vivek.pem -L 8501:localhost:8501 cc@129.114.109.237
# leave that open, then browse on your laptop to:
#   http://localhost:8501
```

**Option B — open the port (public URL, requires Chameleon dashboard action):**
In the Horizon dashboard → the lease's security group → add an ingress rule for
TCP **8501** (source `0.0.0.0/0`, or better, your IP/32). Then browse to
`http://129.114.109.237:8501`. NOTE: the floating IP changes on a new lease.

Recommend Option A for now — it's the least surface area and needs no changes.

---

## 2. Functional tests in the UI

Type these into the chat box. There are two behaviors to verify: (a) plain docs
answering on the local model, and (b) the advisor "room" firing ONLY on edge
questions.

### 2a. General docs questions — advisor must stay DORMANT
- "How do I reserve a bare metal node?"
- "How do I use object storage on Chameleon?"
- "What is a lease and how long can it last?"
- "How do I create a custom disk image?"

Expect: a grounded answer with a **Sources** list. There must be **NO**
`=== EDGE RESOURCE ADVISORY ===` section and no device/lease recommendation.
This proves the gate isn't firing on general traffic.

### 2b. Edge resource questions — advisor must FIRE
- "I want to capture photos with a Pi camera every 10 minutes at the edge — what
  should I reserve?"
- "Read temperature and humidity from a Sense HAT on an edge device."
- "Run CPU image-classification inference on an edge device."
- "I need SSH access into a CHI@Edge container."

Expect: the normal docs answer **plus** a concrete recommendation that names a
specific CHI@Edge device (e.g. a Raspberry Pi / Jetson class device) and a lease
suggestion, grounded in a real `artifact_id`. The answer should read as one
coherent reply — the advisory is injected as context, not bolted on visibly.

### 2c. The standalone-mode test (proves the room is optional)
The chatbot must still work with the advisor turned off. On the node edit
`~/RAG-docs-chameleon/.env`, set `ADVISOR_ENABLED=false`, then
`sudo systemctl restart rag-app`. Ask an edge question again → you should get a
plain docs answer with **no** advisory section, and no crash. Set it back to
`true` and restart when done.

---

## 3. The automated eval (fastest regression check)

`eval_m4.py` runs the gate + advisor over 8 docs + 4 edge questions without the
UI. Run it on the node inside the venv:
```
ssh -i vivek.pem cc@129.114.109.237
cd ~/RAG-docs-chameleon && . .venv/bin/activate
python eval_m4.py
```
Expect the last line: `SUMMARY docs=8/8 edge=4/4 -> EVAL_PASS`.
- `docs=8/8` → none of the general questions falsely fired the room.
- `edge=4/4` → every edge question fired AND grounded in the *expected*
  artifact (`edge-picamera-image`, `edge_sensehat_image`, `edge-cpu-inference`,
  `edge_ssh_image`).
Each edge line also prints `by=tejas` (LLM-generated) or `by=heuristic`
(fallback) — see nuance #4 below.

---

## 4. Result nuances — what to expect and why (read this before judging output)

1. **Cold-start lag on the first question (~90–100s).** Ollama unloads the 19GB
   model from VRAM after ~5 min idle (right now both P100s show 0% / 3 MiB — the
   model is NOT resident). The first prompt reloads it across both cards before
   generating. Subsequent questions are ~36–50s. Don't mistake the cold reload
   for a hang. To pre-warm: `ssh … 'ollama run qwen2.5:32b-instruct-q4_K_M "hi"'`.

2. **Edge turns are ~2× slower than docs turns (~75s vs ~40s).** An edge question
   makes TWO LLM calls: the advisor generates its recommendation JSON, THEN the
   chatbot writes the final answer with that advisory in context. This is by
   design; general questions make one call. If it feels slow, that's the
   double-call, not a fault.

3. **Throughput is ~9 tok/s — this is the P100 ceiling, not a bug.** Pascal has
   no tensor cores; a 32B Q4 model on it is inherently slow-ish. It's fine for a
   single-user demo, not for concurrency. (And critically: if you ever see
   ~2.4 tok/s, Ollama silently fell back to CPU — that means the Ollama version
   drifted above 0.11.x and needs the CUDA-v12 build re-pinned; see runbook
   gotcha #1.)

4. **`produced_by=tejas` vs `heuristic`.** "tejas" here is just the OpenAI-compat
   client name — it's pointed at *local Ollama*, not TACC. `by=tejas` means the
   advisor's LLM reasoning path worked. `by=heuristic` means the LLM/JSON call
   failed and the advisor fell back to rule-based selection — still a valid rec,
   but a signal something's off (usually a stray `chi-edge-advisor/.env` — runbook
   gotcha #2). In a healthy run all 4 edge lines say `by=tejas`.

5. **The gate is deliberately conservative (needs an edge *cue* word).**
   `should_fire()` requires BOTH a router score ≥ 1.0 AND a literal edge cue
   (edge / chi@edge / container / camera / sensor / pi / jetson / gpio / …). This
   was added because a general "SSH to a node with a floating IP" question scored
   identically (2.25) to the real edge-SSH artifact and the score alone couldn't
   separate them. Consequence: an edge question phrased WITHOUT any cue word may
   not fire. That's an intentional precision-over-recall trade for the demo — if
   you want it to fire on a borderline phrasing, include an edge cue word.

6. **Answers are grounded-only by design.** The system prompt forbids using
   outside knowledge; if the retrieved docs don't cover something it will say
   "I don't know." That's correct behavior, not a model weakness — it's the
   anti-hallucination guardrail.

7. **Quality ceiling.** This is a 32B Q4 local model standing in for Llama-3.3-70B.
   Answers are solid and grounded but occasionally terser or less polished than the
   production 70B would be. Judge it on *correctness + grounding*, not prose flair.

---

## 5. Failure-mode spot checks (optional, proves graceful degradation)

- **Ollama down:** `sudo systemctl stop ollama`, ask a question → the app should
  surface an error for that turn but not crash the process; restart ollama to
  recover.
- **Advisor exception:** the inject is wrapped in try/except in `web_rag.py`, so
  even if the room throws, the plain docs answer still returns (the advisory is
  just omitted). You'll see the exception in `journalctl -u rag-app`.

Logs: `ssh … 'journalctl -u rag-app -n 100 --no-pager'`.
