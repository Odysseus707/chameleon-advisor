"""chi-edge-advisor CLI.

One command: given a plain-language workload, run the full pipeline
    read (availability + inventory) -> retrieve -> reason -> validate -> emit
printing each stage and logging everything to JSONL for later grading.

Usage:
    python -m advisor.cli "take a photo with the pi camera every 10 minutes"
    python -m advisor.cli "SSH into an edge device" --backend blazar --hours 6
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from typing import List, Optional

from .artifacts.registry import ARTIFACTS_BY_ID
from .artifacts.store import ArtifactStore
from .artifacts.tree import RouterTree, WorkloadSpec
from .availability.base import get_backend
from .config import settings
from .emit.spec import dry_check, render_spec
from .inventory.catalog import InventoryCache
from .logging_utils import RunLogger
from .reason.reasoner import Reasoner
from .select.ladder import Request, select, to_recommendation
from .select.crosscheck import crosscheck
from .select.intuition import IntuitionStore
from .select.specs import infer_requirements
from .validate.checks import validate_recommendation


def _family_for(retrieval) -> str:
    """Which python-chi grammar this site needs.

    Taken from the artifacts the router actually landed on, falling back to
    the site name. Guessing it at emit time is how you render a spec that
    fails at submission: the three families are different grammars, not
    variations on one.
    """
    for aid in list(retrieval.provenance) + list(retrieval.selected_artifact_ids):
        meta = ARTIFACTS_BY_ID.get(aid)
        if meta:
            return meta.api_family
    site = (retrieval.site or "").upper()
    if site.startswith("KVM@"):
        return "kvm"
    return "edge" if site == "CHI@EDGE" else "baremetal"


def _hr(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def run_pipeline(
    workload: str,
    backend_name: Optional[str] = None,
    hours: Optional[int] = None,
    logger: Optional[RunLogger] = None,
    site: Optional[str] = None,
    count: int = 1,
    requires: Optional[dict] = None,
    availability_override: Optional[List] = None,
    intuition_path: Optional[str] = None,
) -> int:
    """Run the pipeline once.

    ``availability_override`` is the injection point for reproducible runs: the
    benchmark passes snapshot-backed state in rather than the advisor
    inspecting who called it and behaving differently. Live is the default and
    the only other mode; there is no third behaviour hiding behind a caller
    check.
    """
    logger = logger or RunLogger()
    print(f"[run_id={logger.run_id}] workload: {workload!r}")

    # -- RETRIEVE --------------------------------------------------------
    # Runs first, before any network call. Routing reads only the workload
    # string and the artifact registry, so nothing here needs availability;
    # putting it first is what lets it tell READ which hardware to ask about.
    _hr("1. RETRIEVE  (artifact routing + grounding)")
    store = ArtifactStore().build()
    # RouterTree, not the flat router: with four populated site branches the
    # flat router competes all 95 artifacts for every query, which measured a
    # 26-point drop in edge retrieval. The tree scores one branch at a time.
    router = RouterTree(store)
    retrieval = router.route(WorkloadSpec(text=workload, site=site))
    if retrieval.status != "ok":
        print(f"\nNeeds clarification: {retrieval.clarification}")
        logger.log("retrieve", status=retrieval.status,
                   clarification=retrieval.clarification,
                   site_scores=retrieval.site_scores)
        return 2
    print(f"embedder             : {store.embedder.name} ({store.num_chunks} chunks)")
    print(f"task scores          : "
          f"{ {k: round(v, 2) for k, v in retrieval.task_scores.items()} }")
    print(f"selected artifacts   : {retrieval.selected_artifact_ids}")
    print(f"per-artifact budget  : {retrieval.per_artifact_budget}")
    print(f"provenance           : {retrieval.provenance}")
    print(f"candidate hardware   : {retrieval.candidate_machine_types}")
    logger.log(
        "retrieve",
        task_scores=retrieval.task_scores,
        selected_artifact_ids=retrieval.selected_artifact_ids,
        per_artifact_budget=retrieval.per_artifact_budget,
        provenance=retrieval.provenance,
        candidate_machine_types=retrieval.candidate_machine_types,
        candidate_sites=retrieval.candidate_sites,
        num_chunks=len(retrieval.chunks),
    )

    # -- READ: availability + inventory ----------------------------------
    # Scoped to the candidate hardware, so only the sites that can host it get
    # contacted. Blazar cannot filter server-side, so this site pruning is the
    # whole saving: ~7s instead of ~44s for a single-site type.
    _hr("2. READ  (availability + static inventory)")
    # No backend at all when state is injected. Building one anyway made the
    # injection path depend on credentials it never uses - the benchmark's
    # whole reason for injecting is that it must run offline and reproducibly,
    # and a constructor that reaches for a Blazar endpoint defeats it.
    backend = None
    hc = {"backend": "none", "reachable": None}
    if availability_override is None:
        backend = get_backend(backend_name,
                              machine_types=retrieval.candidate_machine_types)
        print(f"availability backend : {backend.name} "
              f"(reports_live_state={backend.reports_live_state})")
        hc = backend.healthcheck()
        print(f"healthcheck          : {hc}")

    if availability_override is not None:
        availability = list(availability_override)
        avail_mode = "injected"
    else:
        avail_mode = "live"
        try:
            availability = backend.list_devices()
        except Exception as exc:  # noqa: BLE001
            print(f"availability read failed: {exc}")
            availability = []
    # A number produced against live state and one produced against a pinned
    # snapshot are not the same measurement and must never share a column.
    print(f"availability mode    : {avail_mode}")
    inventory = InventoryCache().load()
    print(f"live devices seen    : {len(availability)}")
    print(f"inventory device types: {len(inventory)} types across "
          f"{len({s for d in inventory for s in d.sites})} sites")
    logger.log(
        "read",
        workload=workload,
        backend=(backend.name if backend else "injected"),
        reports_live_state=(backend.reports_live_state if backend else False),
        healthcheck=hc,
        availability_mode=avail_mode,
        availability=[asdict(a) for a in availability],
        inventory=[asdict(d) for d in inventory],
    )

    # -- REASON / SELECT --------------------------------------------------
    # Dispatch on the resolved family. Bare metal and KVM go through the
    # deterministic ladder; CHI@Edge keeps the reasoner path byte-for-byte,
    # because its routing and its answers are already collected and published.
    family = _family_for(retrieval)
    if family in {"baremetal", "kvm"}:
        _hr("3. SELECT  (deterministic ladder)")
        # Work out what the job needs when the caller did not say. An
        # explicit `requires` still wins outright: the benchmark passes one and
        # inferring over the top would change what it measures.
        if requires:
            spec = None
            hard, soft, assumed = dict(requires), {}, []
        else:
            # Opt-in, by path. Nothing is discovered: an advisor that quietly
            # accumulates memory between runs stops being reproducible, which
            # is the same reason availability is injected rather than sniffed.
            memory = IntuitionStore.load(intuition_path) if intuition_path else None
            spec = infer_requirements(workload, intuition=memory)
            hard, soft, assumed = spec.hard(), spec.soft(), spec.assumptions
            if spec.count and count == 1:
                count = spec.count
            print(f"inferred requirement : {spec.describe()}")
            for a in assumed:
                print(f"  assumption         : {a}")
            if soft:
                print(f"  ranking only (not a filter): {sorted(soft)}")
            if memory is not None:
                memory.save(intuition_path)
                print(f"  intuition store      : {len(memory)} entries "
                      f"-> {intuition_path}")
        request = Request(site=retrieval.site, count=count,
                          hours=hours or 3, requires=hard, soft_requires=soft,
                          assumptions=assumed, api_family=family)
        result = select(inventory, availability, request)
        rec = to_recommendation(result, request,
                                grounded_by=list(retrieval.provenance))
        print(f"rung                 : {result.rung.name}"
              f"  (expansions={result.rung.expansions}, "
              f"considered={result.rung.considered})")
        if result.rung.wait_hours:
            print(f"wait                 : {result.rung.wait_hours:.1f}h")
        print(f"ranked               : "
              f"{[(c.machine_type, c.free) for c in result.ranked[:5]]}")
        if result.rejected:
            print(f"rejected             : "
                  f"{[(c.machine_type, c.reject_reason) for c in result.rejected[:4]]}")
        # What the corpus makes of the pick. A note, never a veto: it fires
        # only when a comparable artifact used materially different hardware,
        # and stays silent when the corpus simply has nothing to say - which
        # is the common case, since 18 of the 29 node types are named by no
        # artifact at all.
        xc = crosscheck(workload, rec.machine_type, inventory) if rec.machine_type \
            else None
        if xc is not None and xc.fired:
            print(f"corpus check         : {xc.kind}")
            print(f"  {xc.note}")
            rec.assumptions.append(xc.note)
        elif xc is not None and not xc.had_evidence and rec.machine_type:
            print("corpus check         : no comparable artifact — the corpus "
                  "is silent on this, which is neither agreement nor doubt")
        logger.log("select", rung=result.rung.name,
                   crosscheck_kind=(xc.kind if xc else ""),
                   crosscheck_evidence=([] if xc is None else xc.comparable),
                   requires=hard, soft_requires=soft, assumptions=assumed,
                   requirement_origin=(spec.origin if spec else
                                       {k: "explicit" for k in hard}),
                   expansions=result.rung.expansions,
                   wait_hours=result.rung.wait_hours,
                   ranked=[c.machine_type for c in result.ranked],
                   rejected={c.machine_type: c.reject_reason
                             for c in result.rejected})
    else:
        _hr("3. REASON  (LLM recommendation)")
        reasoner = Reasoner()
        # Only the hardware that could actually serve this family. Handing the
        # edge reasoner the whole 36-type catalog made it reject every
        # bare-metal type by name inside a CHI@Edge answer.
        rec = reasoner.recommend(
            workload, availability,
            [d for d in inventory if d.api_family == family], retrieval)

    # The reasoner is not bound to the candidate set, and the LLM path in
    # particular can name a type we never fetched. Leaving that alone makes
    # checks.py find zero devices of that type and fail device_free_in_window,
    # turning a good recommendation into a silent exit 1. One extra targeted
    # fetch is the cheaper error.
    if backend is not None and family == "edge" and rec.machine_type and not any(
            a.machine_type == rec.machine_type for a in availability):
        try:
            rescued = backend.list_devices(machine_type=rec.machine_type)
        except Exception as exc:  # noqa: BLE001
            rescued = []
            print(f"re-fetch for {rec.machine_type!r} failed: {exc}")
        if rescued:
            print(f"re-fetched {len(rescued)} {rec.machine_type} device(s) "
                  f"outside the candidate set")
            availability = list(availability) + rescued
    if hours:
        rec.duration_hours = hours
    print(f"produced_by          : {rec.produced_by}")
    print(f"machine_type         : {rec.machine_type}  (count={rec.count}, "
          f"{rec.duration_hours}h, arch={rec.architecture}, gpu={rec.gpu})")
    print(f"device_name          : {rec.device_name}")
    print(f"image                : {rec.image}")
    print(f"device_profiles      : {rec.device_profiles}  runtime={rec.runtime}")
    print(f"reasoning            : {rec.reasoning}")
    logger.log("reason", recommendation=asdict(rec))

    # -- VALIDATE --------------------------------------------------------
    _hr("4. VALIDATE  (CHI@Edge trap checks)")
    report = validate_recommendation(rec, inventory, availability)
    for c in report.checks:
        mark = "PASS" if c.passed else ("WARN" if c.severity == "warning" else "FAIL")
        print(f"  [{mark}] {c.name}: {c.detail}")
    print(f"overall              : {'PASS' if report.passed else 'FAIL'}")
    logger.log("validate", **report.as_dict())

    # -- EMIT ------------------------------------------------------------
    _hr("5. EMIT  (python-chi lease spec)")
    spec = render_spec(rec)
    check = dry_check(rec)
    print(spec)
    print(f"dry-check ({check.mode}): {'PASS' if check.passed else 'FAIL'}")
    for d in check.details:
        print(f"  - {d}")
    logger.log("emit", spec=spec, dry_check=asdict(check))

    print(f"\n[logged run_id={logger.run_id} -> {logger.log_path}]")
    return 0 if report.passed and check.passed else 1


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="chi-edge-advisor",
        description="Allocation-aware CHI@Edge resource advisor.",
    )
    ap.add_argument("workload", help="plain-language description of the workload")
    ap.add_argument(
        "--backend",
        choices=["reference_api", "blazar"],
        default=None,
        help="availability backend (default: from AVAILABILITY_BACKEND / config)",
    )
    ap.add_argument("--hours", type=int, default=None, help="override lease duration")
    ap.add_argument("--site", default=None,
                    help="declare the target site (CHI@UC, CHI@TACC, KVM@TACC, CHI@Edge)")
    ap.add_argument("--count", type=int, default=1, help="how many nodes")
    ap.add_argument("--intuition", default=None,
                    help="path to a learned-intuition store (opt-in; omit to "
                         "run stateless)")
    args = ap.parse_args(argv)
    return run_pipeline(args.workload, backend_name=args.backend,
                        hours=args.hours, site=args.site, count=args.count,
                        intuition_path=args.intuition)


if __name__ == "__main__":
    sys.exit(main())
