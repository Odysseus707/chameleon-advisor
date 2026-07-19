# Seam Map — RAG-docs-chameleon ↔ chi-edge-advisor Integration Recon

*Phase: read-only reconnaissance. No code written or edited. Every claim cites
`file:line`. Uncertainties are flagged inline as **[UNCERTAIN]**.*

> **Doc note:** The briefing said to "read `chi-edge-advisor_prototype-state.md`
> first for full context." That file does not exist anywhere in the tree
> (`find . -iname "*prototype-state*"` → no results). I used
> `chi-edge-advisor/README.md` and the source itself as the context substitute.
> If a prototype-state doc exists elsewhere, this report has not seen it.

---

## 0. What the two systems actually are (one paragraph each)

**RAG-docs-chameleon** — A Streamlit chat app (`web_rag.py`) that does pure
retrieve-then-generate over Chameleon Cloud public documentation. Retrieval
logic lives in `rag.py`; document ingestion in `loader.py`; index building in
`build_index.py`. It talks to a Llama-3.3-70B model hosted at TACC's Tejas
endpoint via the OpenAI-compatible `langchain_openai.ChatOpenAI`. It is a fork
of `github.com/Odysseus707/RAG-docs-chameleon` (`git remote -v`), itself
carrying merged PRs from `UD-CRPL/improve-retrieval-pipeline`
(`git log --oneline -3`).

**chi-edge-advisor** — A seven-stage Read→Retrieve→Reason→Validate→Emit
pipeline (`advisor/cli.py:31`) that recommends a concrete CHI@Edge device +
lease config for a plain-language workload. Its retrieval is a *partitioned*
artifact store (`advisor/artifacts/store.py`) keyed by `artifact_id`, with a
routing layer (`advisor/artifacts/router.py`) that classifies the workload to a
subset of artifacts before searching. Its LLM client abstraction
(`advisor/reason/llm.py`) already targets the *same* Tejas/Llama endpoint by
default.

The two were designed to rhyme: the advisor's embeddings docstring says
"Production path mirrors RAG-docs-chameleon"
(`advisor/artifacts/embeddings.py:3-4`) and its embedding-model setting comment
says "mirror RAG-docs-chameleon" (`advisor/config.py`, `embedding_model` field).

---

## 1. How the chatbot constructs its LLM call — where the prompt is assembled

**The LLM object and the prompt template are both built in
`rag.py:create_llm_chain()` (`rag.py:211-237`).**

- Model client: `ChatOpenAI(model="Meta-Llama-3.3-70B-Instruct",
  temperature=0, openai_api_key=TEJAS_API_KEY, openai_api_base=TEJAS_API_BASE)`
  (`rag.py:212-217`). Base URL hardcoded to
  `https://ai.tejas.tacc.utexas.edu/v1` (`rag.py:15`).
- Prompt is a LangChain `ChatPromptTemplate.from_messages([...])`
  (`rag.py:219-235`) with three parts:
  1. a fixed **system** message (`rag.py:220-232`),
  2. a `MessagesPlaceholder(variable_name="history")` (`rag.py:233`),
  3. a **user** turn: `"Question: {question}\nContext: {context}"`
     (`rag.py:234`).
- The chain is `prompt | llm` (LCEL pipe) (`rag.py:237`).

**Where the call is actually invoked (two call sites):**
- CLI: `chain.invoke({"question": query, "context": context, "history": []})`
  (`rag.py:256`).
- Web (the deployed path): `st.session_state.chain.invoke({"question":
  question, "context": context, "history": history_messages})`
  (`web_rag.py:468-470`).

**Where `context` comes from:** `build_context()` (`rag.py:94-208`) does the
whole retrieval-and-assembly job and returns `(sources, context,
debug_candidates)`. The `context` string is a formatted block with two labelled
sections — `=== PRIMARY DOCUMENTATION ===` and `=== SUPPLEMENTARY CONTEXT ===`
(`rag.py:194-207`) — built from reranked parent passages.

### The injection seam (this is the important answer)

Two clean seams exist, differing in invasiveness:

1. **Context-string injection (lowest friction).** The model only ever sees a
   single opaque `context` string built by `build_context()` and passed through
   `chain.invoke(...)` at `web_rag.py:468`. Anything appended to that string
   reaches the model with zero prompt-template changes. You could add a third
   labelled section, e.g. `=== EDGE RESOURCE ADVISORY ===`, alongside the
   existing PRIMARY/SUPPLEMENTARY sections (`rag.py:194-207`), carrying the
   advisor's `RetrievalResult.context_text` or a rendered `Recommendation`. The
   system prompt already tells the model how to weight labelled sections
   (`rag.py:222-228`), so a new section is idiomatic.

2. **Prompt-template injection (more explicit).** Add a new templated variable
   (e.g. `{advisor}`) to the user turn at `rag.py:234` and thread it through
   both `.invoke()` calls (`rag.py:256`, `web_rag.py:468`). More honest about
   provenance, but touches the template and every call site.

**Best injection point for tool-style results:** between line 459 and line 468
of `web_rag.py`. That's *after* `build_context()` returns the docs context but
*before* `chain.invoke()` fires — the natural place to run the advisor (as a
tool or a direct call), merge its output into `context`, and hand the combined
string to the model. This block runs once per user turn and already has
`question`, `context`, and `history` in scope (`web_rag.py:459-470`).

---

## 2. Does it have a tool / function-calling / agent layer?

**No. It is pure retrieve-then-generate.** Evidence:

- A targeted grep for tool/agent constructs across all RAG `.py` files
  (`mcp`, `tool_call`, `tools=`, `function_call`, `bind_tools`, `langgraph`,
  `create_react_agent`, `AgentExecutor`) returned **zero matches**.
- The only model plumbing is the single `ChatOpenAI` + `ChatPromptTemplate`
  chain described in §1. No `.bind_tools(...)`, no tool schema, no agent
  executor, no model-driven dispatch. The chain is a straight `prompt | llm`
  (`rag.py:237`).
- Retrieval is a fixed function call inside the request handler (`build_context`,
  `web_rag.py:459`), not a tool the model can choose to call.

So a tool/agent layer would have to be **added**. Upside: because generation is
one LangChain LCEL chain and `ChatOpenAI` supports `.bind_tools()`, upgrading to
tool-calling is mechanically small; the seam is `create_llm_chain()`
(`rag.py:211-237`).

*Model-capability note* **[UNCERTAIN]:** `Meta-Llama-3.3-70B-Instruct` served via
a vLLM/OpenAI-compatible endpoint *usually* supports OpenAI-style
`tools=`/`tool_calls`, but whether the Tejas deployment
(`ai.tejas.tacc.utexas.edu/v1`) actually enables the tools API is not
determinable from this repo. Cannot confirm without hitting the endpoint. The
safe integration path (context-string injection, §1 option 1) does **not** depend
on this.

---

## 3. MCP client support — present or needs adding?

**Needs adding. There is no MCP client anywhere in the codebase.** The same grep
(§2) found no `mcp` references. `requirements.txt` contains LangChain,
`langchain-openai`, `faiss-cpu`, `sentence-transformers`, `streamlit`, and
scraping libs — **no `mcp`, no `langchain-mcp-adapters`, no MCP SDK** (full
`requirements.txt` reviewed).

### If adding MCP — where the client would be instantiated

The deployed app uses Streamlit's re-run model: `web_rag.py` runs top-to-bottom
on every interaction, but expensive singletons are cached in `st.session_state`
and built once:

- `st.session_state.vectorstore` / `parents` — built once in a spinner
  (`web_rag.py:251-254`).
- `st.session_state.chain` — built once via `create_llm_chain()`
  (`web_rag.py:256-257`).

**An MCP client should follow the same pattern: a `st.session_state.mcp_client`
(or `st.session_state.advisor_tools`) created once alongside the chain
(`web_rag.py:256-257`)**, then invoked per-turn inside the `if question:` block,
in the 459→468 gap identified in §1. Reasons:

- MCP session setup (stdio/HTTP handshake, tool discovery) is expensive and must
  not run on every Streamlit re-run — session-state caching is the existing,
  correct pattern here.
- The per-turn call site already has `question` + `context` in scope and runs
  exactly once per user message (`web_rag.py:453-470`).

**[UNCERTAIN] / caution:** MCP's Python SDK is `async`; Streamlit's execution
model is synchronous and re-entrant. Bridging an async MCP `ClientSession` into
Streamlit typically needs an explicit event loop (`asyncio.run(...)` per call, or
a persistent background loop). This is a known friction point and a likely source
of bugs — flagging it now rather than mid-integration.

*Advisor-side note:* the advisor is a **library + CLI** (`python -m advisor.cli`,
`cli.py:16-18`), **not** an MCP server. To reach it over MCP you would wrap
`advisor.cli.run_pipeline` (or the `RetrievalRouter`/`Reasoner` objects directly)
in a small MCP server. That wrapper does not exist yet.

---

## 4. FAISS store: document schema + metadata — are the two stores compatible?

**Short answer: same embedding model and same FAISS metric, but *different index
objects, different metadata schemas, and different partitioning models*. Keep
them as two separate stores; do not merge into one index.**

### RAG-docs-chameleon store

- Built by `create_vectorstore()` (`rag.py:41-70`) using
  `FAISS.from_documents(child_docs, embedding=get_embeddings_model())`
  (`rag.py:68`) — a **LangChain community FAISS** wrapper, persisted with
  `vectorstore.save_local(save_path)` (`rag.py:69`) to `vect_store/` as
  `index.faiss` + `index.pkl` (the load guard checks `index.faiss`,
  `web_rag.py:247`).
- **Parent/child (small-to-big) design.** Parent chunks (2000 chars,
  `rag.py:28-32`) are stored *outside* FAISS in a plain `parents.json`
  (`rag.py:65-66`, loaded by `load_parents`, `rag.py:73-75`). Only **child**
  chunks (400 chars, `rag.py:34-38`) go into FAISS (`rag.py:59-68`).
- **Per-child metadata fields:** `parent_id` (`rag.py:62`) plus loader-attached
  `source` (URL), `source_type`, `title` (`loader.py:127-128`,
  `loader.py:260-261`). `source_type` ∈
  `{readthedocs, python_chi, blog, forum, gitbook, chameleon_org, other}`
  (`loader.py:206-219`). Child `page_content` is prefixed with a
  `[source_type: title]` header (`rag.py:57-61`).
- **Parent record schema** (`parents.json`): `{content, source, source_type}`
  keyed by stringified integer id (`rag.py:50-54`).
- Retrieval: FAISS similarity → group by `source_type` → cross-encoder rerank
  (`BAAI/bge-reranker-base`, `rag.py:86`) → dedupe by URL → expand children back
  to parents via `parent_id` (`rag.py:181-192`).

### chi-edge-advisor store

- Built by `ArtifactStore.build()` (`advisor/artifacts/store.py:106-127`). In the
  production path it constructs a **raw `faiss.IndexFlatIP`** directly
  (`store.py:139-145`) — *not* the LangChain FAISS wrapper — plus a **parallel
  Python list** of `Chunk` records as the metadata sidecar.
- **Persistence is a single JSON file** `data/artifact_store.json` holding
  `{embedder, dim, chunks, vectors}` (`store.py:150-160`); it rebuilds the faiss
  index on load (`store.py:162-169`). This is *not* `save_local` format — the two
  on-disk layouts are incompatible.
- **Chunk metadata schema:** `Chunk(artifact_id, text, source_file, chunk_index)`
  (`store.py:34-39`). Partition key is **`artifact_id`**, and search filters by it
  *before* scoring (`store.py:178-199`, `allowed = set(artifact_ids)`).
- Chunking is markdown-heading-aware, 1200 chars / 150 overlap (`store.py:52-73`)
  — coarser than RAG's 400-char children, and **single-level** (no parent/child
  hierarchy).

### Compatibility verdict

| Dimension | RAG-docs | chi-edge-advisor | Compatible? |
|---|---|---|---|
| Embedding model | `BAAI/bge-large-en-v1.5` (`rag.py:22`) | `BAAI/bge-large-en-v1.5` (`config.py`) | ✅ identical |
| Vector normalization | `normalize_embeddings=True` (`rag.py:24`) | `normalize_embeddings=True` (`embeddings.py:78-82`) | ✅ identical |
| FAISS metric | cosine (normalized) via LangChain FAISS | `IndexFlatIP` = IP on normalized = cosine (`store.py:143`) | ✅ same math |
| Index object / on-disk format | LangChain `save_local` → `index.faiss`+`index.pkl` | raw `IndexFlatIP` + `artifact_store.json` | ❌ different |
| Metadata schema | `source, source_type, title, parent_id` | `artifact_id, source_file, chunk_index` | ❌ different |
| Partition model | flat, reranked, source-type-balanced | partitioned by `artifact_id`, routed | ❌ different |
| Chunk model | parent/child (2000/400) | single-level (1200) | ❌ different |

Because the vectors live in the **same cosine space** (same model, same
normalization), a cross-store *query* is numerically meaningful — you *can* embed
one query and search both indices and the scores are comparable. But the
**metadata schemas and index containers do not unify**: RAG's `parent_id` +
`parents.json` expansion has no analogue in the advisor's flat `artifact_id`
partitions, and vice versa. **Keep two stores and federate at retrieval time**
(query both, merge results) rather than merging indices. This also preserves the
advisor's core value — its `artifact_id` partitioning + routing (`router.py`) —
which a flat merged store would destroy.

---

## 5. Embedding model — confirmed from code (both sides)

**Confirmed identical: `BAAI/bge-large-en-v1.5`, both with L2-normalized
embeddings.**

- RAG: `HuggingFaceBgeEmbeddings(model_name="BAAI/bge-large-en-v1.5",
  model_kwargs={"device": "cpu"}, encode_kwargs={"normalize_embeddings": True})`
  — `rag.py:20-25`. Also baked into the Docker image:
  `SentenceTransformer('BAAI/bge-large-en-v1.5')` (`Dockerfile`, pre-download
  step).
- Advisor: default `EMBEDDING_MODEL` = `"BAAI/bge-large-en-v1.5"`
  (`advisor/config.py`, `embedding_model` field); `BgeEmbedder` loads it via
  `SentenceTransformer(...)` and encodes with `normalize_embeddings=True`
  (`advisor/artifacts/embeddings.py:64-82`).

**Two caveats worth knowing:**
1. RAG uses LangChain's `HuggingFaceBgeEmbeddings` wrapper; the advisor uses
   `sentence_transformers.SentenceTransformer` directly. Same underlying weights
   and same normalization, so vectors match — but the *wrapper* differs (matters
   only if you try to reuse one embeddings object across both, which you
   shouldn't need to).
2. The advisor has an **offline hashing fallback** (`HashingEmbedder`,
   `embeddings.py:34-58`) selected when `ADVISOR_OFFLINE` is set or
   sentence-transformers/torch is missing (`embeddings.py:85-92`). Vectors from
   that fallback are **not** in bge space and **not** comparable to RAG's store.
   Any federated-retrieval integration must assert the advisor is on its bge path,
   not the fallback, or cross-store scores are garbage. **This is a real footgun.**

---

## 6. Configuration & deployment — and what a local instance needs that you lack

### RAG-docs-chameleon deployment

- **Containerized.** `Dockerfile`: `python:3.11-slim`, installs CPU-only torch,
  pip-installs `requirements.txt`, **pre-downloads the bge model into the
  image**, copies app files, exposes `8501`, runs `streamlit run web_rag.py`
  (`Dockerfile`, `CMD`).
- **Entry point:** `web_rag.py` (Streamlit), port 8501.
- **Reverse proxy / TLS:** `docker-compose.yml` runs **Traefik v2.11** in front,
  terminating TLS via Let's Encrypt (`traefik` service), routing `Host(${HOST})`
  to the app on 8501.
- **Env vars** (`.env.example`): `TEJAS_API_KEY=sk-...`,
  `HOST=ai.chameleoncloud.org`, `EMAIL=...`. Compose also injects
  `FEEDBACK_DB_PATH` and `SESSION_LOG_PATH` (`docker-compose.yml`,
  `rag-app.environment`). `TEJAS_API_KEY` is read at `rag.py:16`.
- **State volumes:** `vect_store` (the FAISS index), `_fetch_cache`,
  `feedback_db`, and an **external** `session_log` volume (`docker-compose.yml`,
  `volumes:`).
- **The index is not in the repo.** `vect_store/` is gitignored (`.gitignore`)
  and confirmed absent locally (`ls vect_store` → absent). `web_rag.py:247-249`
  hard-stops with an error if `vect_store/index.faiss` is missing.

### What a local instance needs that you don't currently have

1. **A built FAISS index.** Run `python build_index.py` (`build_index.py`), which
   **live-scrapes** readthedocs + blog (`loader.py:299-302`; only `readthedocs`
   and `blog` are registered in `SOURCES`) and embeds them. Needs **outbound
   network** to `chameleoncloud.readthedocs.io`, `python-chi.readthedocs.io`,
   `blog.chameleoncloud.org`, and downloads bge weights on first run. No committed
   cache (`_fetch_cache` absent locally). Expect a slow first build.
2. **A valid `TEJAS_API_KEY`** for `ai.tejas.tacc.utexas.edu` (`rag.py:16`,
   `.env.example`). Without it, generation fails. **[UNCERTAIN]** whether your
   advisor's `TEJAS_API_KEY` (same var in the advisor `.env.example`) is the same
   credential / has access — you have a key configured advisor-side (`config.py`
   `tejas_api_key`), so it may already be covered, but validity can't be verified
   from files alone.
3. **The bge model weights** (~1.3 GB) — auto-downloaded by sentence-transformers
   on first use; needs disk + network once.
4. **[Optional for local dev]** You can skip Docker/Traefik entirely and run
   `streamlit run web_rag.py` after `pip install -r requirements.txt` and a built
   index. Traefik/Let's Encrypt/`HOST`/`EMAIL` are only for the public HTTPS
   deployment, not needed locally.

You already have: the advisor's own bge path and Tejas client configured
(`config.py`), a Python venv (`chi-edge-advisor/.venv`), and the flattened
grounding docs (`grounding/`). You do **not** have: a built RAG `vect_store`, the
RAG `_fetch_cache`, or a confirmed-working Tejas key against this endpoint.

---

## 7. Files a real integration would have to touch

Legend: **[upstream]** = a clean change plausibly contributable back to
`Odysseus707/RAG-docs-chameleon`; **[local hack]** = fork-only glue you would not
upstream; **[new]** = a file that must be created.

| File | Change | Nature |
|---|---|---|
| `RAG-docs-chameleon/web_rag.py:459-470` | Insert advisor invocation between `build_context()` and `chain.invoke()`; merge advisor output into `context` (or a new template var). Cache an advisor/MCP client in `st.session_state` alongside the chain (`:256-257`). | **[local hack]** initially; could become **[upstream]** if gated behind a feature flag/env var. |
| `RAG-docs-chameleon/rag.py:194-207` | Add a third labelled context section (e.g. `=== EDGE RESOURCE ADVISORY ===`) in `build_context`'s assembly, and/or extend the system prompt (`:220-232`) to describe it. | **[upstream]** — small, additive, matches the existing PRIMARY/SUPPLEMENTARY idiom. |
| `RAG-docs-chameleon/rag.py:211-237` | Only if going the tool-calling route: `.bind_tools()` on `ChatOpenAI` + a tool schema. | **[upstream]** if generalized; depends on Tejas tools support (§2, uncertain). |
| `RAG-docs-chameleon/requirements.txt` | Add `mcp` / `langchain-mcp-adapters` (MCP path) or a dependency on the advisor package. | **[upstream]** if the feature lands upstream; else **[local hack]**. |
| `RAG-docs-chameleon/Dockerfile` | Copy/install the advisor package into the image; possibly pre-build the advisor artifact store. | **[local hack]** — couples the two projects; not upstream-friendly. |
| `RAG-docs-chameleon/docker-compose.yml` | If the advisor runs as a separate MCP service: add a service + network wiring. Else nothing. | **[local hack]**. |
| `chi-edge-advisor/advisor/mcp_server.py` | Wrap `run_pipeline` / `RetrievalRouter` / `Reasoner` as an MCP server (or a thin importable `advise(workload) -> str`). Does not exist today. | **[new]** — belongs to the advisor repo; upstream *to the advisor*. |
| `chi-edge-advisor/advisor/artifacts/store.py` | Optionally expose a "federated query" helper returning bge-space scores so RAG can merge cross-store results. | **[new / upstream to advisor]**. |
| `integration-notes/` (this dir) | Integration design + glue notes. | **[new]** (already here). |

**The one genuinely clean upstream contribution** is the labelled-section
mechanism (`rag.py:194-207` + system prompt): additive, provider-agnostic, and it
improves the chatbot even without the advisor. Everything that actually *couples*
the two projects (importing the advisor, Docker wiring, MCP service) is fork-local
by nature and should sit behind an env flag so the upstream app still runs
standalone.

---

## 8. The three biggest unknowns blocking integration

1. **Does the Tejas endpoint support OpenAI tool-calling?** (`rag.py:212-217`,
   `ai.tejas.tacc.utexas.edu/v1`.) If yes, the advisor can be a real
   model-invoked tool and the integration is elegant. If no, you're locked into
   context-string injection (§1 option 1) — workable, but the model can't
   *decide* to consult the advisor. Not determinable from the repo; requires
   probing the live endpoint. Also unverified: whether your existing
   `TEJAS_API_KEY` actually authenticates against this deployment.

2. **Async MCP inside synchronous Streamlit.** (§3.) The MCP Python SDK is async;
   Streamlit re-runs top-to-bottom and caches via `st.session_state`
   (`web_rag.py:251-257`). Whether an MCP `ClientSession` can be held across
   Streamlit re-runs without event-loop breakage — or whether you must fall back
   to a per-turn `asyncio.run()` or a direct in-process import of the advisor
   library — is unresolved and the most likely place the integration gets stuck.
   The lower-risk fallback (import the advisor package directly, skip MCP)
   sidesteps this but abandons the MCP goal.

3. **Retrieval-federation semantics + the offline-embedding footgun.** (§4, §5.)
   The two stores share bge cosine space *only when the advisor runs its bge
   path*, not the `HashingEmbedder` fallback (`embeddings.py:85-92`) — and there
   is currently no guard forcing bge in an integrated deployment. Beyond that, the
   *policy* is undecided: does the advisor's recommendation get appended verbatim
   as authoritative context, reranked into RAG's existing cross-encoder pool
   (`rag.py:126-131`, which would require chunk-shaped advisor output), or shown
   as a separate UI panel? Each implies a different touch to
   `build_context`/`web_rag.py`, and none is specified yet.
