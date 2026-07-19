# chi-edge-advisor: Prototype State and Build Notes

**Project:** OSRE 2026 Fellowship. CHI@Edge Allocation-Aware Resource Advisor ("From Lookup to Reasoning").
**Fellow:** Vivek Rai
**Companion document to:** `project_log.md` (which covers the Milestone 1 coding benchmark).
**Scope of this document:** the standalone `chi-edge-advisor` prototype. This is the Read plus Reason pipeline from the pitch, covering the "map the allocation API" and "load to resource brain" milestones.
**Status as of 2026-07-01:** the full seven-module pipeline runs end to end against live CHI@Edge data. Reasoning currently runs on a local Ollama model so no paid API or network round-trip is required. 28 tests pass.

This document is the shared context for the prototype. Anyone picking it up (the fellow in a later session, a mentor, a future collaborator) should be able to understand what was built, why, what failed along the way, and what remains, without reconstructing it from chat logs.

---

## 1. What the prototype is, in one paragraph

`chi-edge-advisor` takes a plain-language workload description (for example "take a photo with the pi camera") and returns a runnable python-chi lease spec. It reads live device availability from Blazar, retrieves relevant Trovi artifacts by semantic search, uses an LLM to reason over that context into a structured recommendation, validates the recommendation against CHI@Edge-specific traps, and emits the reservation code. It is a standalone prototype now; the plan is to wrap it as an MCP server plugged into `ChameleonCloud/RAG-docs-chameleon` later. The stack mirrors that repo (FAISS, `BAAI/bge-large-en-v1.5`, an OpenAI-compatible LLM client) so the eventual integration is low-friction.

---

## 2. Where it lives

- Path: `/Users/vivekrai/Downloads/Trovi Artifacts/chi-edge-advisor/`
- Python package: `chi-edge-advisor`. All code under `advisor/`.
- Not a git repository yet. Initializing one is a prerequisite before MCP packaging.

---

## 3. Architecture: seven modules

| Module | Path | Purpose |
|---|---|---|
| Availability adapter | `advisor/availability/` | `DeviceAvailability` dataclass plus `BlazarBackend` and `ReferenceApiBackend` behind a common abstract base class |
| Static inventory cache | `advisor/inventory/catalog.py` | Curated fallback catalog; python-chi source with JSON cache |
| Artifact store | `advisor/artifacts/` | FAISS store partitioned by `artifact_id`; `RetrievalRouter` with provenance |
| Reasoner | `advisor/reason/` | `TejasClient`, `OllamaClient`, `AnthropicClient`; heuristic fallback |
| Validator | `advisor/validate/checks.py` | Six CHI@Edge trap checks |
| Emitter | `advisor/emit/spec.py` | Renders the runnable python-chi lease spec |
| CLI | `advisor/cli.py` | Orchestrates read then retrieve then reason then validate then emit |

Supporting files: `advisor/config.py` (Settings dataclass, `.env` loader), `advisor/logging_utils.py` (JSONL run log), `advisor/http_util.py` (stdlib `urllib`, no external dependency).

The artifact store implements the design settled in the architecture session: one FAISS store partitioned by an `artifact_id` metadata field, so each Trovi artifact is an independently retrievable namespace. The `RetrievalRouter` selects relevant artifacts per workload and returns assembled context with provenance, which is the signal the generalization experiment will use to measure whether artifacts transfer or only serve as task-specific lookups.

---

## 4. Key design decisions

- **Offline by default.** The probe, pipeline, and tests all run with zero installs. Optional heavy dependencies are import-guarded. `ADVISOR_OFFLINE=1` forces the pure-Python path even when the real stack is installed.
- **Never hardcode the backend or API keys.** All configuration lives in `.env` and `Settings`. Real environment variables always win over `.env`.
- **Config-driven LLM provider.** `LLM_PROVIDER=` selects `tejas` (Tejas AI, OpenAI-compatible), `ollama` (local, free, no key), or `anthropic` (hosted, paid).
- **Grounding.** Four Trovi artifacts are seeded in `grounding/`: `edge-picamera-image`, `edge_ssh_image`, `edge_sensehat_image`, `edge-cpu-inference`. The edge-cpu-inference content was fetched from `teaching-on-testbeds/edge-cpu-inference` on GitHub. Note that this repo lives under that org, not the ChameleonCloud org.

---

## 5. Empirical finding: the availability probe

`probe_availability.py` was the first deliverable, by design, because the whole shape of the Read layer depended on its result. The verdict:

```
VERDICT: reference API is STATIC-ONLY
  The reference API does NOT reflect live reservation state.
  Moreover it exposes NO CHI@Edge device inventory at all
  (edge site has 0 clusters / 0 nodes).
  => Live availability MUST come from Blazar via python-chi.
```

All live-status endpoints returned 404. No reservation-like fields appear in node records. This is why `AVAILABILITY_BACKEND=blazar` is the required setting for real use.

**Why this matters beyond the code.** In the earlier architecture session the reference API was drawn as a possible source of both static inventory and live status, because the supervisor's tip pointed at `api.chameleoncloud.org/docs` as the place to get availability information. The probe settles that question for CHI@Edge: the reference API is not useful for the edge site at all, neither for live state nor for static inventory. For CHI@Edge, both inventory and availability come through Blazar and python-chi. This is a finding to relay to the team, since it revises the assumption behind that tip. The reference API may still be the right source for the bare-metal sites (CHI@TACC, CHI@UC), which is worth confirming separately if the advisor is later generalized across sites.

The `ReferenceApiBackend` remains in the codebase behind the same interface, so if a future reference-API status endpoint appears, or the generalization to bare-metal sites happens, no rewrite is needed.

---

## 6. The Blazar authentication journey

This was the most involved part of the build. The full chain is documented so future sessions do not re-tread it.

**Pitfall 1: `blazarclient` not installed.**
Symptom: `availability read failed: No module named 'blazarclient'`, live devices seen: 0. Cause: python-chi 1.2.10 imports `blazarclient` at `chi/clients.py:74` but does not declare `python-blazarclient` as a dependency. Fix: install it, but be aware the default install pulls the upstream OpenStack fork, which is the wrong one (see Pitfall 2).

**Pitfall 2: upstream `blazarclient` has no `.device` resource.**
Symptom: `AttributeError: 'Client' object has no attribute 'device'`. Cause: CHI@Edge device reservations are a Chameleon-specific Blazar extension. Upstream python-blazarclient only knows `host`, `lease`, `floatingip`. The Chameleon fork adds `device`. Fix (the user must run this in their own shell; auto-install from external git is blocked by safety policy):

```bash
pip install --force-reinstall --no-deps \
  "git+https://github.com/ChameleonCloud/python-blazarclient.git"
```

Verification: `pip show python-blazarclient` still shows `Home-page: launchpad.net/blazar` because the fork does not change metadata. The real test is whether `devices.py` physically exists:

```bash
python -c "import blazarclient, os; print(os.path.exists(os.path.join(os.path.dirname(blazarclient.__file__), 'v1', 'devices.py')))"
# Must print: True
```

**Pitfall 3: OIDC auth fails non-interactively.**
Symptom: `keystoneauth1.exceptions.http.Unauthorized: Unrecognized schema in response body. (HTTP 401)`. Cause: portal users typically authenticate via SSO, and the resulting OIDC token cannot be used programmatically. Fix: use Application Credentials instead. Portal path: `chi.edge.chameleoncloud.org` then Identity then Application Credentials then Create. Download the openrc file and source it in a fresh terminal. The RC file sets `OS_AUTH_TYPE=v3applicationcredential`, `OS_AUTH_URL=https://chi.edge.chameleoncloud.org:5000/v3`, and the credential id and secret.

**Pitfall 4: stale `OS_*` vars contaminate the session.**
Symptom: `OptionError: You have provided a username. In V3 you must also provide user_domain_id or user_domain_name.` Cause: an old `OS_USERNAME` from a previous RC file is still set alongside the new app-credential vars. Fix: open a clean shell, source only the app-credential openrc, and verify with `env | grep OS_` that only the four app-credential vars are present.

**Pitfall 5: `chi.set("project_name")` conflicts with Application Credentials.**
Symptom: `HTTP 401: Application credentials cannot request a scope.` Cause: the project scope is already embedded in an application credential, so Keystone rejects any attempt to set it again. Fix, now in `advisor/availability/blazar.py`:

```python
def _ensure_site(self) -> None:
    if self._configured:
        return
    self._chi.use_site(self.site_name)
    import os
    if settings.chi_project_name and os.environ.get("OS_AUTH_TYPE") != "v3applicationcredential":
        self._chi.set("project_name", settings.chi_project_name)
    self._configured = True
```

**Pitfall 6: wrong field names on python-chi Device objects.**
Symptom: live devices seen: 63, but `machine_type: unknown` and empty peripherals. Cause: `Device` does not expose `.architecture`, `.gpu`, or `.peripherals`. The actual fields are:

```python
dev.device_name                # e.g. 'iot-rpi4-01'
dev.device_type                # e.g. 'raspberrypi4-64'  (this IS machine_type)
dev.supported_device_profiles  # e.g. ['pi_gpio']        (not 'peripherals')
dev.reservable                 # True/False
dev.uuid                       # UUID string
dev.authorized_projects        # e.g. {'all'}
dev.owning_project             # project ID string
```

Fix: `_device_to_availability` now derives `architecture` and `gpu` from the `device_type` string and reads `supported_device_profiles` for peripherals. Also note that raw `blazarclient.device.list()` returns `type=container` for every device, which is the Blazar reservation type, not the hardware type. Use `hardware.get_devices()` (the python-chi wrapper), which returns the correct `device_type`.

---

## 7. Current configuration

`.env` (user's setup):

```
AVAILABILITY_BACKEND=blazar
CHI_SITE_NAME=CHI@Edge
CHI_PROJECT_NAME=CHI-261560
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
```

Chameleon credentials are set via an Application Credential openrc, sourced per session rather than stored in `.env`. Credential acquisition is intentionally out of scope for this project's documentation.

Local Ollama models available: `llama3`, `qwen2.5:7b-instruct`, `qwen3:8b`, `qwen3:14b`, `gemma3:12b`, `gemma4:26b`. `qwen2.5:7b-instruct` is recommended over base `llama3` for the reasoner, because the reasoner emits structured JSON and `llama3` sometimes leaves the `reasoning` field blank.

---

## 8. Verified end-to-end run

Command:

```
python -m advisor.cli "take a photo with the pi camera"
```

Result summary (run_id `b359ccd80d0b`):

1. **Read.** Backend blazar, `reports_live_state=True`, site reachable, 63 live devices seen.
2. **Retrieve.** Embedder bge-large-en-v1.5 over 162 chunks. Selected artifact: `edge-picamera-image` (task score 2.5, others lower).
3. **Reason.** Produced by ollama. `machine_type=raspberrypi4-64`, count 1, 3h, `arch=arm64`, `gpu=False`, `device_name=iot-rpi4-01`, image `ghcr.io/chameleoncloud/edge-picamera-image:latest`, `device_profiles=['pi_libcamera']`.
4. **Validate.** All six checks PASS (machine_type_exists, architecture_match, device_profile_exists, device_free_in_window, platform_version_present, gpu_runtime_nvidia). Overall PASS.
5. **Emit.** Structural dry-check PASS.

Emitted spec:

```python
from datetime import timedelta
import chi
from chi import container, lease

chi.use_site("CHI@Edge")

my_lease = lease.Lease("advisor-iot-rpi4-01-lease", duration=timedelta(hours=3))
my_lease.add_device_reservation(
    amount=1, machine_type="raspberrypi4-64", device_name="iot-rpi4-01"
)
my_lease.submit(idempotent=True)

my_container = container.Container(
    name="advisor-iot-rpi4-01-run",
    image_ref="ghcr.io/chameleoncloud/edge-picamera-image:latest",
    exposed_ports=[],
    reservation_id=my_lease.device_reservations[0]["id"],
    device_profiles=['pi_libcamera'],
    command=["sleep", "infinity"],
)
my_container.submit()
```

This spec uses `add_device_reservation` (not `add_node_reservation`) and `container.Container` (not `create_server`), the two most common CHI@Edge API mistakes and the ones the validator guards against. This is the exact "action gap" failure the Milestone 1 benchmark documented, now closed by the prototype end to end.

---

## 9. Working versus not yet done

**Working:**

- Full seven-module pipeline, end to end, against live CHI@Edge data.
- 28 tests passing (`pytest tests/`).
- Real Blazar connectivity: 63 live devices, 35 free at time of test.
- Correct artifact routing via bge-large semantic search.
- Local Ollama reasoning (free, no API key, no network).
- All six validator trap checks.
- Runnable python-chi spec emission with real device names.
- Structured JSONL run logging (`data/runs.jsonl`).

**Not yet done or future work:**

- `diag_blazar.py` is a dev diagnostic, not production code. Removable before MCP packaging.
- python-chi is not installed in the venv, so the emitter does a structural dry-check only. Actual lease submission requires python-chi plus live credentials.
- `HF_TOKEN` warning on every run. Cosmetic, fixable by setting `HF_TOKEN` in `.env`.
- Reasoning field sometimes empty with `llama3:latest`. Switch to `qwen2.5:7b-instruct` for more reliable JSON.
- MCP server wrapper not yet built.
- Integration with `ChameleonCloud/RAG-docs-chameleon` not yet done.
- Only four of the planned grounding artifacts are seeded. More to ingest.

---

## 10. How to run from a clean session

```bash
# 1. Activate venv
cd "/Users/vivekrai/Downloads/Trovi Artifacts/chi-edge-advisor"
source .venv/bin/activate

# 2. Source Chameleon Application Credentials
#    (fresh shell, no old OS_* vars)
source ~/Downloads/app-cred-chi-edge-advisor-openrc.sh

# 3. Verify: should show only 4 OS_ vars, no OS_USERNAME
env | grep OS_

# 4. Run
python -m advisor.cli "your workload description here"

# Examples:
python -m advisor.cli "take a photo with the pi camera"
python -m advisor.cli "run a neural network on a Jetson"
python -m advisor.cli "read temperature from SenseHAT"
```

---

## 11. Open threads and next steps

- **Reasoner reliability.** Move the default Ollama model to `qwen2.5:7b-instruct` for dependable JSON output.
- **Install python-chi in the venv** so the emitter can do a real submission dry-run rather than only a structural check.
- **Initialize a git repo** as a prerequisite to MCP packaging.
- **Build the MCP server wrapper** that exposes read, recommend, and emit as tools, then wire it into the RAG chatbot. This is item 4 on that repo's own ROADMAP, so it is the maintainer's planned next step rather than a detour.
- **Ingest more grounding artifacts** beyond the seeded four.
- **Benchmark expansion.** Add benchmark prompts of the form "I need X, what is free right now, and what should I reserve," which force the Read layer and the reasoning layer to combine. These are currently untested in the benchmark sheet and are exactly what the advisor now makes possible.
- **Team confirmation.** Relay the probe finding (reference API is static-only and exposes no CHI@Edge inventory) and confirm whether the reference API is the right source for the bare-metal sites when the advisor is later generalized across Chameleon.

---

*Last updated 2026-07-01. All code is in place and the full pipeline is verified working.*
