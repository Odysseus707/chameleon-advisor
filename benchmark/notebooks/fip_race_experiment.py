#!/usr/bin/env python3
"""fip_race_experiment: what is actually true when associate_floating_ip fails.

  python fip_race_experiment.py --site CHI@UC

CB14 raised `ResourceError: None of the ports can route to floating ip ...`.
CB38 raised at the same call on one run and passed on another; CB19 passed.
Seven golds call `associate_floating_ip()` on the line after `submit()`.

WHY AN EXPERIMENT AND NOT A FIX
`chi/server.py:952-973` reaches that one error message from two different
states, and the message cannot tell them apart:

    ports = list(conn.network.ports(device_id=server_id))
    for port in ports:
        try:    return conn.network.update_ip(fip["id"], port_id=port["id"])
        except SDKException: pass        # <- swallows the real reason
    raise ResourceError("None of the ports can route to floating ip ...")

  (a) `ports` is EMPTY - the loop never runs and it falls through to the raise.
  (b) ports exist and every update_ip attempt failed.

If it is (a) the fix is to wait for a port. If it is (b) waiting fixes nothing
and the fix is something else entirely. Writing a wait into seven golds on the
strength of a guess is exactly what D80 refuses to do, so this measures which
state it is, and how long (a) lasts.

WHAT IT RECORDS
Immediately after submit() returns - the instant the golds currently call
associate - and then every 5s: how many neutron ports the server has, and
whether the server reports any addresses. Then it attempts the association and
records which attempt succeeded. The output is the evidence a fix has to be
built from.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
EXPORTS = BENCH / "exports"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BENCH.parent / "chi-edge-advisor"))

import live_api_probe as P                                # noqa: E402
import live_gold_batch as B                               # noqa: E402

POLL_SECONDS = 5
MAX_WAIT = 300


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", default="CHI@UC", choices=sorted(B.SITE_RC))
    ap.add_argument("--node-type", default=None)
    args = ap.parse_args()

    B.use(args.site)
    import chi
    from chi import lease as chi_lease
    from chi import server as chi_server

    free = B.free_counts(args.site)
    ntype = args.node_type or next(
        (t for t in ("gpu_rtx_6000", "compute_skylake", "compute_cascadelake_r",
                     "compute_cascadelake", "compute_haswell_ib")
         if free.get(t, 0) > 0), None)
    if not ntype:
        print(f"nothing free at {args.site}: {free}")
        return 1
    print(f"{args.site}: using {ntype} ({free[ntype]} free)")

    rec = {"site": args.site, "node_type": ntype,
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "samples": [], "associate_attempts": []}
    name = f"fiprace-{datetime.datetime.now():%H%M%S}"
    lease = None
    try:
        lease = chi_lease.Lease(name + "-lease",
                                duration=datetime.timedelta(hours=1))
        lease.add_node_reservation(amount=1, node_type=ntype)
        lease.add_fip_reservation(1)
        lease.submit(idempotent=True, wait_for_active=True)
        rid = lease.node_reservations[0]["id"]
        print(f"lease {lease.id} reservation {rid}")

        srv = chi_server.Server(name, image_name="CC-Ubuntu22.04",
                                reservation_id=rid, key_name=P.KEYPAIR_NAME)
        srv.submit(idempotent=True, show="text")
        print(f"server {srv.id} submitted; submit() has returned - this is the "
              "instant the golds call associate_floating_ip()\n")

        conn = chi.clients.connection()
        t0 = time.time()
        while time.time() - t0 < MAX_WAIT:
            elapsed = round(time.time() - t0, 1)
            ports = list(conn.network.ports(device_id=srv.id))
            s = conn.compute.get_server(srv.id)
            rec["samples"].append({"t": elapsed, "ports": len(ports),
                                   "status": s.status,
                                   "addresses": bool(s.addresses)})
            print(f"  t={elapsed:6.1f}s  ports={len(ports)}  "
                  f"status={s.status}  addresses={bool(s.addresses)}")
            if ports:
                rec["first_port_at"] = elapsed
                break
            time.sleep(POLL_SECONDS)

        # Now attempt the association, retrying, recording which attempt wins.
        for attempt in range(1, 6):
            try:
                fip = srv.associate_floating_ip()
                rec["associate_attempts"].append(
                    {"attempt": attempt, "ok": True, "fip": str(fip)})
                print(f"\nassociate_floating_ip: SUCCEEDED on attempt "
                      f"{attempt} -> {fip}")
                break
            except Exception as exc:                      # noqa: BLE001
                rec["associate_attempts"].append(
                    {"attempt": attempt, "ok": False,
                     "error": f"{type(exc).__name__}: {exc}"})
                print(f"\nassociate_floating_ip attempt {attempt} FAILED: "
                      f"{type(exc).__name__}: {exc}")
                time.sleep(POLL_SECONDS)
    finally:
        print("\n-- teardown --")
        try:
            conn2 = chi.clients.connection()
            for s in conn2.compute.servers():
                if s.name == name:
                    conn2.compute.delete_server(s)
                    print(f"  deleted server {name}")
        except Exception as exc:                          # noqa: BLE001
            print(f"  server: {exc}")
        if lease is not None:
            try:
                chi_lease.delete_lease(lease.id)
                print(f"  deleted lease {lease.id}")
            except Exception as exc:                      # noqa: BLE001
                print(f"  lease: {exc}")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    out = EXPORTS / f"fip_race_experiment_{datetime.date.today().isoformat()}.json"
    out.write_text(json.dumps(rec, indent=1) + "\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
