# chameleon-work — workspace notes for Claude

One workspace, four components. Read `README.md` for the map, `PROJECT_GUIDE.md` for usage.

## Do not move or rename these three directories

`RAG-docs-chameleon/`, `chi-edge-advisor/`, and `grounding/` must stay top-level siblings with these exact names — they mirror `/home/cc/` on the Chameleon node and the layout is load-bearing:

- systemd on the node: `WorkingDirectory=/home/cc/RAG-docs-chameleon` (see `docs/reference/rag-app.service.reference`)
- `web_rag.py` does `import advisor_room` — a bare same-directory module
- the `advisor` package is wired into the RAG venv via an absolute-path `pip install -e`
- `chi-edge-advisor/advisor/config.py` defaults `grounding_dir` to `_PKG_ROOT.parent / "grounding"` (sibling assumption)
- `benchmark_v4/tools/bench_config.yaml` pins node paths under `/home/cc/`

`RAG-docs-chameleon/` is an **independent git repo** (upstream: Odysseus707/RAG-docs-chameleon) on branch `wip/advisor-integration` — do not switch it back to `main` (that would remove `advisor_room.py` from the worktree). The workspace repo gitignores it.

`vivek.pem` (root) is the node SSH key: gitignored, never commit, referenced by `benchmark_v4/tools/bench_config.yaml` and `node_sync.sh` at this exact location.

## Local run caveats

- Run advisor tests with `LLM_PROVIDER=none` (a live local Ollama breaks the heuristic test); the offline CLI needs `AVAILABILITY_BACKEND=reference_api`.

## graphify

This workspace has a knowledge graph at `graphify-out/` with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when `graphify-out/graph.json` exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If `graphify-out/wiki/index.md` exists, use it for broad navigation instead of raw source browsing.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
