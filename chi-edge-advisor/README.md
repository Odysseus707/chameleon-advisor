# chi-edge-advisor

An **allocation-aware resource advisor** for Chameleon Cloud's **CHI@Edge**
testbed. You describe a workload in plain language; it reads live device
availability, retrieves the relevant Trovi artifacts, and recommends a concrete
device plus a **runnable `python-chi` lease spec** — after checking the
recommendation against known CHI@Edge traps.

> OSRE 2026 fellowship prototype. It is intentionally structured to become an
> **MCP server** plugged into [`ChameleonCloud/RAG-docs-chameleon`](https://github.com/ChameleonCloud/RAG-docs-chameleon),
> so it mirrors that stack where practical: FAISS, `BAAI/bge-large-en-v1.5`
> embeddings, and an OpenAI-compatible client pointed at the Tejas AI endpoint
> serving `Meta-Llama-3.3-70B-Instruct`.

---

## TL;DR — explain it in 60 seconds

> "You type *'take a photo with the Pi camera'*. The advisor (1) **reads** which
> CHI@Edge devices are free right now, (2) **retrieves** the matching Trovi
> tutorial (here, the Pi-camera artifact) from a FAISS vector store, (3)
> **reasons** with a Llama-3.3-70B model to pick a device + image + settings,
> (4) **validates** the pick against CHI@Edge gotchas (arch mismatch, device not
> actually free, missing `platform_version`, GPU without `runtime=nvidia`…), and
> (5) **emits** copy-pasteable `python-chi` code that creates the lease and
> container. Every step is logged to JSONL so runs can be graded later."

The one non-obvious thing it proves up front (see below): **the reference API
does *not* know what's reserved** — live state has to come from Blazar.

---

## Key finding: the availability probe

The **first deliverable** is [`probe_availability.py`](probe_availability.py),
which empirically answers: *does the Chameleon reference API reflect live
reservation state, or only static inventory?*

```bash
python probe_availability.py
```

**Verdict: `STATIC-ONLY`.** Measured against the live API:

| Check | Result |
| --- | --- |
| Reference API reachable / `edge` site exists | yes / yes |
| CHI@Edge clusters exposed in reference API | **0** |
| CHI@Edge devices exposed | **0** |
| Reservation-like fields in a node's schema | **none** |
| Candidate live-status endpoints probed | all **404** |

So the reference API is not just missing live state — it exposes **no CHI@Edge
inventory at all** (only baremetal sites are catalogued there). **Consequence:**
live availability *and* the edge hardware catalog must come from **Blazar via
`python-chi`**. The `ReferenceApiBackend` remains useful only as a static
identity source; set `AVAILABILITY_BACKEND=blazar` for real live state.

The whole system is built so this backend is a config switch — nothing downstream
cares which backend supplies live state.

---

## Architecture

```
workload string
     │
     ▼
┌──────────┐  ┌───────────┐  ┌──────────┐  ┌───────────┐  ┌────────┐
│  READ    │→ │ RETRIEVE  │→ │  REASON  │→ │ VALIDATE  │→ │  EMIT  │
│ avail +  │  │ artifacts │  │  LLM rec │  │ trap chk  │  │ py-chi │
│ inventory│  │  (FAISS)  │  │          │  │           │  │  spec  │
└──────────┘  └───────────┘  └──────────┘  └───────────┘  └────────┘
     └──────────────── structured JSONL logging (every stage) ───────┘
```

Module map (cleanly separated, each independently testable):

| Module | Responsibility |
| --- | --- |
| `advisor/availability/` | `DeviceAvailability` dataclass + `AvailabilityBackend` interface. Two backends: `ReferenceApiBackend` (static catalog + live-status probe) and `BlazarBackend` (live via python-chi). Chosen by config via `get_backend()`. |
| `advisor/inventory/` | Static CHI@Edge hardware catalog (types, arch, GPU, profiles, peripherals). Sourced from python-chi; curated fallback when offline. Cached to JSON, refreshable. |
| `advisor/artifacts/` | Ingest Trovi artifacts (README + flattened notebook), chunk + embed into one FAISS store **partitioned by `artifact_id`**. `RetrievalRouter` classifies the task, selects artifact_ids, budgets per-artifact retrieval, and returns context **with provenance**. |
| `advisor/reason/` | LLM reasoner → structured `Recommendation`. Tejas Llama client by default; Anthropic dev fallback; deterministic heuristic when no creds. |
| `advisor/validate/` | CHI@Edge trap checks; pass/fail per check. |
| `advisor/emit/` | Renders a runnable `python-chi` spec (`add_device_reservation`, `container.Container`) + a no-submit dry check. |
| `advisor/cli.py` | One command running read → retrieve → reason → validate → emit. |
| `advisor/config.py` | All settings from env / `.env`. Backend and API keys never hardcoded. |
| `advisor/logging_utils.py` | Append-only JSONL logging of every stage. |

---

## Install

The probe, the offline pipeline, and the tests need **nothing installed** — they
use only the Python standard library. Install the real stack only to enable real
embeddings/FAISS, the LLM, and the live Blazar backend.

```bash
cd chi-edge-advisor
python3 -m venv .venv && source .venv/bin/activate

# (a) zero-install: probe + offline demo + tests work immediately
python probe_availability.py

# (b) full stack (real embeddings, LLM, live availability)
pip install -r requirements.txt
# ...or as a package (installs the `chi-edge-advisor` command):
pip install -e .
```

---

## Quickstart

```bash
# 1. Probe the reference API (first deliverable)
python probe_availability.py
python probe_availability.py --json          # machine-readable

# 2. Run the full pipeline. ADVISOR_OFFLINE=1 forces the dependency-free path
#    (hashing embedder + heuristic reasoner).
ADVISOR_OFFLINE=1 python -m advisor.cli "take a photo with the pi camera every 10 minutes"
ADVISOR_OFFLINE=1 python -m advisor.cli "read temperature and humidity from a sensor"
ADVISOR_OFFLINE=1 python -m advisor.cli "ssh into an edge device"
ADVISOR_OFFLINE=1 python -m advisor.cli "run an image classification model on the edge"

# 3. Real run (after pip install + creds + .env), live availability from Blazar.
#    LLM_PROVIDER=ollama uses a local Ollama model
#    Chameleon credentials must be sourced first (see Deployment below).
python -m advisor.cli "take a photo with the pi camera"
python -m advisor.cli "run a neural network on a Jetson"
```

Each stage prints its inputs/outputs; the final spec is copy-pasteable
`python-chi`. Exit code is `0` only when validation **and** the emit dry-check
pass (so with the `reference_api` backend it will report `FAIL` on
"device free in window" — correctly, because that backend has no live state).

---

## Configuration

All configuration is environment-driven (loaded from `.env` if present). Copy
[`.env.example`](.env.example) to `.env`. Highlights:

| Variable | Default | Meaning |
| --- | --- | --- |
| `AVAILABILITY_BACKEND` | `reference_api` | `reference_api` (static) or `blazar` (live). **Set to `blazar` for real use.** |
| `REFERENCE_API_BASE` | `https://api.chameleoncloud.org` | Discovery API base. |
| `CHI_SITE_NAME` | `CHI@Edge` | python-chi site. |
| `CHI_PROJECT_NAME` | — | Chameleon project for leases. |
| `LLM_PROVIDER` | `tejas` | `tejas` (Llama 3.3 70B), `ollama` (local, no key, no cost), or `anthropic` (dev fallback). |
| `TEJAS_BASE_URL` | `https://ai.tejas.tacc.utexas.edu/v1` | OpenAI-compatible endpoint. |
| `TEJAS_MODEL` | `Meta-Llama-3.3-70B-Instruct` | Model id. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama server (used when `LLM_PROVIDER=ollama`). |
| `OLLAMA_MODEL` | `llama3` | Any model shown by `ollama list`. `qwen2.5:7b-instruct` recommended for reliable JSON output. |
| `TEJAS_API_KEY` / `ANTHROPIC_API_KEY` | — | Credentials (out of scope to acquire here). |
| `EMBEDDING_MODEL` | `BAAI/bge-large-en-v1.5` | Sentence-transformers model. |
| `ADVISOR_OFFLINE` | `0` | Force the dependency-free path regardless of installed libs. |

Nothing about the backend selection or API keys is hardcoded — everything routes
through `advisor/config.py`.

---

## How each stage works

- **READ.** `get_backend()` builds the configured availability backend and calls
  `list_devices()`; the static catalog comes from `InventoryCache`. Availability
  fields are `None` when a backend can't know live state (never silently "free").
- **RETRIEVE.** Artifacts are chunked and embedded into one FAISS store keyed by
  `artifact_id`. `RetrievalRouter` scores the workload against each artifact's
  tags, selects the relevant `artifact_id`s, splits a retrieval budget across
  them, and returns assembled context plus **provenance** (which artifacts
  grounded it).
- **REASON.** The reasoner builds a prompt from {workload, availability,
  inventory, retrieved context} and asks the LLM for a JSON `Recommendation`
  (device/machine_type, count, duration, architecture, image, profiles, runtime,
  reasoning). No creds → a transparent heuristic uses the top-provenance
  artifact's grounded facts instead.
- **VALIDATE.** Runs the trap checks: architecture match (arm64 vs x86_64),
  device actually free in the window, `machine_type`/`device_profile` exist in
  inventory, `platform_version` present, and `runtime=nvidia` when a GPU workload
  lands on a Jetson. Each check returns pass/fail with a reason.
- **EMIT.** Renders `python-chi` using the CHI@Edge-correct calls
  (`add_device_reservation`, `container.Container` — *not* `add_node_reservation`
  / `create_server`) and dry-checks it by constructing the objects **without
  submitting**.

### Seeded artifacts

| `artifact_id` | Source | Device | Grounded facts |
| --- | --- | --- | --- |
| `edge_ssh_image` | ChameleonCloud/edge_ssh_image | raspberrypi4-64 (arm64) | SSH image, port 22 |
| `edge-picamera-image` | ChameleonCloud/edge-picamera-image | raspberrypi4-64 (arm64) | `pi_libcamera` profile, camera |
| `edge_sensehat_image` | ChameleonCloud/edge_sensehat_image | raspberrypi4-64 (arm64) | `pi_sensehat`/`pi_gpio`, sensors |
| `edge-cpu-inference` | teaching-on-testbeds/edge-cpu-inference | raspberrypi4-64 (arm64) | `python:3.9-slim`, MobileNet CPU inference |

Artifact prose lives under [`../grounding/<artifact_id>/`](../grounding) (README
+ flattened notebook markdown). Add an artifact by dropping its markdown there
and appending an entry to `advisor/artifacts/registry.py`.

---

## Logging & benchmarking

Every stage appends a JSON line to `data/runs.jsonl` (configurable via
`ADVISOR_LOG_PATH`), keyed by a per-run `run_id`: inputs, retrieved
`artifact_id`s, the recommendation, validation results, and the emitted spec.
This is the substrate for later benchmark grading.

```bash
python -c "import json;[print(json.loads(l)['stage']) for l in open('data/runs.jsonl')]"
```

---

## Testing

The suite mocks the network and the LLM and runs with **no dependencies**:

```bash
python -m unittest discover -s tests -v      # stdlib, zero installs
pytest                                       # if pytest is installed
```

Covers the adapter interface (`test_availability.py`), the router's artifact
selection + budget + provenance (`test_router.py`), the validator's trap checks
(`test_validator.py`), and the reasoner with a mocked LLM (`test_reasoner.py`).

---

## Project layout

```
chi-edge-advisor/
├── probe_availability.py       # FIRST deliverable: static-vs-live verdict
├── advisor/
│   ├── config.py               # env/.env settings (backend & keys never hardcoded)
│   ├── logging_utils.py        # JSONL per-stage logging
│   ├── http_util.py            # stdlib urllib GET/JSON (probe runs install-free)
│   ├── availability/           # DeviceAvailability + backends (reference_api, blazar)
│   ├── inventory/              # static catalog cache
│   ├── artifacts/              # registry, embeddings, FAISS store, RetrievalRouter
│   ├── reason/                 # LLM clients + reasoner + Recommendation schema
│   ├── validate/               # CHI@Edge trap checks
│   ├── emit/                   # python-chi spec renderer + dry check
│   └── cli.py                  # end-to-end pipeline command
├── tests/                      # network + LLM mocked; runs under stdlib unittest
├── data/                       # caches + runs.jsonl (generated)
├── requirements.txt            # production "real stack" deps
├── .env.example                # copy to .env
└── pyproject.toml
```

---

## Deployment (stub)

> Credential acquisition is **out of scope** for this prototype — this section
> documents the build/run/deploy steps and the config to fill in.

Target: a Chameleon VM (e.g. KVM@TACC) wired to a Tejas-style model API,
mirroring how `RAG-docs-chameleon` is deployed.

1. **Provision.** Launch a small Ubuntu VM on KVM@TACC (or any host that can
   reach `api.chameleoncloud.org`, the Tejas endpoint, and CHI@Edge/Blazar).
2. **Build.**
   ```bash
   git clone <this repo> && cd chi-edge-advisor
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e .            # or: pip install -r requirements.txt
   ```
3. **Configure** (`.env`):
   - `AVAILABILITY_BACKEND=blazar`
   - `CHI_SITE_NAME=CHI@Edge`, `CHI_PROJECT_NAME=<your project>`
   - Chameleon credentials: create an **Application Credential** at
     `chi.edge.chameleoncloud.org → Identity → Application Credentials`,
     download the `openrc`, and `source` it before running. Do **not** mix
     with a username/password RC file in the same shell — app credentials
     carry their own project scope and reject an additional `project_name`
     override. Acquisition details are out of scope here.
   - `LLM_PROVIDER=tejas` (or `ollama` for local, credential-free use),
     `TEJAS_BASE_URL`, `TEJAS_MODEL`, `TEJAS_API_KEY` — *token to be provided*.
   - `EMBEDDING_MODEL=BAAI/bge-large-en-v1.5` (first run downloads weights;
     pre-warm on the VM to avoid cold-start latency).
4. **Warm caches.** `python -c "from advisor.inventory import InventoryCache; InventoryCache().refresh()"`
   and build the artifact store once so FAISS is persisted under `data/`.
5. **Run.** `chi-edge-advisor "<workload>"` (or `python -m advisor.cli ...`).
6. **Operate.** Ship `data/runs.jsonl` to your logging sink for benchmark grading.

### Roadmap → MCP server

The pipeline stages are already function-shaped. Wrapping them as MCP tools
(`read_availability`, `retrieve_artifacts`, `reason`, `validate`, `emit`) lets
the existing RAG chatbot call the advisor directly. Because embeddings, the LLM
client, and the availability backend already match/return-toward the
`RAG-docs-chameleon` stack, the store and model client can be shared rather than
duplicated.
```
