# From Lookup to Reasoning

**OSRE 2026 fellowship — Chameleon Cloud.** A documentation chatbot for Chameleon
is a lookup system: it can quote the docs, but it cannot tell you whether the
hardware you just asked for exists, is free, or can run your workload. This
project adds the missing half and then measures whether it helped.

Three components, and a benchmark built to grade them:

- a **self-hosted RAG chatbot** over the Chameleon docs,
- an **allocation-aware advisor** that routes a plain-language workload to real,
  currently-free hardware and grounds it in Trovi artifacts,
- an **executable-checker benchmark** — 270 items across two wings — that scores
  answers by running them, not by string-matching them.

The central result is a negative one that was written down before it was
measured: grounding an assistant in live allocation state fixes *availability*
answers and barely touches *capability* answers, because Blazar exposes what
exists and is free, not what the hardware can do.

---

## Results

Two wings, two different testbeds, never blended — different hardware and
different suites, so compare shape between them, never scores.

### Chameleon bare-metal wing — 136 items

`Meta-Llama-3.3-70B-Instruct` via the TACC Tejas endpoint. Identical system
prompt in both arms; the only difference is whether advisor context is present.
0 errors in either arm.

| checker group | bare model | with advisor |
|---|---:|---:|
| capability | 19.2% | **77.8%** |
| feasibility | 38.4% | **95.1%** |
| mechanism | 0.0% | **72.0%** |
| specifics | 0.8% | **50.4%** |
| safety | 97.8% | 94.9% |
| **every checker passes** | **3/136** | **60/136** |

**Zero regressions on the reservation suite** — the set of items that pass only
in the bare arm is empty.

The `mechanism` row is the sharpest: without reference material the model does
not write `python-chi` at all. Of 40 code answers, 26 were portal
click-throughs and 10 were `openstack` CLI. Given retrieved artifacts it writes
`python-chi` that satisfies 72% of mechanism checks.

### CHI@Edge wing — 134 items, controlled A/B

`qwen2.5:32b` on one 2×P100 node. Same RAG, same model, same prompts; the only
variable is whether the advisor fires.

| condition / suite | metric | advisor OFF | advisor ON | Δ |
|---|---|---:|---:|---:|
| blind, reservation | feasibility | 36.8% | 66.2% | **+29.4** |
| blind, reservation | capability | 48.3% | 48.9% | +0.6 |
| matched, reservation | full-item PASS | 5/48 | 30/48 | **+25** |
| matched, reservation | feasibility | 45.7% | 82.9% | **+37.1** |
| matched, reservation | capability | 53.4% | 85.6% | **+32.2** |

**The headline split:** availability accuracy moves 37% → 66%; capability
accuracy does not move at all (48.3% → 48.9%). Blazar answers "does this exist
and is it free", not "can it do the job" — so an advisor grounded only in
allocation state cannot improve capability. That prediction was recorded in
writing before the run, and it is the measured case for ingesting artifacts.

Where artifact coverage stops, so does the benefit: 2 of 7 CHI@Edge device types
are documented by any Trovi artifact, and on the undocumented accelerators
(all Jetsons, Coral) the advisor stops helping.

### Retrieval quality

Router ablation over the 40 bare-metal items that have a target artifact:

| level | recall |
|---|---:|
| L1, no truncation | **82.5%** |
| L2 @ k=3 (default) | 35.0% |
| L2 @ k=10 | 57.5% |

Tree routing beats flat retrieval at every budget (35.0% vs 22.5% at k=3), and
**site routing is exact: 31/31**. All remaining loss is within-cluster ranking —
the router reaches the right site and the right use-case cluster, then picks the
wrong artifact inside it.

### Verified against the real testbed

13 gold answers were executed against live CHI@TACC and CHI@UC (project
CHI-231225, `python-chi` 1.2.10): 7/7 and 6/6 did everything their item
declares, confirmed from the API rather than from a harness trace. That pass
found four defects the benchmark now catches:

| finding | consequence |
|---|---|
| `get_node_reservation` raises `AttributeError` on `python-chi` 1.2.10 | reproduced twice, five days apart |
| the lease-id trap is silent | passing a lease id where a reservation id belongs is **accepted**; the instance reaches ERROR, never ACTIVE |
| `submit()` defaults to `show="widget"` | renders only inside a notebook, and otherwise raises *after* the instance is ACTIVE — 31 golds corrected |
| `associate_floating_ip()` with no argument | takes the first unallocated IP in the project, not the one the lease reserved — 7 golds corrected |

The last one is the project's own thesis in miniature: reserve one thing, bind
to another.

---

## Repository map

Everything listed here is in the repository and browsable on GitHub.

| Path | What it is |
|---|---|
| **`PROJECT_GUIDE.md`** | **Start here to run things.** Master usage guide for the chatbot, advisor, benchmark and node ops, verified against the live node. |
| `benchmark/` | The evaluation benchmark, packaged as **`chi-edge-bench`**. See `benchmark/README.md`. |
| `benchmark/chi_edge_bench/` | The CHI@Edge wing: 134 items, AST checkers, scoring harness, four run adapters, and the offline `python-chi` stub. |
| `benchmark/chameleon_bench/` | The Chameleon bare-metal wing: 136 items, 91 artifacts, their extractions and rendered grounding, a 29-row capability table, 14 recorded state snapshots, and its own stub. |
| `benchmark/corpus_v2/tools/` | Corpus authoring and verification: extraction, pinning, variant generation, the repair passes, and the gold verifiers. |
| `benchmark/benchmark_v4_decisions.md` | **The decision log, D01–D84** — the reasoning behind every methodology choice, including the checker bug that moved every published capability number and why the pre-fix exports were kept. |
| `benchmark/exports/RESULTS.md` | Generated results for the CHI@Edge wing, with its caveats stated. |
| `benchmark/notebooks/` | Live-verification drivers (`live_api_probe.py`, `live_gold_batch.py`) and the gold-verification notebook. |
| `benchmark/tests/` | Benchmark test suite. |
| `chi-edge-advisor/` | The advisor engine (the `advisor` package): routes a workload to grounded artifacts, checks device availability, emits a recommendation. Has its own pytest suite. |
| `grounding/` | The advisor's grounding corpus — one folder of Trovi-artifact docs per supported workload (5 workloads). |
| `docs/reference/` | Node reference files: the `rag-app` systemd unit and the node environment template. |
| `connect_chatbot.sh` | SSH tunnel + lifecycle helper for the chatbot on the node. |

**Not in this repository:**

- **The chatbot** is its own repo — [Odysseus707/RAG-docs-chameleon](https://github.com/Odysseus707/RAG-docs-chameleon),
  branch `feat/reserve-from-chatbot`. FAISS retrieval + reranker + LLM with a
  Streamlit UI (`web_rag.py`); `advisor_room.py` is the bridge to the advisor.
  Clone it separately; do **not** use `main`, which has no advisor bridge.
- Run outputs, the generated knowledge graph, working notes, and all
  credentials are deliberately untracked. See `.gitignore`, which says why for
  each one.

---

## How the pieces fit

```
user ──► web_rag.py (Streamlit) ──► rag.py (FAISS + reranker + LLM)
              │ if the question is about edge hardware (gate)
              ▼
        advisor_room.py ──► advisor package ──► grounding/<artifact>/
                            (chi-edge-advisor)       Blazar availability

benchmark ──drives both as external processes──► bench_config.yaml
```

The advisor has two halves and the benchmark exercises each on the items that
suit it: the **ladder** ("what is free at this site, and what of it fits") needs
a site, so reservation items get it; the **retrieval router** ("what does the
corpus show about doing this") needs only the question, so code items get
retrieved artifact grounding.

Everything heavy runs on a Chameleon bare-metal node (`/home/cc/`, systemd
service `rag-app`, Ollama).

---

## The two wings

| | CHI@Edge wing | Chameleon bare-metal wing |
|---|---|---|
| package dir | `chi_edge_bench/` | `chameleon_bench/` |
| items | 134 (core 50, reservation 84) | 136 (CB code 40, RB ranked-list 96) |
| answer shape | `python-chi` code, device choices | `python-chi` code / ranked node types |
| graded on | capability, feasibility, mechanism, safety, specifics | the same five groups |
| reference arm | `qwen2.5:32b`, controlled A/B | Llama-3.3-70B via Tejas |

A gold answer is admitted only if it passes 100% of its own checkers. Answers
are graded by **executing** them against a pinned offline stub, so a checker
cannot pass on an answer that merely looks right.

---

## Measurement gates

All verified on the current tree:

| gate | result | command |
|---|---|---|
| CHI@Edge gold gate | **134/134** | `validate_golds --suite all` |
| Chameleon gold gate | **136/136** | `validate_golds --wing chameleon_bench --suite all` |
| stub execution | **31 correct, 0 failed** | `corpus_v2/tools/verify_golds_exec.py` |
| artifact authoring gate | **90/90** | `corpus_v2/tools/verify_authored.py run` |
| verdict parity (L2), gold gate (L3) | **hold** | `corpus_v2/tools/parity_baseline.py verify` |
| advisor suite | **234 passed** | `pytest chi-edge-advisor/tests` |

Verdict parity is the invariant that guarantees no CHI@Edge measurement moved
while the bare-metal wing was built.

### Reproducing the numbers

```bash
cd benchmark
V=../.venv/bin/python

LLM_PROVIDER=none $V -m pytest -q
LLM_PROVIDER=none $V -m chi_edge_bench.harness.validate_golds --suite all
LLM_PROVIDER=none $V -m chi_edge_bench.harness.validate_golds \
    --wing chameleon_bench --suite all
LLM_PROVIDER=none $V corpus_v2/tools/verify_golds_exec.py

# the two arms
$V chi_edge_bench/tools/run_llm_wing.py --advisor off --system <arm>
$V chi_edge_bench/tools/run_llm_wing.py --advisor on  --system <arm>
$V chi_edge_bench/tools/score_wing.py --wing chameleon_bench --suite all \
     --condition chameleon_wing --system <bare> --compare <advisor>

# retrieval quality
cd ../chi-edge-advisor
$V tools/ablate_router.py --wing chameleon_bench --l2-k 3
```

---

## Setup

One virtualenv for the whole workspace, at the root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r chi-edge-advisor/requirements.txt \
                                -e "benchmark[xlsx,dev]"
```

`chi-edge-advisor/.venv` and `benchmark/.venv` are symlinks to it, so every
documented `.venv/bin/python …` invocation works from either project. The
editable install puts the `chi-edge-bench` command on PATH.

The benchmark also installs standalone, both wings included:

```bash
pip install "git+https://github.com/Odysseus707/chameleon-advisor#subdirectory=benchmark"
python -m chi_edge_bench.harness.validate_golds --wing chameleon_bench --suite all
```

Run the advisor tests with `LLM_PROVIDER=none`; a live local Ollama changes what
the heuristic test sees. The offline CLI needs `AVAILABILITY_BACKEND=reference_api`.

A virtualenv is not relocatable: moving or renaming this directory bakes the old
absolute path into `pyvenv.cfg`, every console-script shebang, and `activate`.
The symptom is `python: command not found` right after activating. Rebuild it.

The node SSH key and the Chameleon application credentials are not in this
repository and must be obtained separately; `.gitignore` pins the paths the
tooling expects.

---

## Scope and known gaps

Stated precisely, because the measurement is the contribution:

- **One model per wing, one node.** No claim about other models.
- **Full-item PASS is strict** — every checker on an item must pass. The group
  rates are the informative measure.
- **Ranked-list golds are solved against pinned snapshots**, under a
  free-now-only convention. They are not a claim about what is free right now;
  live free counts change hourly, so re-solving against live Blazar would
  measure what time it is.
- **Fed conditions are paste-shaped, not RAG-shaped.** Feeding a ~10k-token
  artifact blob as the retrieval query is not what the deployed chatbot sees;
  those rows measure the model, not the pipeline.
- **Uncovered-item ground truth is ours.** No artifact documents 5 of the
  CHI@Edge device types, so a hand-authored capability table defines
  correctness there.
- **KVM@TACC is out of scope** — it reserves flavors, not hosts.
- **`chi_edge_bench.tools.export_xlsx` does I/O at import time** and fails
  unless a prior run has produced `tier_report.json`, which trips one import
  test.
- **The level-1 content-parity pin is stale** against 9 later CB item edits.
  Verdict parity (L2) and the gold gate (L3) both hold, so no measurement
  moved; the pin needs re-taking.

---

## Do not move or rename these three directories

`RAG-docs-chameleon/`, `chi-edge-advisor/` and `grounding/` mirror `/home/cc/`
on the Chameleon node, and the layout is load-bearing:

- the node's systemd unit pins `WorkingDirectory=/home/cc/RAG-docs-chameleon`,
- `web_rag.py` imports `advisor_room` as a bare same-directory module,
- the `advisor` package is installed into the RAG venv by absolute-path
  `pip install -e`,
- `advisor/config.py` resolves `grounding/` as a sibling of `chi-edge-advisor/`,
- `bench_config.yaml` pins node paths under `/home/cc/`.

Reorganize *around* them, never inside.

---

## License

MIT — see `benchmark/LICENSE`.
