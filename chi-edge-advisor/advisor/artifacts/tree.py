"""RouterTree: hierarchical retrieval routing (site -> use-case -> chunks).

Level-0  hard site gate: when a WorkloadSpec declares a site, the declaration
         must agree with the embedding argmax over site descriptors, else the
         result comes back with status="needs_clarification".
Level-1  soft use-case routing: use-cases are scored by the max classify score
         of their member artifacts; those above the relevance floor survive
         (optionally truncated to ``use_case_top_k``).
Level-2  unchanged dense search: selection, budgeting, retrieval and assembly
         are delegated to the flat RetrievalRouter restricted to the surviving
         artifact pool, so a tree with one populated branch and default knobs
         produces byte-identical output to the flat router.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from .registry import ARTIFACTS, ArtifactMeta
from .router import RetrievalResult, RetrievalRouter, SectionProvenance
from .store import ArtifactStore, _dot


@dataclass
class WorkloadSpec:
    """Structured workload: free text plus an optional declared site."""

    text: str
    site: Optional[str] = None

    @classmethod
    def coerce(cls, workload: Union[str, "WorkloadSpec"]) -> "WorkloadSpec":
        if isinstance(workload, WorkloadSpec):
            return workload
        if isinstance(workload, str):
            return cls(text=workload)
        raise TypeError(f"workload must be str or WorkloadSpec, got {type(workload)!r}")


@dataclass
class SiteDescriptor:
    """A routable Chameleon site with prose embedded for Level-0 scoring."""

    name: str  # canonical, e.g. "CHI@Edge"
    uid: str  # short alias, e.g. "edge"
    description: str


SITES: List[SiteDescriptor] = [
    SiteDescriptor(
        name="CHI@Edge",
        uid="edge",
        description=(
            "CHI@Edge runs containers on small edge devices: reserve a raspberry "
            "pi or jetson device, launch a container image on the device, attach "
            "peripherals such as a camera or sense hat sensors over gpio, capture "
            "photos, read temperature, ssh into the container, and run on-device "
            "machine learning inference at the edge."
        ),
    ),
    SiteDescriptor(
        name="KVM@TACC",
        uid="kvm",
        description=(
            "KVM@TACC provides virtual machines: launch a vm instance from a "
            "flavor with kvm virtualization, boot cloud server instances, resize "
            "flavors, and manage virtual machine images without reserving "
            "physical hardware."
        ),
    ),
    SiteDescriptor(
        name="CHI@UC",
        uid="uc",
        description=(
            "CHI@UC provides bare metal nodes in Chicago: reserve physical hosts "
            "by node type, provision an operating system image directly onto "
            "bare metal server hardware."
        ),
    ),
    SiteDescriptor(
        name="CHI@TACC",
        uid="tacc",
        description=(
            "CHI@TACC provides bare metal nodes in Texas: reserve physical gpu "
            "or cpu hosts by node type, provision images onto dedicated bare "
            "metal server hardware."
        ),
    ),
]


class RouterTree:
    """Two-level logical partition router over the flat artifact store."""

    def __init__(
        self,
        store: ArtifactStore,
        total_budget: int = 6,
        max_artifacts: int = 3,
        relevance_floor: float = 0.0,
        use_case_top_k: Optional[int] = None,
        sites: Optional[List[SiteDescriptor]] = None,
        artifacts: Optional[List[ArtifactMeta]] = None,
    ):
        self.store = store
        self.relevance_floor = relevance_floor
        self.use_case_top_k = use_case_top_k
        self._leaf = RetrievalRouter(
            store,
            total_budget=total_budget,
            max_artifacts=max_artifacts,
            relevance_floor=relevance_floor,
        )
        self.total_budget = self._leaf.total_budget
        self.max_artifacts = self._leaf.max_artifacts

        self.sites = list(sites or SITES)
        # NOTE: artifacts must exist in the global registry (classify() scores
        # against ARTIFACTS_BY_ID); this list only shapes the tree's branches.
        self.artifacts = list(ARTIFACTS if artifacts is None else artifacts)

        # site name -> member artifacts, preserving registry order.
        self.branches: Dict[str, List[ArtifactMeta]] = {}
        for meta in self.artifacts:
            self.branches.setdefault(meta.site, []).append(meta)

        # case-insensitive name/uid aliases -> canonical site name.
        self._alias: Dict[str, str] = {}
        for s in self.sites:
            self._alias[s.name.lower()] = s.name
            if s.uid:
                self._alias[s.uid.lower()] = s.name

        # partition-descriptor table: one embedded vector per site.
        vecs = self.store.embedder.embed([s.description for s in self.sites])
        self._site_vecs: Dict[str, List[float]] = {
            s.name: v for s, v in zip(self.sites, vecs)
        }

    # -- Level-0: site gate ------------------------------------------------
    def _site_scores(self, text: str) -> Dict[str, float]:
        qvec = self.store.embedder.embed([text])[0]
        return {name: _dot(qvec, vec) for name, vec in self._site_vecs.items()}

    def _clarify(
        self, spec: WorkloadSpec, site_scores: Dict[str, float], reason: str
    ) -> RetrievalResult:
        return RetrievalResult(
            workload=spec.text,
            task_scores={},
            selected_artifact_ids=[],
            per_artifact_budget={},
            chunks=[],
            context_text="",
            provenance=[],
            status="needs_clarification",
            clarification=reason,
            site_scores=site_scores,
        )

    # -- route ---------------------------------------------------------------
    def route(self, workload: Union[str, WorkloadSpec]) -> RetrievalResult:
        spec = WorkloadSpec.coerce(workload)
        site_scores = self._site_scores(spec.text)

        if spec.site is not None:
            declared = self._alias.get(spec.site.strip().lower())
            if declared is None:
                known = ", ".join(s.name for s in self.sites)
                return self._clarify(
                    spec, site_scores, f"unknown site {spec.site!r} (known: {known})"
                )
            best = max(site_scores, key=site_scores.get)
            # Hard gate: the declared site must match the embedding argmax
            # (ties resolve in favor of the declaration).
            if site_scores[declared] < site_scores[best] - 1e-12:
                return self._clarify(
                    spec,
                    site_scores,
                    f"workload reads like {best} "
                    f"(score {site_scores[best]:.3f} vs {site_scores[declared]:.3f} "
                    f"for declared {declared}); please confirm the target site",
                )
            site = declared
            if site not in self.branches:
                return self._clarify(
                    spec, site_scores, f"no grounded artifacts for site {site}"
                )
        else:
            # No declaration -> never gate; pick the best *populated* branch.
            if not self.branches:
                return self._clarify(
                    spec, site_scores, "router tree has no grounded artifacts"
                )
            site, best_score = None, None
            for name in self.branches:
                s = site_scores.get(name, 0.0)
                if best_score is None or s > best_score:
                    site, best_score = name, s

        # -- Level-1: use-case soft routing (top-k) ------------------------
        branch = self.branches[site]
        all_scores = self._leaf.classify(spec.text)
        scores = {m.artifact_id: all_scores[m.artifact_id] for m in branch}

        members: Dict[str, List[str]] = {}
        for m in branch:  # group order = first appearance in registry order
            uc = m.use_case or m.artifact_id
            members.setdefault(uc, []).append(m.artifact_id)
        uc_scores = {uc: max(scores[a] for a in aids) for uc, aids in members.items()}

        ranked = sorted(uc_scores.items(), key=lambda kv: kv[1], reverse=True)
        selected_ucs = [uc for uc, s in ranked if s > self.relevance_floor]
        if not selected_ucs and ranked:
            selected_ucs = [ranked[0][0]]
        if self.use_case_top_k is not None:
            selected_ucs = selected_ucs[: self.use_case_top_k]

        # -- Level-2: unchanged dense search over the surviving pool -------
        keep = set(selected_ucs)
        pool = [m.artifact_id for m in branch if (m.use_case or m.artifact_id) in keep]
        selected = self._leaf._select({aid: scores[aid] for aid in pool})
        budget = self._leaf._budget(selected, scores)
        result = self._leaf._finish(spec.text, scores, selected, budget)

        uc_by_aid = {m.artifact_id: (m.use_case or m.artifact_id) for m in branch}
        result.site = site
        result.site_scores = site_scores
        result.use_case_scores = uc_scores
        result.selected_use_cases = selected_ucs
        result.sections = [
            SectionProvenance(
                index=i,
                artifact_id=c.artifact_id,
                site=site,
                use_case=uc_by_aid.get(c.artifact_id, c.artifact_id),
                source_file=c.source_file,
                score=c.score,
            )
            for i, c in enumerate(result.chunks)
        ]
        return result
