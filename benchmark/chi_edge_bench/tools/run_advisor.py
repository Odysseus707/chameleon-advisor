#!/usr/bin/env python3
"""Run the chi-edge-advisor against the reservation suite and record its answers.

This is the system under test, driven offline: no Tejas key, no Ollama, no network.
The advisor's own heuristic reasoner and the recorded snapshot stand in for the live
site, so the run is reproducible and costs nothing.

Availability is served FROM THE ITEM'S OWN SNAPSHOT rather than from Blazar. That is
the entire point of the perturbed environments: an item graded against
edge_pi_blackout must present the advisor with a world in which the Pis are down,
which no live probe can be asked to produce.

The advisor recommends ONE machine_type; the suite asks for a ranked top 3. The
answer is rendered as whatever it actually produced - one line if it offers one
option - rather than padded. A short list is a real property of the system and
should score as one, not be hidden.

Writes only to runs/<condition>/<system>/. The v4 collected answers under
runs/{blind,matched,heldout,uncovered}/ are never touched.

  python tools/run_advisor.py                       # all reservation items
  python tools/run_advisor.py --system s7-advisor   # name the run directory
  python tools/run_advisor.py --limit 5             # smoke test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
from pathlib import Path

import yaml

from chi_edge_bench.paths import (capability_table, items_dir, runs_dir,
                                  snapshots_dir, workspace)


def _attach_advisor() -> None:
    """Make the `advisor` package importable.

    Normally it is an installed dependency (`pip install chi-edge-bench[fork]`).
    In the source repo it is an uninstalled sibling directory, so fall back to
    that - and say so, because a silent fallback here is how you end up unsure
    which advisor produced a run.
    """
    try:
        import advisor  # noqa: F401  PLC0415
        return
    except ImportError:
        pass
    sibling = workspace().parent / "chi-edge-advisor"
    if not sibling.is_dir():
        raise SystemExit(
            "the `advisor` package is not importable and no sibling "
            f"chi-edge-advisor/ exists at {sibling}.\n"
            "Install it with:  pip install 'chi-edge-bench[fork]'")
    print(f"[run_advisor] using uninstalled advisor at {sibling}", file=sys.stderr)
    sys.path.insert(0, str(sibling))



def availability_from_snapshot(snapshot: str, captable: dict):
    """The DeviceAvailability list the advisor would have seen in that environment.

    All devices are passed, not just the free ones: `reservable=False` is the
    signal that distinguishes a down device from a busy one, and dropping it
    would hide the trap the suite is built around.
    """
    _attach_advisor()
    from advisor.availability.base import DeviceAvailability

    devices = json.loads((snapshots_dir() / f"{snapshot}.json").read_text())["devices"]
    out = []
    for d in devices:
        spec = captable.get(d["device_type"], {})
        out.append(DeviceAvailability(
            device_uid=d["uuid"],
            machine_type=d["device_type"],
            site="CHI@Edge",
            architecture=spec.get("architecture"),
            gpu=spec.get("accelerator") == "cuda",
            peripherals=list(spec.get("peripherals") or []),
            free_now=d["status"] == "free",
            reservable=d["reservable"],
        ))
    return out


def render(rec, free_types: dict, note: str = "") -> str:
    """Format a Recommendation as the ranked list the suite grades.

    An empty machine_type is a real answer, not a failure: it is the advisor
    saying nothing on the site satisfies the request. Emitting a ranked list
    anyway would turn a correct abstention into a fabricated recommendation.
    """
    if not rec.machine_type:
        # Two different empty answers, and they must not share a headline.
        # "Nothing can satisfy this" is a claim about the hardware. When the
        # hardware fits and is merely reserved that headline is false, and it is
        # the part that gets graded - the correct answer is that everything
        # suitable is busy. The reasoner signals this by leaving machine_type
        # empty while populating alternatives with the qualifying-but-busy types.
        if rec.alternatives:
            busy = ", ".join(rec.alternatives)
            head = (f"All devices that suit this request are busy right now: {busy}. "
                    "This is an availability limit, not a capability one: the "
                    "hardware exists and fits, it is currently reserved.")
        else:
            head = "Nothing on CHI@Edge can satisfy this request."
        body = [head, "", rec.reasoning.strip()]
        if note:
            body += ["", note]
        return "\n".join(body) + "\n"

    picks = [rec.machine_type] + [a for a in (rec.alternatives or [])
                                  if a != rec.machine_type]
    lines = []
    for i, t in enumerate(picks, 1):
        n = free_types.get(t, 0)
        lines.append(f"{i}. {t} - {n} free." )
    if rec.image:
        cfg = [f"image {rec.image}"]
        if rec.device_profiles:
            cfg.append(f"device_profiles={rec.device_profiles}")
        if rec.runtime:
            cfg.append(f'runtime="{rec.runtime}"')
        lines += ["", "Configuration: " + ", ".join(cfg) + "."]
    # The full reasoning, not a 90-character prefix of it. The coverage caveat
    # and the rejected-type list sit at the end of that string, so truncating
    # dropped exactly the parts that say what the recommendation does NOT cover.
    if rec.reasoning:
        lines += ["", rec.reasoning.strip()]
    if note:
        lines += ["", note]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--system", default="s7-advisor")
    ap.add_argument("--condition", default="reservation")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    # Offline everything. Set before importing advisor config, which reads env once.
    import os
    os.environ.setdefault("ADVISOR_OFFLINE", "1")
    os.environ.setdefault("LLM_PROVIDER", "none")
    os.environ.setdefault("AVAILABILITY_BACKEND", "reference_api")

    from chi_edge_bench.tools import provenance  # noqa: E402
    from advisor.artifacts.router import RetrievalRouter  # noqa: E402
    from advisor.artifacts.store import ArtifactStore  # noqa: E402
    from advisor.inventory.catalog import InventoryCache  # noqa: E402
    from advisor.reason.reasoner import Reasoner  # noqa: E402

    # Which catalogue this arm was collected against. A recommendation is only
    # interpretable next to the hardware facts the advisor had at the time.
    catalog_sha = None
    _cat = Path(__file__).resolve().parents[3] / "chi-edge-advisor/advisor/inventory/catalog.py"
    if _cat.is_file():
        catalog_sha = hashlib.sha256(_cat.read_bytes()).hexdigest()

    items = sorted(items_dir().glob("R*.yaml"))
    if args.limit:
        items = items[:args.limit]

    outdir = runs_dir() / args.condition / args.system
    outdir.mkdir(parents=True, exist_ok=True)

    captable = yaml.safe_load(
        capability_table().read_text())["device_types"]
    store = ArtifactStore().build()
    router = RetrievalRouter(store)
    inventory = InventoryCache().load()
    reasoner = Reasoner()
    print(f"embedder {store.embedder.name}, {store.num_chunks} chunks, "
          f"{len(inventory)} device types")

    ok = err = 0
    for path in items:
        item = yaml.safe_load(path.read_text())
        availability = availability_from_snapshot(item["snapshot"], captable)
        free_types = {}
        for d in availability:
            if d.free_now:
                free_types[d.machine_type] = free_types.get(d.machine_type, 0) + 1
        try:
            retrieval = router.route(item["prompt"])
            rec = reasoner.recommend(item["prompt"], availability, inventory,
                                     retrieval)
            text = render(rec, free_types)
            ok += 1
        except Exception as exc:  # a crash is a result: record it, do not hide it
            text = (f"ADVISOR ERROR: {type(exc).__name__}: {exc}\n\n"
                    + traceback.format_exc(limit=3))
            err += 1
        (outdir / f"{item['id']}.md").write_text(text)
        # Bind the answer to the prompt it answered. run_bench.py has always
        # done this; this tool never did, so every advisor cell was an
        # unmanifested one that could not prove which prompt produced it.
        provenance.record(outdir, item["id"], item["prompt"],
                          system=args.system, condition=args.condition,
                          produced_by=getattr(rec, "produced_by", "heuristic"),
                          advisor_catalog_sha256=catalog_sha)

    print(f"{len(items)} items -> {outdir}")
    print(f"  answered {ok}   errored {err}")
    print("\nScore with:\n  ../.venv/bin/python tools/score_runs.py --suite reservation \\\n"
          "    --csv exports/reservation_scores.csv --md exports/reservation_summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
