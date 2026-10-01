#!/usr/bin/env python3
"""verify_golds_exec: RUN every bare-metal gold and check what it actually did.

  python corpus_v2/tools/verify_golds_exec.py            # all items
  python corpus_v2/tools/verify_golds_exec.py CB09       # one
  python corpus_v2/tools/verify_golds_exec.py --trace CB09   # show the trace

WHY THIS EXISTS
The checkers prove an answer has the right SHAPE - the right calls, the right
kwargs, in the right places. They cannot prove it would DO the right thing. So
"are the golds verified?" has, until now, had a weaker answer than it should:
they pass their own checkers, which is circular-sounding even though the gate is
real.

This closes that. Each gold is executed against a stub backed by the REAL Blazar
capture of 2026-09-04, and what it did - which site, which node type, how many,
bound to which reservation, with which image, torn down or not - is compared to
an expectation the item declares independently of its checkers. A gold that
parses, satisfies every checker and still reserves the wrong hardware fails here.

The stub hard-errors on hardware that does not exist at the selected site, and
merely records scarcity: "0 of 37 free" is a fact about the calendar, not a
mistake in the answer, and grading it here would make the suite measure when it
was run.

Executed code is the benchmark's own gold text, in a subprocess, with no network
and no credentials. The stub is the only `chi` on the path.

PRECONDITIONS FOR RUNNING A GOLD FOR REAL
Two things the golds need that this stub cannot supply and deliberately does
not model, because they are properties of the caller's environment rather than
of the API:

  A KEYPAIR.  `chi.server.Server(...)` with no `key_name` falls through to
  `update_keypair()`, which wants a keypair named f"{USER}-jupyter" and a
  public-key path from the `keypair_public_key` context variable. Chameleon's
  hosted Jupyter provides both; a shell, a container and CI provide neither,
  and the failure is `AttributeError: 'NoneType' object has no attribute
  'name'` - an error that names neither keypairs nor the missing setting.

  This is NOT written into the golds. A keypair name is specific to whoever is
  running, so putting one in a reference answer would bake one person's account
  into the benchmark's definition of correct. It is a precondition on the
  RUNNER, and `notebooks/live_gold_batch.py --emulate-notebook` supplies it
  when executing golds against the real testbed.

  The `show=` argument is the opposite case and IS modelled here - see
  stub_chi/chi/server.py. It is a property of the call, not of the caller, so
  a gold can and now does get it right.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent.parent
WING = BENCH / "chameleon_bench"
ITEMS = WING / "data" / "items"
SNAPSHOTS = WING / "data" / "snapshots"
STUB = WING / "harness" / "stub_chi"

TIMEOUT = 20


def run_gold(code: str) -> tuple[int, dict, str]:
    """Execute one gold with the stub on the path. Returns (rc, trace, stderr)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(STUB) + os.pathsep + env.get("PYTHONPATH", "")
    env["CHI_SNAPSHOT_DIR"] = str(SNAPSHOTS)
    with tempfile.TemporaryDirectory() as td:
        trace_path = Path(td) / "trace.json"
        env["CHI_TRACE"] = str(trace_path)
        src = Path(td) / "gold.py"
        src.write_text("def display(x):\n    print(x)\n\n" + code)
        try:
            p = subprocess.run([sys.executable, str(src)], capture_output=True,
                               text=True, timeout=TIMEOUT, env=env)
            rc, err = p.returncode, p.stderr
        except subprocess.TimeoutExpired:
            return 124, {}, "timeout"
        trace = json.loads(trace_path.read_text()) if trace_path.exists() else {}
    return rc, trace, err


# ----------------------------------------------------------------- comparison

def compare(expect: dict, trace: dict) -> list[str]:
    """Every way the recorded effect can differ from what the item declared."""
    bad = []
    leases = trace.get("leases") or []
    servers = trace.get("servers") or []

    if "site" in expect and trace.get("site") != expect["site"]:
        bad.append(f"site: ran at {trace.get('site')!r}, expected {expect['site']!r}")

    if "node_reservations" in expect:
        got = [{"node_type": r["node_type"], "amount": r["amount"]}
               for l in leases for r in l["node_reservations"]]
        want = [{"node_type": r["node_type"], "amount": r.get("amount", 1)}
                for r in expect["node_reservations"]]
        if got != want:
            bad.append(f"node reservations: got {got}, expected {want}")

    if "flavor_reservations" in expect:
        got = [{"flavor": r["flavor"], "amount": r["amount"]}
               for l in leases for r in l["flavor_reservations"]]
        want = [{"flavor": r["flavor"], "amount": r.get("amount", 1)}
                for r in expect["flavor_reservations"]]
        if got != want:
            bad.append(f"flavor reservations: got {got}, expected {want}")

    if "lease_hours" in expect:
        got = [l["hours"] for l in leases if l["hours"] is not None]
        if expect["lease_hours"] not in got:
            bad.append(f"lease hours: got {got}, expected {expect['lease_hours']}")

    if expect.get("lease_submitted") and not any(l["submitted"] for l in leases):
        bad.append("no lease was submitted")

    if "server_image" in expect:
        got = [s["image"] for s in servers]
        if expect["server_image"] not in got:
            bad.append(f"server image: got {got}, expected {expect['server_image']!r}")

    if expect.get("server_bound_to_reservation"):
        if not any(s["bound_to_reservation"] for s in servers):
            bad.append("no server was bound to a reservation from the lease "
                       "(reservation_id absent, or not derived from it)")

    if "server_flavor" in expect:
        got = [s["flavor"] for s in servers]
        if expect["server_flavor"] not in got:
            bad.append(f"server flavor: got {got}, expected {expect['server_flavor']!r}")

    if expect.get("lease_deleted") and not any(l["deleted"] for l in leases):
        bad.append("lease was never deleted (no teardown)")
    if expect.get("server_deleted") and not any(s["deleted"] for s in servers):
        bad.append("server was never deleted (no teardown)")

    if "fip_reservations" in expect:
        got = sum(len(l["fip_reservations"]) for l in leases)
        if got != expect["fip_reservations"]:
            bad.append(f"floating-ip reservations: got {got}, "
                       f"expected {expect['fip_reservations']}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--trace", action="store_true", help="print each trace")
    args = ap.parse_args()

    paths = sorted(ITEMS.glob("*.yaml"))
    if not paths:
        raise SystemExit(f"no items under {ITEMS}")

    ran = failed = skipped = 0
    for p in paths:
        item = yaml.safe_load(p.read_text())
        if args.ids and item["id"] not in args.ids:
            continue
        expect = item.get("exec_expect")
        if not expect:
            skipped += 1
            print(f"{item['id']:<7} SKIP   no exec_expect "
                  f"({item.get('expected_answer_type')})")
            continue

        ran += 1
        rc, trace, err = run_gold(item["gold_spec"])
        if rc != 0:
            failed += 1
            tail = err.strip().splitlines()[-1] if err.strip() else f"rc={rc}"
            print(f"{item['id']:<7} ERROR  {tail}")
            continue
        bad = compare(expect, trace)
        if bad:
            failed += 1
            print(f"{item['id']:<7} FAIL")
            for b in bad:
                print(f"        x {b}")
        else:
            notes = trace.get("notes") or []
            print(f"{item['id']:<7} OK     " +
                  (f"({notes[0]})" if notes else ""))
        if args.trace:
            print(json.dumps(trace, indent=1))

    print(f"\nExecuted {ran} gold(s): {ran - failed} correct, {failed} failed; "
          f"{skipped} without an execution expectation.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
