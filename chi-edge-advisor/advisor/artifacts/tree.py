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

import re
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


# How far the embedding argmax must beat a declared site before the
# declaration is challenged. A declaration is the user telling us where they
# want to be; overturning it needs evidence, not a rounding difference.
# Measured on the site descriptors: a genuine disagreement ("boot a vm from a
# flavor" declared as CHI@Edge) scores 0.47 clear, while a canonical edge
# workload the descriptors merely fail to separate ("read temperature humidity
# and pressure from a sensor") loses to KVM@TACC by 0.007. Anything in that
# gap is noise, and gating on it turns a correct declaration into a question.
SITE_GATE_MARGIN = 0.05


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
        #
        # Unscoped, the branches are narrowed to what the index can serve, for
        # the same reason RetrievalRouter narrows its pool: a branch holding
        # artifacts with no chunks routes to them and retrieves nothing. The
        # leaf router has already made that decision, so read it from there
        # rather than deriving it twice and risking the two disagreeing.
        if artifacts is not None:
            self.artifacts = list(artifacts)
        else:
            servable = self._leaf.pool
            self.artifacts = [m for m in ARTIFACTS if m.artifact_id in servable]

        # site name -> member artifacts, preserving registry order. An
        # artifact observed at several sites joins every one of those branches
        # while keeping a single store namespace, so its grounding is chunked
        # and embedded once. Artifacts that observed no site join no branch:
        # filing them under a guess is how you recommend hardware that is not
        # there.
        self.branches: Dict[str, List[ArtifactMeta]] = {}
        for meta in self.artifacts:
            for site in meta.branch_sites():
                self.branches.setdefault(site, []).append(meta)

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

    def _named_site(self, text: str) -> Optional[str]:
        """The site the workload names outright, or None.

        A user who types "CHI@TACC" has not given a hint to be weighed against
        descriptor prose; they have said where they want to be. Measured on the
        benchmark's own items, reading the name beats the embedding argmax
        outright: 134/134 vs 132/134 on the edge suite, 32/32 vs 13/32 on the
        chameleon suite. The embedding stays as the fallback for the 22 edge
        items that name no site at all.

        LAST mention wins, and that is the whole reason to prefer it over the
        first: "convert my CHI@UC script to run on CHI@Edge" names two sites,
        and the destination - the one the user wants code for - is the one they
        finish on. First-mention gets that item wrong.

        Only full canonical names are matched. The short uids (uc, edge, kvm)
        are ordinary substrings of ordinary words and would fire constantly.
        """
        best: Optional[tuple] = None
        for name in self._site_vecs:
            for m in re.finditer(re.escape(name), text, re.IGNORECASE):
                if best is None or m.start() > best[0]:
                    best = (m.start(), name)
        return best[1] if best else None

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
        # What the text says, if it says anything. Outranks the embedding for
        # both the gate and the no-declaration pick.
        named = self._named_site(spec.text)
        if named is not None and named not in self.branches:
            named = None  # named a site we have nothing for; fall back

        if spec.site is not None:
            declared = self._alias.get(spec.site.strip().lower())
            if declared is None:
                known = ", ".join(s.name for s in self.sites)
                return self._clarify(
                    spec, site_scores, f"unknown site {spec.site!r} (known: {known})"
                )
            # Hard gate. The declaration is challenged on evidence only:
            # either the text names a different site outright, or the
            # embedding prefers one by more than SITE_GATE_MARGIN.
            best = named or max(site_scores, key=site_scores.get)
            contradicted = (
                named is not None and named != declared
            ) or (
                named is None
                and site_scores[declared] < site_scores[best] - SITE_GATE_MARGIN
            )
            if contradicted:
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
            if named is not None:
                site = named
            else:
                site, best_score = None, None
                for name in self.branches:
                    s = site_scores.get(name, 0.0)
                    if best_score is None or s > best_score:
                        site, best_score = name, s

        # -- Level-1: use-case soft routing (top-k) ------------------------
        branch = self.branches[site]
        # Scored over the branch, not the registry. Tag weighting is relative
        # to the candidates, and "which of these 26 KVM artifacts" is a
        # different question from "which of these 95".
        branch_pool = {m.artifact_id: m for m in branch}
        scores = self._leaf.classify(spec.text, pool=branch_pool)

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
