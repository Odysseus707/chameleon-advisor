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

from .artifacts.router import RetrievalRouter
from .artifacts.store import ArtifactStore
from .availability.base import get_backend
from .config import settings
from .emit.spec import dry_check, render_spec
from .inventory.catalog import InventoryCache
from .logging_utils import RunLogger
from .reason.reasoner import Reasoner
from .validate.checks import validate_recommendation


def _hr(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def run_pipeline(
    workload: str,
    backend_name: Optional[str] = None,
    hours: Optional[int] = None,
    logger: Optional[RunLogger] = None,
) -> int:
    logger = logger or RunLogger()
    print(f"[run_id={logger.run_id}] workload: {workload!r}")

    # -- RETRIEVE --------------------------------------------------------
    # Runs first, before any network call. Routing reads only the workload
    # string and the artifact registry, so nothing here needs availability;
    # putting it first is what lets it tell READ which hardware to ask about.
    _hr("1. RETRIEVE  (artifact routing + grounding)")
    store = ArtifactStore().build()
    router = RetrievalRouter(store)
    retrieval = router.route(workload)
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
    backend = get_backend(backend_name,
                          machine_types=retrieval.candidate_machine_types)
    print(f"availability backend : {backend.name} "
          f"(reports_live_state={backend.reports_live_state})")
    hc = backend.healthcheck()
    print(f"healthcheck          : {hc}")
    try:
        availability = backend.list_devices()
    except Exception as exc:  # noqa: BLE001
        print(f"availability read failed: {exc}")
        availability = []
    inventory = InventoryCache().load()
    print(f"live devices seen    : {len(availability)}")
    print(f"inventory device types: {len(inventory)} types across "
          f"{len({s for d in inventory for s in d.sites})} sites")
    logger.log(
        "read",
        workload=workload,
        backend=backend.name,
        reports_live_state=backend.reports_live_state,
        healthcheck=hc,
        availability=[asdict(a) for a in availability],
        inventory=[asdict(d) for d in inventory],
    )

    # -- REASON ----------------------------------------------------------
    _hr("3. REASON  (LLM recommendation)")
    reasoner = Reasoner()
    rec = reasoner.recommend(workload, availability, inventory, retrieval)

    # The reasoner is not bound to the candidate set, and the LLM path in
    # particular can name a type we never fetched. Leaving that alone makes
    # checks.py find zero devices of that type and fail device_free_in_window,
    # turning a good recommendation into a silent exit 1. One extra targeted
    # fetch is the cheaper error.
    if rec.machine_type and not any(
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
    args = ap.parse_args(argv)
    return run_pipeline(args.workload, backend_name=args.backend, hours=args.hours)


if __name__ == "__main__":
    sys.exit(main())
