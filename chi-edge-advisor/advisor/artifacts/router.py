"""RetrievalRouter: classify workload -> select artifacts -> budget -> assemble.

Given a plain-language workload, the router:
  1. classifies the task by scoring each artifact's tags against the workload,
  2. selects the relevant artifact_ids (those clearing a relevance floor),
  3. allocates a per-artifact retrieval budget proportional to relevance,
  4. retrieves chunks per artifact and assembles context WITH provenance
     (exactly which artifact_ids grounded the answer).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .registry import ARTIFACTS_BY_ID
from .store import ArtifactStore, RetrievedChunk

log = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> List[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class SectionProvenance:
    """Structured attribution for one assembled context section (one chunk)."""

    index: int
    artifact_id: str
    site: str
    use_case: str
    source_file: str
    score: float


@dataclass
class RetrievalResult:
    workload: str
    task_scores: Dict[str, float]
    selected_artifact_ids: List[str]
    per_artifact_budget: Dict[str, int]
    chunks: List[RetrievedChunk]
    context_text: str
    # provenance: artifact_ids that actually contributed retrieved chunks.
    provenance: List[str] = field(default_factory=list)
    # RouterTree extensions (defaults keep the flat router's output unchanged).
    status: str = "ok"  # "ok" | "needs_clarification"
    clarification: str = ""
    site: Optional[str] = None
    site_scores: Dict[str, float] = field(default_factory=dict)
    selected_use_cases: List[str] = field(default_factory=list)
    use_case_scores: Dict[str, float] = field(default_factory=dict)
    # per-section provenance, aligned 1:1 with ``chunks``/context sections.
    sections: List[SectionProvenance] = field(default_factory=list)
    # Hardware the selected artifacts actually target, in score order. This is
    # the advisor picking its tags: it lets the availability layer fetch only
    # the sites that carry these types instead of sweeping all of them.
    # Deliberately over-generated (union across every selected artifact, not
    # just the top one), because a type missing here costs a second fetch.
    candidate_machine_types: List[str] = field(default_factory=list)
    candidate_sites: List[str] = field(default_factory=list)


class RetrievalRouter:
    def __init__(
        self,
        store: ArtifactStore,
        total_budget: int = 6,
        max_artifacts: int = 3,
        relevance_floor: float = 0.0,
    ):
        self.store = store
        self.total_budget = total_budget
        self.max_artifacts = max_artifacts
        self.relevance_floor = relevance_floor

    # -- 1. classification ------------------------------------------------
    def classify(self, workload: str) -> Dict[str, float]:
        """Score each artifact by tag/title overlap with the workload."""
        wtokens = set(_tokens(workload))
        scores: Dict[str, float] = {}
        for aid, meta in ARTIFACTS_BY_ID.items():
            score = 0.0
            for tag in meta.tags:
                ttoks = set(_tokens(tag))
                if ttoks & wtokens:
                    # multi-word tag fully present scores higher.
                    score += 1.0 if ttoks <= wtokens else 0.5
            # title words give a small nudge.
            score += 0.25 * len(set(_tokens(meta.title)) & wtokens)
            scores[aid] = score
        return scores

    # -- 2/3. select + budget --------------------------------------------
    def _select(self, scores: Dict[str, float]) -> List[str]:
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        selected = [aid for aid, s in ranked if s > self.relevance_floor]
        if not selected:
            # Nothing matched -> fall back to the single best-scoring artifact
            # so the pipeline always has some grounding.
            selected = [ranked[0][0]] if ranked else []
        return selected[: self.max_artifacts]

    def _budget(self, selected: List[str], scores: Dict[str, float]) -> Dict[str, int]:
        if not selected:
            return {}
        total_score = sum(max(scores[a], 0.0001) for a in selected)
        budget: Dict[str, int] = {}
        remaining = self.total_budget
        for aid in selected:
            share = max(scores[aid], 0.0001) / total_score
            alloc = max(1, round(share * self.total_budget))
            budget[aid] = alloc
            remaining -= alloc
        # Trim/pad rounding drift so budgets sum to total_budget.
        while remaining < 0:
            biggest = max(budget, key=budget.get)
            if budget[biggest] > 1:
                budget[biggest] -= 1
            remaining += 1
        while remaining > 0:
            best = max(selected, key=lambda a: scores[a])
            budget[best] += 1
            remaining -= 1
        return budget

    # -- 4. retrieve + assemble ------------------------------------------
    def _llm_pick(self, workload: str) -> "str | None":
        """Ask a model which artifact matches the user's intent.

        classify() scores by literal word overlap with tags and titles, so it
        cannot connect "I want to work with cameras" to the picamera artifact
        when the words do not line up - it has been observed routing that
        request to the SSH artifact instead. Intent matching is what a model is
        good at, so it is asked directly.

        Returns None when disabled or unreachable, in which case the caller
        keeps the lexical ordering untouched. Off by default so collected
        benchmark runs stay reproducible.
        """
        import json
        import os
        import urllib.request

        if os.environ.get("ADVISOR_LLM_ROUTER", "false").lower() not in {
                "1", "true", "yes", "on"}:
            return None

        catalog = "\n".join(
            "%s: %s%s (tags: %s)" % (
                aid, meta.title,
                " - " + meta.use_case if getattr(meta, "use_case", "") else "",
                ", ".join(meta.tags))
            for aid, meta in ARTIFACTS_BY_ID.items()
        )
        prompt = (
            "Pick the ONE reference artifact that best matches what the user "
            "wants to do.\n\nArtifacts:\n" + catalog +
            "\n\nReply with exactly one artifact id from the list above, or NONE "
            "if none of them fit.\n\nUser request: " + workload
        )
        # Same resolution as rag.py and advisor_room.judge: LLM_* first, TEJAS_*
        # as fallback, then the real gateway. No key default on purpose - a
        # placeholder key turns a missing credential into a silent 401, and this
        # path then falls back to lexical ordering without saying so.
        base = (os.environ.get("LLM_API_BASE") or os.environ.get("TEJAS_BASE_URL")
                or "https://ai.tejas.tacc.utexas.edu/v1").rstrip("/")
        model = (os.environ.get("LLM_MODEL") or os.environ.get("TEJAS_MODEL")
                 or "Meta-Llama-3.3-70B-Instruct")
        key = os.environ.get("LLM_API_KEY") or os.environ.get("TEJAS_API_KEY") or ""
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 16,
        }).encode()
        req = urllib.request.Request(
            base + "/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + key},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                reply = json.load(resp)["choices"][0]["message"]["content"]
        except Exception as err:
            log.warning("llm router unreachable: %s", err)
            return None

        # Scan the whole reply rather than the first token: the model often
        # answers "The best match is edge_ssh_image", and taking token[0] threw
        # the answer away and silently fell back to lexical order. Earliest
        # mentioned id wins. Matching against the registry means a hallucinated
        # name can never enter provenance.
        hits = [(reply.find(aid), aid) for aid in ARTIFACTS_BY_ID if aid in reply]
        return min(hits)[1] if hits else None

    def route(self, workload: str) -> RetrievalResult:
        scores = self.classify(workload)
        picked = self._llm_pick(workload)
        if picked is not None:
            # Lift the intent match above every lexical score so _select ranks it
            # first, while leaving the relative order of the rest intact.
            scores = dict(scores)
            scores[picked] = max(scores.values(), default=0.0) + 1.0
        selected = self._select(scores)
        budget = self._budget(selected, scores)
        return self._finish(workload, scores, selected, budget, prefer=picked)

    def _finish(
        self,
        workload: str,
        scores: Dict[str, float],
        selected: List[str],
        budget: Dict[str, int],
        prefer: Optional[str] = None,
    ) -> RetrievalResult:
        chunks: List[RetrievedChunk] = []
        for aid in selected:
            chunks.extend(
                self.store.search(workload, artifact_ids=[aid], k=budget.get(aid, 1))
            )
        chunks.sort(key=lambda c: c.score, reverse=True)

        provenance = []
        for c in chunks:
            if c.artifact_id not in provenance:
                provenance.append(c.artifact_id)

        # provenance is ordered by chunk similarity, which is not the same as the
        # selection order. The reasoner reads provenance[0], so an intent pick
        # has to be lifted here or it never reaches the recommendation. Done
        # before machine_types is derived below so both stay consistent.
        if prefer and prefer in provenance:
            provenance = [prefer] + [a for a in provenance if a != prefer]

        context_text = self._assemble(chunks)
        # Union over provenance order first (artifacts that actually grounded
        # the answer), then the rest of the selection, so the reasoner's likely
        # pick sorts early while the fallbacks stay in the fetch set.
        types, sites = [], []
        for aid in provenance + [a for a in selected if a not in provenance]:
            meta = ARTIFACTS_BY_ID.get(aid)
            if not meta:
                continue
            for mt in meta.machine_types:
                if mt not in types:
                    types.append(mt)
            if meta.site and meta.site not in sites:
                sites.append(meta.site)

        return RetrievalResult(
            workload=workload,
            task_scores=scores,
            selected_artifact_ids=selected,
            per_artifact_budget=budget,
            chunks=chunks,
            context_text=context_text,
            provenance=provenance,
            candidate_machine_types=types,
            candidate_sites=sites,
        )

    @staticmethod
    def _assemble(chunks: List[RetrievedChunk]) -> str:
        parts: List[str] = []
        for c in chunks:
            meta = ARTIFACTS_BY_ID.get(c.artifact_id)
            header = f"[artifact:{c.artifact_id}"
            if meta:
                header += f" | {meta.repo} | image={meta.image}"
            header += f" | {c.source_file}]"
            parts.append(f"{header}\n{c.text}")
        return "\n\n---\n\n".join(parts)
