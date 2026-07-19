"""RetrievalRouter: classify workload -> select artifacts -> budget -> assemble.

Given a plain-language workload, the router:
  1. classifies the task by scoring each artifact's tags against the workload,
  2. selects the relevant artifact_ids (those clearing a relevance floor),
  3. allocates a per-artifact retrieval budget proportional to relevance,
  4. retrieves chunks per artifact and assembles context WITH provenance
     (exactly which artifact_ids grounded the answer).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .registry import ARTIFACTS_BY_ID
from .store import ArtifactStore, RetrievedChunk

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
    def route(self, workload: str) -> RetrievalResult:
        scores = self.classify(workload)
        selected = self._select(scores)
        budget = self._budget(selected, scores)
        return self._finish(workload, scores, selected, budget)

    def _finish(
        self,
        workload: str,
        scores: Dict[str, float],
        selected: List[str],
        budget: Dict[str, int],
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

        context_text = self._assemble(chunks)
        return RetrievalResult(
            workload=workload,
            task_scores=scores,
            selected_artifact_ids=selected,
            per_artifact_budget=budget,
            chunks=chunks,
            context_text=context_text,
            provenance=provenance,
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
