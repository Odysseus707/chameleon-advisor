# Router refactor plan: from flat RetrievalRouter to RouterTree

**Phase A deliverable** — read-only map of the current retrieval router, the FAISS/partition
verdict, and the RouterTree design implemented in Phase B.

> **Sources.** The briefing said to read `chi-edge-advisor_prototype-state.md` first. That file
> does not exist anywhere in this tree (already flagged in `seam-map.md` lines 6-10). This map
> was made from the source of record instead: `chi-edge-advisor/advisor/artifacts/{router,store,registry,embeddings}.py`,
> verified line-by-line on 2026-07-16.

---

## 1. The current RetrievalRouter, mapped

### 1.1 Inputs

- A single **plain-language workload string**. There is no structured workload spec anywhere:
  `advisor/cli.py:35` (`run_pipeline(workload: str, ...)`) passes it straight to
  `router.route(workload)` (`cli.py:72-73`). `RAG-docs-chameleon/advisor_room.py` likewise
  passes the raw user question, and additionally uses `router.classify(question)` as its
  fire/no-fire gate.
- An `ArtifactStore` injected at construction (`router.py:39-49`), plus three knobs:
  `total_budget=6`, `max_artifacts=3`, `relevance_floor=0.0`.

### 1.2 Scoring (artifact classification)

`RetrievalRouter.classify()` (`router.py:52-66`) is **lexical, not embedding-based**:

- tokenize the workload with `[a-z0-9]+` (lowercased);
- for each artifact in the global `ARTIFACTS_BY_ID` (`registry.py:99`), score its `tags`:
  **+1.0** if a (possibly multi-word) tag's tokens are fully contained in the workload tokens,
  **+0.5** if they merely intersect;
- **+0.25 × |title tokens ∩ workload tokens|** as a nudge.

Embedding similarity enters only later, at chunk ranking inside `store.search()` — it plays no
part in choosing artifacts.

### 1.3 Selection and budget

- `_select()` (`router.py:69-76`): rank artifacts by score descending (Python stable sort),
  keep those **strictly above** `relevance_floor`, fall back to the single best-scoring
  artifact when nothing clears the floor (so the pipeline always has grounding), truncate to
  `max_artifacts`.
- `_budget()` (`router.py:78-99`): distribute `total_budget` retrieval slots across the
  selected artifacts **proportional to their classify score** (`max(1, round(share × total))`),
  then trim/pad rounding drift so the budgets sum exactly to `total_budget` (test-pinned).

### 1.4 Partition mechanism (the key finding)

The store (`store.py`) chunks every `grounding/<artifact_id>/*.md` file (heading-aware,
1200 chars, 150 overlap), embeds all chunks into **one flat in-memory list**, and builds a
FAISS `IndexFlatIP` over them (`store.py:108-121`).

**However, the FAISS index is built and then never queried.** `ArtifactStore.search()`
(`store.py:146-171`) performs a pure-Python brute-force cosine over `self._vectors`, applying
an **allow-set post-filter** — `if allowed is not None and chunk.artifact_id not in allowed:
continue` (`store.py:160`) — before taking top-k. "Partitioned by artifact_id" therefore means:
*a single flat store with a per-query allow-set filter*, not per-partition indexes and not
FAISS-side metadata filtering (FAISS `IndexFlatIP` has no native metadata filtering at all).

The router routes by passing `artifact_ids=[aid]` per selected artifact (`router.py:108-111`),
so today's partitioning is **one level deep**: `artifact_id → chunks`.

### 1.5 Provenance format

Two parallel channels (`router.py:114-119, 130-140`):

1. `RetrievalResult.provenance`: an **ordered, de-duplicated list of artifact_ids** that
   actually contributed a retrieved chunk. Flows into `Recommendation.grounded_by`
   (`reason/schema.py:27-28`) and is emitted into the final spec comment (`emit/spec.py`).
2. `RetrievalResult.context_text`: chunk sections joined by `\n\n---\n\n`, each prefixed with
   a header `[artifact:<id> | <repo> | image=<image> | <source_file>]`.

There is **no per-section structured provenance** — attribution below the artifact level (which
section came from which file at which score) exists only inside the header strings.

---

## 2. Verdict: FAISS metadata filtering vs. a partition-descriptor index

**Question:** does FAISS metadata filtering suffice for two-level logical partitions
(site → use-case), or is a partition-descriptor index needed?

**Answer: both halves, for different levels — and neither requires touching FAISS.**

- **Level-2 (chunk retrieval): the existing allow-set post-filter suffices.** FAISS is not in
  the query path and `IndexFlatIP` offers no metadata filtering anyway; the effective mechanism
  is a Python post-filter over chunk metadata. Two-level logical partitions reduce, at query
  time, to *deriving a richer allow-set* (site → use-case → artifact_ids, all computable from
  `ArtifactMeta`) and passing it to the same `store.search()`. At this corpus scale (5
  artifacts, low hundreds of chunks) a brute-force scan plus post-filter is exact, simple, and
  microseconds-cheap. No per-partition indexes, no FAISS changes, no re-chunking.
- **Levels 0-1 (routing decisions) need a partition-descriptor table — not a FAISS index.**
  Choosing a site (and scoring use-cases) requires something to compare the workload against:
  short prose **descriptors per partition**, embedded once with the store's embedder and scored
  by plain dot products. With 4 sites and 3 use-cases this is a dozen vectors — an in-memory
  dict, not an index structure. Building a FAISS index over ~12 descriptor vectors would be
  pure ceremony.

So: **keep the flat store + post-filter for dense search; add a lightweight
partition-descriptor table for the tree's routing levels.**

---

## 3. RouterTree design (implemented in Phase B)

### 3.1 Partition taxonomy

Two new **defaulted** fields on `ArtifactMeta` (backward-compatible): `site` (default
`"CHI@Edge"`) and `use_case` (default `""` ⇒ the artifact is its own use-case).

| site | use_case | artifact_id |
|---|---|---|
| CHI@Edge | access | edge_ssh_image |
| CHI@Edge | peripherals | edge-picamera-image |
| CHI@Edge | peripherals | edge_sensehat_image |
| CHI@Edge | inference | edge-cpu-inference |
| CHI@Edge | inference | serve-edge-chi *(new — benchmark A5, added so 5 of 6 benchmark artifacts are covered)* |

Site descriptors (`advisor/artifacts/tree.py: SITES`) exist for **CHI@Edge, KVM@TACC, CHI@UC,
CHI@TACC** — the last three are descriptor-only (no artifacts), giving the Level-0 gate real
contrast without inventing grounding.

### 3.2 The three levels

- **Level-0 — hard site gate.** New `WorkloadSpec(text, site=None)`; plain strings coerce with
  `site=None`. The gate fires **only when `spec.site` is set**: the declared site must agree
  with the embedding argmax over all site descriptors, else the result comes back with
  `status="needs_clarification"` (plus a human-readable `clarification`) instead of retrieval
  results. Unknown site names and sites with no grounded artifacts also clarify. When
  `spec.site is None`, the branch is chosen by embedding score over **populated** sites only —
  with one populated branch this is deterministic, so **plain-string traffic (CLI,
  advisor_room) can never be gated**.
- **Level-1 — soft use-case routing (top-k).** Use-case score = max classify score over member
  artifacts; use-cases above the relevance floor are kept (ranked, stable), with fallback to
  the best group; an optional `use_case_top_k` truncates. Default `None` = non-restrictive.
- **Level-2 — unchanged dense search.** Selection, budgeting, retrieval, and assembly run
  through the *same* `RetrievalRouter` code (`_select`/`_budget`/`_finish`) restricted to the
  surviving artifact pool.

Budgets remain proportional to score (same `_budget`). Provenance gains a **per-section**
channel: `RetrievalResult.sections` — one `SectionProvenance(index, artifact_id, site,
use_case, source_file, score)` per assembled context section — without altering
`context_text` or the legacy `provenance` list.

### 3.3 Byte-identical guarantee (one populated branch, default knobs)

Every artifact scoring above the floor belongs to a use-case whose max ≥ that score, so its
group survives Level-1 and the artifact reaches the Level-2 pool; `_select` over the pool is
then identical to `_select` over all artifacts (stable ranking, sub-floor artifacts never
selected). In the all-zero fallback case, the best group is the group of the first registry
artifact, whose Level-2 fallback picks exactly flat's `ranked[0][0]`. Everything downstream
(budget → search → assemble) is the same code path (`_finish`). Divergence is possible only
via an explicit `use_case_top_k` — which is precisely the ablation knob.

Pinned by `tests/test_router_tree.py::test_byte_identical_single_branch` (string-equality on
`context_text` plus field equality across six workloads, including the unmatched-workload
fallback).

### 3.4 Compatibility

- `RetrievalResult` grows only **defaulted** fields (`status`, `clarification`, `site`,
  `site_scores`, `selected_use_cases`, `use_case_scores`, `sections`); no consumer
  destructures it positionally, and the flat router leaves them at defaults.
- `RetrievalRouter` is untouched behaviorally (one pure refactor: the tail of `route()` is
  extracted into `_finish()` so the tree can share it). CLI and `advisor_room.py` keep working
  unchanged.
- All 28 pre-existing tests stay green, unmodified.
- **Note for the node deployment:** the grounding corpus gained `grounding/serve-edge-chi/`;
  the deployed node's `GROUNDING_DIR` copy must be re-synced before the advisor there can
  retrieve A5 content (out of scope here).

### 3.5 Ablation (Phase C)

`chi-edge-advisor/tools/ablate_router.py` runs every `benchmark_v4/items/*.yaml` prompt
through both routers and scores whether the item's `target_artifact` lands in top-k at each
level (L0 site, L1 use-case@k, L2 artifact@k, plus chunk-level hits), emitting
**Table A7 (tree vs flat)** to `benchmark_v4/exports/ablation_A7.{md,json}`. Benchmark→router
ID map: A1→edge_ssh_image, A2→edge-picamera-image, A3→edge_sensehat_image, A5→serve-edge-chi,
A6→edge-cpu-inference. **45 of 50 items are covered**: uncovered are the two A4 targets
(bare-metal distractor, no router counterpart) plus three items with an empty
`target_artifact` (N14/N17/N18, designed no-source items) — flagged and excluded from the
aggregates. Default embedder is the deterministic `HashingEmbedder` (reproducible; same one
the unit tests pin), with `--embedder auto` for bge-fidelity numbers.

**Results (2026-07-16, hashing embedder, budget 6):**

| level | tree (`--l1-k 2`) | tree (`--l1-k 3`) | flat |
|---|---|---|---|
| L0 site | 100.0% | 100.0% | n/a |
| L1 use-case | 73.3% @2 | 97.8% @3 | n/a |
| L2 artifact @3 | 68.9% | **86.7%** | **86.7%** |
| chunk-level | 68.9% | **86.7%** | **86.7%** |

At the non-restrictive `--l1-k 3` the tree's L2/chunk hit-rates are *exactly* equal to the
flat router's — the byte-identical parity holds on real benchmark prompts, not just unit
tests. Truncating to the top-2 use-cases costs ~18 points of artifact recall (8 items whose
target's use-case ranks third), which quantifies the routing-aggressiveness trade-off.
