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


def chameleon_availability(item: dict):
    """DeviceAvailability for a bare-metal item, from its own pinned snapshot.

    A separate function from the edge one on purpose. The two wings' snapshots
    do not share a schema - edge records `uuid`/`device_type`, bare metal
    records `uid`/`node_type`/`device_name` - and folding them together behind
    conditionals would make it easy to read one wing's field off the other's
    file and never notice.

    The site comes from the ITEM. Hardcoding CHI@Edge here (which the edge path
    does, correctly, for itself) would make the ladder's site filter reject
    every bare-metal candidate and turn every answer into a refusal.
    """
    _attach_advisor()
    from advisor.availability.base import DeviceAvailability

    devices = json.loads(
        (snapshots_dir() / f"{item['snapshot']}.json").read_text())["devices"]
    return [DeviceAvailability(
        device_uid=d["uid"],
        device_name=d.get("device_name"),
        machine_type=d["node_type"],
        site=item["site"],
        free_now=d["status"] == "free",
        reservable=d["reservable"],
        next_free_window=d.get("next_free_utc"),
        available_hours=d.get("available_hours"),
        source="snapshot",
        live_state_known=True,
    ) for d in devices]


def snapshot_now(snapshot: str):
    """The instant a snapshot was recorded, to be used as the ladder's "now".

    Blazar reports WHEN a host next frees, so a wait is a subtraction and the
    thing subtracted has to be the moment the state was observed. Against the
    wall clock instead, every wait in these pinned snapshots shrinks by a day
    each day, and the 24-hour horizon that separates the `future` rung from
    `infeasible_busy` gets crossed by the calendar. Two runs of one arm a week
    apart were not comparable and nothing said so.

    None when the snapshot carries no `recorded` stamp: the ladder then falls
    back to the wall clock, which is the old behaviour and the right one for a
    live probe.
    """
    from datetime import datetime

    meta = json.loads(
        (snapshots_dir() / f"{snapshot}.json").read_text()).get("_meta") or {}
    stamp = meta.get("recorded")
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None


def render_chameleon(result, snapshot: str, count: int = 1) -> str:
    """The ranked list the reservation suite grades, or a refusal.

    Leads with the state of play before the list. When nothing is free the
    headline says so first and the wait second: an answer that opens with a
    node type reads as "reserve this now", which is false when the honest
    claim is "this is the earliest thing available, in nine hours".

    TWO SEPARATIONS THIS FUNCTION EXISTS TO GET RIGHT.

    Capability-feasible is not the same as reservable. A type that fits the
    requirement but has zero free hosts belongs under "not recommended", with
    the count that makes it so - listing it as "also feasible" invites the
    reader to reserve something they cannot have, and it is the one mistake
    the ranked-list checkers are built to catch.

    And when nothing is free, the list is ordered by WHEN, not by how good.
    Ranking by capability there produced an answer whose headline said "the
    earliest option is in about 1.5 hours" above a rank 1 that was 34 hours
    out: both facts true, the pair of them incoherent.
    """
    lines = []
    rung = result.rung.name
    # Reservable right now, in the ladder's order (free desc, then capability).
    have = [c for c in result.ranked if c.free >= count]
    # Capability-feasible but not enough free hosts. Ordered by when they come
    # back, soonest first; a type that never assembles enough sorts last.
    lack = sorted((c for c in result.ranked if c.free < count),
                  key=lambda c: (c.next_free_hours is None,
                                 c.next_free_hours or 0.0))
    listed = have if have else lack

    if rung == "infeasible_capability":
        lines.append(f"Nothing at {result.site} can satisfy this request.")
        lines.append("")
        lines.append(result.rung.detail + ".")
    elif rung == "unknown_availability":
        lines.append(f"Cannot say for {result.site}: no availability data.")
        lines.append("")
        lines.append(result.rung.detail)
    elif rung == "infeasible_busy":
        lines.append(f"Nothing is free at {result.site} right now, and nothing "
                     "frees up within 24 hours.")
        lines.append("")
        lines.append("This is an availability limit, not a capability one: "
                     "the hardware below fits the request and is simply "
                     "reserved. " + result.rung.detail + ".")
    elif rung == "no_host_state":
        # KVM reserves flavors, not hosts. Falling through to the branch below
        # printed "Available now at KVM@TACC:" over a host tally that means
        # nothing here - a false availability claim, stated in the one format
        # the reader is most likely to act on.
        lines.append(f"No host-level answer applies at {result.site}.")
        lines.append("")
        lines.append(result.rung.detail + ".")
    elif rung == "future":
        # Nothing is reservable now, so nothing goes in a numbered list. A
        # numbered list IS the recommendation - putting a zero-free type in
        # one tells the reader to reserve something that does not exist to be
        # reserved, however carefully the surrounding prose hedges. The wait
        # is real information and it is given as prose.
        soonest = listed[0] if listed else None
        lines.append(f"Nothing is free at {result.site} right now, so there is "
                     f"nothing to reserve at this moment.")
        lines.append("")
        if soonest is not None:
            lines.append(
                f"The earliest option is {soonest.machine_type}, in about "
                f"{result.rung.wait_hours:.1f} hours "
                f"({soonest.free} of {soonest.total} free now). Others follow: "
                + ", ".join(f"{c.machine_type} in {c.next_free_hours:.1f}h"
                            for c in listed[1:4] if c.next_free_hours) + ".")
            lines.append("")
            lines.append("Those times are lower bounds: Blazar reports when a "
                         "host next becomes free, not that it stays free.")
    else:
        lines.append(f"Available now at {result.site}:")
        lines.append("")
        for i, c in enumerate(listed[:3], 1):
            bits = [f"{c.free} of {c.total} free"]
            if c.next_free_hours:
                bits.append(f"next free in {c.next_free_hours:.1f}h")
            lines.append(f"{i}. {c.machine_type} - " + "; ".join(bits) + ".")
        # WHY they qualify, not just that they are free. A list of free counts
        # answers "what is idle"; the question was "what can run my job", and
        # RB18 is the item where a model handed the first refused to read it as
        # the second.
        seen, reasons = set(), []
        for c in listed[:3]:
            if c.accept_reason and c.accept_reason not in seen:
                seen.add(c.accept_reason)
                reasons.append((c.machine_type, c.accept_reason))
        if len(reasons) == 1:
            lines.append("")
            lines.append(f"Why these qualify: {reasons[0][1]}.")
        elif reasons:
            lines.append("")
            lines.append("Why these qualify:")
            for name, why in reasons:
                lines.append(f"  {name}: {why}.")
        if result.chosen and result.chosen.example_host:
            lines.append("")
            lines.append(f"Verified free host: {result.chosen.example_host}.")

    if rung == "free_now":
        others = [c.machine_type for c in listed[3:]]
        if others:
            lines += ["", "Also feasible, lower ranked: " + ", ".join(others) + "."]

    # Coverage, stated. 18 of the 29 bare-metal types are named by no artifact
    # in the corpus at all, so a recommendation for one of them rests on the
    # capability table and nothing else. That is a real limit on how far the
    # answer is grounded and the reader is entitled to it - especially here,
    # where the hardware facts are hand-authored rather than measured.
    shown = listed[:3] if listed else result.ranked[:3]
    uncovered = [c.machine_type for c in shown if not c.covered_by]
    if uncovered:
        lines += ["", "Coverage: no Trovi artifact in the corpus documents "
                  + ", ".join(uncovered) + ". The hardware facts above come "
                  "from the capability table, not from a worked example, so "
                  "there is no validated image or notebook to copy for them."]
    elif not result.requirement_grounded:
        # Said only when TRUE. Hardware meeting this requirement may be
        # perfectly well documented and merely busy - claiming otherwise to
        # sound suitably cautious would be a fabricated limitation, which is
        # its own kind of wrong answer.
        if result.requirement_types:
            lines += ["", "Coverage: no Trovi artifact in the corpus documents "
                      + ", ".join(sorted(result.requirement_types))
                      + ", the only hardware on this testbed that meets the "
                      "requirement. There is no worked example to follow."]
        else:
            lines += ["", "Coverage: no hardware anywhere on this testbed meets "
                      "the requirement, and no Trovi artifact in the corpus "
                      "demonstrates it. This is not documented."]

    # Everything the answer is declining, and why. Two different reasons, kept
    # apart: the hardware cannot do the job, or it can and is not free.
    declined = [(c.machine_type, c.reject_reason) for c in result.rejected]
    if have:
        declined += [(c.machine_type,
                      f"{c.free} of {c.total} free, need {count}") for c in lack]
    if declined:
        # PROSE, not bullets, and this is deliberate. As a "- {type}: {why}"
        # list the model copied it into its own answer above its own rejection
        # heading, where the rank-line pattern read it as a recommendation:
        # forbidden_types_listed 23/32 and no_down_types_listed 25/32 against
        # rank1_feasible 20/21 on the same arm. The content was right and the
        # shape was contagious.
        lines += ["", "Not recommended (do not repeat this list as a "
                      "recommendation): "
                  + "; ".join(f"{name} because {why}" for name, why in declined)
                  + "."]

    # Which mode produced this. A number from live state and a number from a
    # pinned snapshot are not the same measurement and must not sit in the
    # same column unlabelled.
    lines += ["", f"[selection_rung={rung}; availability=snapshot:{snapshot}; "
                  f"expansions={result.rung.expansions}]"]
    return "\n".join(lines) + "\n"


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
    ap.add_argument("--wing", default="chi_edge_bench",
                    choices=["chi_edge_bench", "chameleon_bench"],
                    help="which wing's items to answer (default: the edge wing)")
    args = ap.parse_args()

    # P2: the wing is process state. A run that forgets to set it resolves
    # snapshots and the capability table to the EDGE wing and then grades
    # bare-metal answers against CHI@Edge hardware. Set explicitly, always,
    # even for the default - an implicit default is exactly what makes the
    # mistake invisible.
    from chi_edge_bench import paths
    paths.set_wing(args.wing)

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

    chameleon = args.wing == "chameleon_bench"
    items = sorted(items_dir().glob("RB*.yaml" if chameleon else "R*.yaml"))
    if args.limit:
        items = items[:args.limit]
    if not items:
        # P5: an empty run reports "0 answered" and exits 0. There is no
        # reading of "the advisor answered nothing" that is a result.
        print(f"ERROR: no items matched under {items_dir()}", file=sys.stderr)
        return 2

    outdir = runs_dir() / args.condition / args.system
    outdir.mkdir(parents=True, exist_ok=True)

    inventory = InventoryCache().load()
    edge_inventory = [d for d in inventory if d.api_family == "edge"]
    if chameleon:
        # The bare-metal table's top-level key is `node_types`; the edge
        # wing's is `device_types`. Reading the wrong one is a KeyError at
        # best, and at worst grades one wing's answers against the other's
        # hardware, which is precisely what set_wing above exists to prevent.
        from advisor.select.ladder import Request, select
        captable = yaml.safe_load(capability_table().read_text())["node_types"]
        print(f"chameleon wing: {len(items)} items, {len(captable)} node types, "
              f"{len(inventory)} catalog entries")
    else:
        captable = yaml.safe_load(capability_table().read_text())["device_types"]
    store = ArtifactStore().build()
    # SCOPED TO THE EDGE POOL. The registry now holds 95 artifacts across four
    # sites, and an unscoped flat router competes all of them for every query:
    # left alone it re-routed R01 from edge-picamera-image to
    # edge-cpu-inference and changed the emitted image, which would silently
    # move answers already collected and published for arms s14-s17.
    from advisor.artifacts.registry import EDGE_ARTIFACTS
    router = RetrievalRouter(
        store, artifacts=[a.artifact_id for a in EDGE_ARTIFACTS])
    reasoner = Reasoner()
    print(f"embedder {store.embedder.name}, {store.num_chunks} chunks, "
          f"{len(inventory)} device types")

    ok = err = 0
    for path in items:
        item = yaml.safe_load(path.read_text())
        try:
            if chameleon:
                availability = chameleon_availability(item)
                result = select(inventory, availability, Request(
                    site=item["site"], count=item.get("requested_count", 1),
                    hours=item.get("requested_hours", 3),
                    requires=item.get("requires") or {},
                    api_family="baremetal",
                    now=snapshot_now(item["snapshot"])))
                text = render_chameleon(result, item["snapshot"],
                                        count=item.get("requested_count", 1))
                rec = None
            else:
                availability = availability_from_snapshot(item["snapshot"], captable)
                free_types = {}
                for d in availability:
                    if d.free_now:
                        free_types[d.machine_type] = \
                            free_types.get(d.machine_type, 0) + 1
                retrieval = router.route(item["prompt"])
                # Edge inventory only. The catalog carries 29 bare-metal types
                # now, and handing them to the edge reasoner made it reject
                # each one by name - "gpu_h100 (no camera)" in an answer about
                # a Raspberry Pi. The pick never changed; the reasoning around
                # it filled with hardware that was never a candidate.
                rec = reasoner.recommend(item["prompt"], availability,
                                         edge_inventory, retrieval)
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
                          produced_by=("ladder" if chameleon
                                       else getattr(rec, "produced_by", "heuristic")),
                          wing=args.wing,
                          # Snapshot-backed, never live. An answer graded
                          # against a pinned capture and one produced against
                          # the real site are not the same measurement.
                          availability_mode="snapshot",
                          advisor_catalog_sha256=catalog_sha)

    print(f"{len(items)} items -> {outdir}")
    print(f"  answered {ok}   errored {err}   (wing={args.wing}, "
          f"availability=snapshot)")
    suite = "baremetal_reservation" if chameleon else "reservation"
    print(f"\nScore with:\n  ../.venv/bin/python tools/score_runs.py "
          f"--suite {suite}")
    # An arm where nothing answered is not an arm. Say so in the exit code.
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
