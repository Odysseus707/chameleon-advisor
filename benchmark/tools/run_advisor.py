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
import json
import sys
import traceback
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ADVISOR = ROOT.parent / "chi-edge-advisor"
sys.path.insert(0, str(ADVISOR))


def availability_from_snapshot(snapshot: str, captable: dict):
    """The DeviceAvailability list the advisor would have seen in that environment.

    All devices are passed, not just the free ones: `reservable=False` is the
    signal that distinguishes a down device from a busy one, and dropping it
    would hide the trap the suite is built around.
    """
    from advisor.availability.base import DeviceAvailability

    devices = json.loads((ROOT / "snapshots" / f"{snapshot}.json").read_text())["devices"]
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
    """Format a Recommendation as the ranked list the suite grades."""
    picks = [rec.machine_type] + [a for a in (rec.alternatives or [])
                                  if a != rec.machine_type]
    lines = []
    for i, t in enumerate(picks, 1):
        n = free_types.get(t, 0)
        lines.append(f"{i}. {t} - {n} free; {rec.reasoning[:90]}"
                     if i == 1 else f"{i}. {t} - {n} free.")
    if rec.image:
        cfg = [f"image {rec.image}"]
        if rec.device_profiles:
            cfg.append(f"device_profiles={rec.device_profiles}")
        if rec.runtime:
            cfg.append(f'runtime="{rec.runtime}"')
        lines += ["", "Configuration: " + ", ".join(cfg) + "."]
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

    from advisor.artifacts.router import RetrievalRouter  # noqa: E402
    from advisor.artifacts.store import ArtifactStore  # noqa: E402
    from advisor.inventory.catalog import InventoryCache  # noqa: E402
    from advisor.reason.reasoner import Reasoner  # noqa: E402

    items = sorted((ROOT / "items").glob("R*.yaml"))
    if args.limit:
        items = items[:args.limit]

    outdir = ROOT / "runs" / args.condition / args.system
    outdir.mkdir(parents=True, exist_ok=True)

    captable = yaml.safe_load(
        (ROOT / "capability_table.yaml").read_text())["device_types"]
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

    print(f"{len(items)} items -> {outdir.relative_to(ROOT.parent)}")
    print(f"  answered {ok}   errored {err}")
    print("\nScore with:\n  ../.venv/bin/python tools/score_runs.py --suite reservation \\\n"
          "    --csv exports/reservation_scores.csv --md exports/reservation_summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
