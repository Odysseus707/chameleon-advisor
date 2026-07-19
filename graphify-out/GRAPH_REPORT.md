# Graph Report - .  (2026-07-19)

## Corpus Check
- 132 files · ~184,686 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 703 nodes · 1329 edges · 40 communities (35 shown, 5 thin omitted)
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 195 edges (avg confidence: 0.65)
- Token cost: 580,921 input · 0 output

## Community Hubs (Navigation)
- Advisor Pipeline & CHI@Edge
- RAG Indexing & Eval Pipeline
- Benchmark Scoring & Calibration
- AST Checker Library
- Benchmark Findings & Ablation
- Node Ops & Run Config
- Benchmark Run Adapters
- Artifact Registry & Router
- Advisor LLM Clients
- Recommendation Validation
- Benchmark Item Builder
- Advisor CLI & Emit
- Device Inventory Catalog
- Feedback Store & Report
- Workload Spec & RouterTree Tests
- Offline Embedder & Router Tests
- Availability Backend Interface
- Embedding Providers
- Artifact FAISS Store
- Device Availability Model
- Reference API Backend
- Benchmark Stub chi Package
- Advisor Config Settings
- HTTP Helper & Adapter Tests
- Flat Retrieval Router
- Pipeline Run Logging
- Recommendation Reasoner
- Blazar Availability Probe
- Reasoner Tests
- Artifact Extractions A1/A5/A6
- Semantic Scoring
- Artifact Extractions A2/A3
- RAG Docs & Roadmap
- Jaccard Similarity Metric
- XLSX Export Tool
- Misc Path Helpers
- Advisor Package Root
- Advisor Project Node

## God Nodes (most connected - your core abstractions)
1. `ArtifactStore` - 40 edges
2. `RetrievalRouter` - 32 edges
3. `DeviceAvailability` - 27 edges
4. `HashingEmbedder` - 19 edges
5. `WorkloadSpec` - 19 edges
6. `RouterTree` - 19 edges
7. `Reasoner` - 19 edges
8. `validate_recommendation()` - 19 edges
9. `DeviceType` - 17 edges
10. `RetrievalResult` - 16 edges

## Surprising Connections (you probably didn't know these)
- `Evaluator Prompt (dual-LLM design)` --semantically_similar_to--> `CHI@Edge trap validation checks`  [INFERRED] [semantically similar]
  RAG-docs-chameleon/results/model_parameters_mapping.pdf → chi-edge-advisor/README.md
- `RAG Eval Pipeline (golden question set, eval/)` --semantically_similar_to--> `CHI@Edge Coding Benchmark v4 README`  [INFERRED] [semantically similar]
  RAG-docs-chameleon/README.md → benchmark_v4/README.md
- `Advisor Firing Gate (edge cue word + tag score >= ADVISOR_GATE)` --semantically_similar_to--> `Reranker Score Threshold (0.5 cutoff)`  [INFERRED] [semantically similar]
  PROJECT_GUIDE.md → RAG-docs-chameleon/ROADMAP.md
- `Fed Grounding Files (A1-A6 flattened artifacts as run context)` --semantically_similar_to--> `Advisor Grounding Corpus (grounding/)`  [INFERRED] [semantically similar]
  benchmark_v4/README.md → README.md
- `RAG model parameter sweep (Models 1-14 + baselines)` --conceptually_related_to--> `RAG-docs-chameleon chatbot`  [INFERRED]
  RAG-docs-chameleon/results/model_parameters_mapping.pdf → docs/architecture/architecture-and-integration.md

## Import Cycles
- 1-file cycle: `benchmark_v4/harness/stub_chi/chi/__init__.py -> benchmark_v4/harness/stub_chi/chi/__init__.py`

## Hyperedges (group relationships)
- **CHI@Edge Trovi Artifact Corpus A1-A6 (extractions + grounding)** — benchmark_v4_extractions_a1, benchmark_v4_extractions_a2, benchmark_v4_extractions_a3, benchmark_v4_extractions_a4, benchmark_v4_extractions_a5, benchmark_v4_extractions_a6, benchmark_v4_grounding_a1, benchmark_v4_grounding_a2, benchmark_v4_grounding_a3, benchmark_v4_grounding_a4, benchmark_v4_grounding_a5, benchmark_v4_grounding_a6, benchmark_v4_readme_fed_grounding [EXTRACTED 1.00]
- **Benchmark v4 Integrity Mechanisms** — benchmark_v4_readme_gold_admission_gate, benchmark_v4_readme_computed_tiers, benchmark_v4_benchmark_v4_decisions_hallucination_canaries, benchmark_v4_benchmark_v4_decisions_ast_only_checks, benchmark_v4_readme_verification_levels, benchmark_v4_readme_h0_h1_instrument [INFERRED 0.85]
- **RAG Retrieval Quality Stack** — rag_docs_chameleon_readme_retrieval_pipeline, rag_docs_chameleon_readme_parent_child_chunking, rag_docs_chameleon_readme_cross_encoder_reranker, rag_docs_chameleon_readme_tiered_context_assembly, rag_docs_chameleon_roadmap_reranker_threshold [INFERRED 0.85]
- **Advisor grounding artifact corpus (RouterTree taxonomy)** — grounding_edge_ssh_image_readme_edge_ssh_image, grounding_edge_picamera_image_readme_edge_picamera_image, grounding_edge_sensehat_image_readme_edge_sensehat_image, grounding_edge_cpu_inference_readme_edge_cpu_inference, grounding_serve_edge_chi_main_serve_edge_chi [EXTRACTED 1.00]
- **Advisor room integration flow** — docs_architecture_architecture_and_integration_rag_docs_chameleon, docs_architecture_architecture_and_integration_advisor_room, docs_architecture_architecture_and_integration_should_fire_gate, docs_architecture_architecture_and_integration_edge_resource_advisory_injection, docs_architecture_architecture_and_integration_local_llm, chi_edge_advisor_readme_chi_edge_advisor [EXTRACTED 1.00]
- **Five-stage advisor pipeline (READ-RETRIEVE-REASON-VALIDATE-EMIT)** — chi_edge_advisor_readme_pipeline, chi_edge_advisor_readme_blazarbackend, chi_edge_advisor_readme_referenceapibackend, docs_architecture_router_refactor_plan_retrieval_router, chi_edge_advisor_readme_trap_checks, chi_edge_advisor_readme_spec_emitter [EXTRACTED 1.00]

## Communities (40 total, 5 thin omitted)

### Community 0 - "Advisor Pipeline & CHI@Edge"
Cohesion: 0.07
Nodes (61): BlazarBackend, CHI@Edge testbed, chi-edge-advisor, READ-RETRIEVE-REASON-VALIDATE-EMIT pipeline, probe_availability.py availability probe, python-chi, raspberrypi4-64 device type, ReferenceApiBackend (+53 more)

### Community 1 - "RAG Indexing & Eval Pipeline"
Cohesion: 0.05
Nodes (53): fetch_source(), load_cache(), Build (or refresh) the FAISS vector index from Chameleon docs.  Each documentati, save_cache(), main(), Run the RAG pipeline against the golden question set and save results for manual, Summarise reranker scores and source breakdown from debug_candidates., retrieval_stats() (+45 more)

### Community 2 - "Benchmark Scoring & Calibration"
Cohesion: 0.06
Nodes (47): Checker-vs-Human Calibration (Cohen's kappa on v3 cells), Checker Gaps P03/P08 (actionable false negatives), Code-Fence Recovery (--wrap-code, ast.parse gate), Benchmark v4 Decision Log (D01-D18), Generation-Equivalence Grading (D01), evaluate(), exec_v1(), extract_code() (+39 more)

### Community 3 - "AST Checker Library"
Cohesion: 0.09
Nodes (35): AST-Only Forbidden-Call Checks (D10), _calls(), _calls_named(), check_abstain_or_discover(), check_availability_query(), check_container_call(), check_forbidden_calls(), check_kwarg() (+27 more)

### Community 4 - "Benchmark Findings & Ablation"
Cohesion: 0.08
Nodes (32): Benchmark v4 Session Report, Distractor Robustness via A4 (D08), Hallucination Canaries (D09, T4b abstention items), Table A7: Router Ablation — Tree vs Flat, Tree vs Flat Routing Result (flat 86.7% > tree 68.9% at artifact level), Artifact Extraction A4: MCP_SLM_Project / OpenMCP (edge LLM + bare-metal distractor), Grounding A4: OpenMCP Resource-Provisioning Notebooks, assign() (+24 more)

### Community 5 - "Node Ops & Run Config"
Cohesion: 0.07
Nodes (30): bench_config.yaml — run_bench Configuration, node_sync.sh script, Load-Bearing Directory Layout Constraint, vivek.pem — Chameleon Node SSH Key, Advisor Firing Gate (edge cue word + tag score >= ADVISOR_GATE), Chameleon Bare-Metal Node (integration-testbed, 2x Tesla P100), Fork Adapter — In-Process Chatbot Pipeline Runner, advise() (+22 more)

### Community 6 - "Benchmark Run Adapters"
Cohesion: 0.13
Nodes (19): AnthropicAdapter, cmd_pilot(), ForkAdapter, git_info(), hash_other_runs(), items_for_condition(), main(), now_iso() (+11 more)

### Community 7 - "Artifact Registry & Router"
Cohesion: 0.18
Nodes (17): advisor.artifacts -- Trovi artifact ingestion, FAISS store, retrieval router., ArtifactMeta, Registry of seeded Trovi artifacts.  Each artifact is one independently-retrieva, RetrievalRouter: classify workload -> select artifacts -> budget -> assemble.  G, Structured attribution for one assembled context section (one chunk)., RetrievalResult, SectionProvenance, _dot() (+9 more)

### Community 8 - "Advisor LLM Clients"
Cohesion: 0.12
Nodes (14): advisor.reason -- LLM (Tejas Llama default / Anthropic fallback) reasoner., AnthropicClient, get_llm_client(), LLMClient, OllamaClient, Protocol, LLM client abstraction.  Default: the Tejas AI OpenAI-compatible endpoint servin, Build the configured client. Raises if its SDK/creds are missing. (+6 more)

### Community 9 - "Recommendation Validation"
Cohesion: 0.20
Nodes (7): CheckResult, validate_recommendation(), ValidationReport, advisor.validate -- CHI@Edge trap checks over a Recommendation., _check(), Validator trap-check tests., TestValidator

### Community 10 - "Benchmark Item Builder"
Cohesion: 0.17
Nodes (19): amount(), avail(), cany(), cs(), devname(), emit(), envkeys(), hours() (+11 more)

### Community 11 - "Advisor CLI & Emit"
Cohesion: 0.18
Nodes (16): _hr(), main(), chi-edge-advisor CLI.  One command: given a plain-language workload, run the ful, run_pipeline(), advisor.emit -- render + dry-check a runnable python-chi lease spec., dry_check(), DryCheckResult, Emitter: turn a validated Recommendation into a runnable python-chi spec.  Uses (+8 more)

### Community 12 - "Device Inventory Catalog"
Cohesion: 0.18
Nodes (9): DeviceType, InventoryCache, Path, Static CHI@Edge hardware catalog: device types, arch, GPU, peripherals.  The pro, Fetch, cache, and query the CHI@Edge static catalog., Return the catalog, using cache unless ``refresh`` is set., Prefer python-chi; fall back to the curated catalog., One CHI@Edge machine_type and its capabilities. (+1 more)

### Community 13 - "Feedback Store & Report"
Cohesion: 0.14
Nodes (12): Connection, main(), FeedbackRecord, FeedbackStore, hash_response(), Return True if this session has already submitted feedback for this response., Return the set of response_hash values already rated in this session., Return aggregated feedback statistics. (+4 more)

### Community 14 - "Workload Spec & RouterTree Tests"
Cohesion: 0.16
Nodes (7): Structured workload: free text plus an optional declared site., WorkloadSpec, RouterTree tests: site gate, use-case routing, flat-parity (offline embedder)., TestFlatParity, TestSiteGate, TestUseCaseRouting, TreeTestBase

### Community 15 - "Offline Embedder & Router Tests"
Cohesion: 0.15
Nodes (6): HashingEmbedder, Deterministic hashing bag-of-words embedder (offline fallback).      Feature-has, RetrievalRouter artifact-selection tests (offline hashing embedder)., RouterTestBase, TestBudgetAndProvenance, TestClassification

### Community 16 - "Availability Backend Interface"
Cohesion: 0.15
Nodes (9): AvailabilityBackend, get_backend(), Common interface both backends implement., Return normalized availability for CHI@Edge devices.          When ``machine_typ, Return normalized availability for a single device, or None., Lightweight reachability check. Override for richer diagnostics., Factory: build the configured backend.      ``name`` overrides config; otherwise, Availability adapter: normalized live/near-live device state for CHI@Edge.  Two (+1 more)

### Community 17 - "Embedding Providers"
Cohesion: 0.16
Nodes (9): BgeEmbedder, Embedder, get_embedder(), _l2_normalize(), Protocol, Embedding backends.  Production path mirrors RAG-docs-chameleon: BAAI/bge-large-, BAAI/bge-large-en-v1.5 via sentence-transformers (production path)., Pick bge when available (and not forced offline); else hashing. (+1 more)

### Community 18 - "Artifact FAISS Store"
Cohesion: 0.17
Nodes (7): ArtifactStore, Chunk, chunk_markdown(), Path, Split markdown into overlapping chunks, preferring section boundaries., Builds/persists/queries the partitioned artifact vector store., Return (filename, text) for each markdown file of an artifact.

### Community 19 - "Device Availability Model"
Cohesion: 0.23
Nodes (6): DeviceAvailability, Normalized availability model + backend interface + config-driven factory., One normalized view of a CHI@Edge device's identity + reservation state.      Ev, Convenience: is the device free right now?          Returns True/False when know, BlazarBackend, BlazarBackend: authoritative live CHI@Edge state via python-chi.  Live reservati

### Community 20 - "Reference API Backend"
Cohesion: 0.22
Nodes (6): ReferenceApiBackend: CHI@Edge availability via the Chameleon reference API.  The, Test whether the reference API exposes any live status endpoint.          Return, Discover node detail URLs by walking site -> clusters -> nodes., ReferenceApiBackend, get_json(), GET a URL and parse JSON, never raising for network/HTTP errors.      Returns an

### Community 21 - "Benchmark Stub chi Package"
Cohesion: 0.20
Nodes (4): get_devices(), _load(), Mirror python-chi hardware.get_devices for CHI@Edge.     filter_reserved=True ->, Stub `chi` package for V1 snapshot execution (benchmark v4).  Implements only th

### Community 22 - "Advisor Config Settings"
Cohesion: 0.18
Nodes (7): _load_dotenv(), Path, Central settings module.  Everything configurable lives here and is sourced from, Minimal .env loader (no external dependency).      Only sets variables that are, Immutable snapshot of runtime configuration., Settings, One-shot Blazar device-read diagnostic.  Run this in the SAME shell where your C

### Community 23 - "HTTP Helper & Adapter Tests"
Cohesion: 0.25
Nodes (6): HttpResult, Tiny dependency-free HTTP/JSON helper (stdlib urllib).  Kept dependency-free so, _fake_get_json(), Adapter interface tests (network mocked)., TestDeviceAvailability, TestReferenceApiBackend

### Community 24 - "Flat Retrieval Router"
Cohesion: 0.31
Nodes (3): Score each artifact by tag/title overlap with the workload., RetrievalRouter, _tokens()

### Community 25 - "Pipeline Run Logging"
Cohesion: 0.24
Nodes (6): _json_default(), Any, Path, Structured JSONL logging of every pipeline stage.  Each pipeline run appends one, Append-only JSONL logger scoped to a single pipeline run., RunLogger

### Community 26 - "Recommendation Reasoner"
Cohesion: 0.31
Nodes (3): Explainable non-LLM recommendation driven by artifact provenance., Reasoner, Build from an LLM's JSON, tolerating missing/renamed keys.

### Community 27 - "Blazar Availability Probe"
Cohesion: 0.40
Nodes (9): _fmt(), _fmt_blazar(), main(), probe_blazar(), Any, Query Blazar via python-chi for live device state.      Returns a result dict; ', Fetch one node from a baremetal site and inspect its schema shape., run_probe() (+1 more)

### Community 28 - "Reasoner Tests"
Cohesion: 0.31
Nodes (3): FakeLLM, Reasoner tests with a mocked LLM client (no network)., TestReasoner

### Community 29 - "Artifact Extractions A1/A5/A6"
Cohesion: 0.33
Nodes (6): Artifact Extraction A1: edge_ssh_image (imperative python-chi), Artifact Extraction A5: serve-edge-chi (ONNX inference on Pi 5), Artifact Extraction A6: edge-cpu-inference (TFLite MobileNet on Pi 4), Grounding A1: Ubuntu SSH Image for CHI@Edge, Grounding A5: Serving ML Models on Edge Devices (GourmetGram), Grounding A6: Edge CPU Inference

### Community 30 - "Semantic Scoring"
Cohesion: 0.53
Nodes (5): ndarray, cosine_sim(), get_embeddings(), Score a pipeline run against the golden set using embedding-based semantic simil, score_run()

### Community 31 - "Artifact Extractions A2/A3"
Cohesion: 0.50
Nodes (4): Artifact Extraction A2: edge-picamera-image (OO python-chi, pi_libcamera), Artifact Extraction A3: edge_sensehat_image (OO python-chi, pi_sensehat), Grounding A2: edge-picamera-image / libcamera stack, Grounding A3: CHI@Edge Sense-HAT Tutorials

### Community 32 - "RAG Docs & Roadmap"
Cohesion: 0.67
Nodes (3): Chameleon Docs Assistant README, Chameleon API MCP Server (planned live-data integration), RAG-docs-chameleon Roadmap

## Knowledge Gaps
- **20 isolated node(s):** `node_sync.sh script`, `chi-edge-advisor`, `Chameleon Docs Assistant README`, `Traefik Reverse Proxy Service (docker-compose)`, `RAG App Python Requirements` (+15 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_load()` connect `Node Ops & Run Config` to `Device Inventory Catalog`, `Availability Backend Interface`, `Embedding Providers`, `Artifact FAISS Store`, `Flat Retrieval Router`, `Recommendation Reasoner`?**
  _High betweenness centrality (0.348) - this node is a cross-community bridge._
- **Why does `README.md — Workspace Map (chameleon-work)` connect `Benchmark Findings & Ablation` to `Benchmark Scoring & Calibration`, `Node Ops & Run Config`?**
  _High betweenness centrality (0.147) - this node is a cross-community bridge._
- **Are the 22 inferred relationships involving `ArtifactStore` (e.g. with `RetrievalResult` and `RetrievalRouter`) actually correct?**
  _`ArtifactStore` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `RetrievalRouter` (e.g. with `ArtifactStore` and `RetrievedChunk`) actually correct?**
  _`RetrievalRouter` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `DeviceAvailability` (e.g. with `BlazarBackend` and `ReferenceApiBackend`) actually correct?**
  _`DeviceAvailability` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `HashingEmbedder` (e.g. with `FakeLLM` and `TestReasoner`) actually correct?**
  _`HashingEmbedder` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `WorkloadSpec` (e.g. with `ArtifactMeta` and `RetrievalResult`) actually correct?**
  _`WorkloadSpec` has 14 INFERRED edges - model-reasoned connections that need verification._