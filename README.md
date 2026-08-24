# chameleon-work

OSRE 2026 fellowship workspace — **"From Lookup to Reasoning"**: a self-hosted RAG chatbot for Chameleon Cloud docs, an allocation-aware CHI@Edge resource advisor seamed into it, and an executable-checker benchmark that evaluates the whole system.

## ⚠️ Do not move or rename these three directories

`RAG-docs-chameleon/`, `chi-edge-advisor/`, and `grounding/` mirror `/home/cc/` on the Chameleon node and their layout is load-bearing: the node's systemd unit pins `WorkingDirectory=/home/cc/RAG-docs-chameleon`, `web_rag.py` imports `advisor_room` as a same-directory module, the `advisor` package is installed into the RAG venv via absolute-path `pip install -e`, and `advisor/config.py` resolves `grounding/` as a sibling of `chi-edge-advisor/`. Reorganize *around* them, never inside.

## Map

| Entry | What it is |
|---|---|
| `RAG-docs-chameleon/` | The chatbot ("the fork"): FAISS retrieval + reranker + LLM, Streamlit UI (`web_rag.py`); `advisor_room.py` bridges to the advisor. **Independent git repo** (upstream: [Odysseus707/RAG-docs-chameleon](https://github.com/Odysseus707/RAG-docs-chameleon)), on branch `wip/advisor-integration` — ignored by this repo, clone separately on a fresh machine. |
| `chi-edge-advisor/` | The advisor engine (`advisor` package): routes a workload description to grounded artifacts, checks device availability, emits a CHI@Edge resource recommendation. Has its own pytest suite. |
| `grounding/` | The advisor's grounding corpus — one folder of Trovi-artifact docs per supported workload. |
| `benchmark/` | The evaluation benchmark, packaged as **`chi-edge-bench`** — 134 items in two suites, deterministic AST checkers, a scoring harness, and four adapters. Installable on any machine (`pip install "git+…#subdirectory=benchmark"`); see `benchmark/README.md`. No code imports from the other projects — it drives them via `chi_edge_bench/tools/bench_config.yaml`. |
| `docs/` | All documentation: `usage/`, `architecture/`, `reference/`, `archive/` — see `docs/README.md`. |
| `PROJECT_GUIDE.md` | **Start here.** Master usage guide (chatbot, advisor, benchmark, node ops), verified against the live node. |
| `CLAUDE.md` | Workspace notes for Claude Code (constraints + knowledge-graph usage). |
| `graphify-out/` | Generated knowledge graph of the workspace (`graph.html` to explore, `GRAPH_REPORT.md` for the audit). |
| `vivek.pem` | SSH key for the Chameleon node — gitignored, **never commit**; referenced at this exact location by `benchmark/chi_edge_bench/tools/bench_config.yaml` and `node_sync.sh`. |

## How the pieces relate

```
user ──► web_rag.py (Streamlit) ──► rag.py (FAISS + reranker + LLM)
              │ if edge question (gate)
              ▼
        advisor_room.py ──► advisor package ──► grounding/<artifact>/
                            (chi-edge-advisor)
benchmark ──drives──► both, as external processes (bench_config.yaml)
```

Everything heavy runs on a Chameleon bare-metal node (`/home/cc/`, systemd service `rag-app`, Ollama LLM); see `docs/usage/runbook.md` to relaunch after a fresh lease.

## Where to start

1. `PROJECT_GUIDE.md` — how to run and test everything
2. `docs/README.md` — documentation index
3. `graphify-out/graph.html` — visual map of the codebase

## Fresh-machine notes

- `RAG-docs-chameleon/` is not in this repo: `git clone https://github.com/Odysseus707/RAG-docs-chameleon.git` then check out `wip/advisor-integration` (do **not** work on `main` — the advisor bridge files live only on the WIP branch).
- One virtualenv for the whole workspace, at the root: `.venv` (gitignored).
  `chi-edge-advisor/.venv` and `benchmark/.venv` are symlinks to it, so every
  documented `.venv/bin/python ...` invocation still works from either project.
  Recreate with `python -m venv .venv && .venv/bin/python -m pip install -r
  chi-edge-advisor/requirements.txt -e "benchmark[xlsx,dev]"`.
  The benchmark is a real package now (`chi-edge-bench`), so an editable
  install puts the `chi-edge-bench` command on PATH and makes `pytest` work
  from `benchmark/`.
- A virtualenv is not relocatable: moving or renaming this directory bakes the
  old absolute path into `pyvenv.cfg`, every console-script shebang, and
  `activate`. The symptom is `python: command not found` immediately after
  activating, or a broken `pip` while `.venv/bin/python` still works. Rebuild
  the venv if that happens.
- Obtain `vivek.pem` separately and place it at the workspace root.
