#!/usr/bin/env python3
"""live_gold_batch: run gold answers against the REAL testbed, in parallel.

  python live_gold_batch.py --site CHI@TACC --plan
  python live_gold_batch.py --site CHI@TACC --run 9 --emulate-notebook
  python live_gold_batch.py --site CHI@UC   --run 9 --emulate-notebook
  python live_gold_batch.py --site CHI@TACC --sweep

One site per invocation, so the two can run as two concurrent processes without
sharing python-chi's global client state. Within a site, golds run concurrently
in waves.

THIS IS THE V2 PATH
`verify_golds_exec.py` runs each gold against a stub backed by the pinned
capture: no network, no credentials, and the stub decides what "worked" means.
That is V1, and it is circular in one specific way - the stub was written from
the same understanding of the API as the golds, so where they agree the
agreement is not evidence. Every time the testbed has disagreed with the stub
this cycle, the stub was the thing that was wrong.

So this writes each gold's own text to a file, runs it with `runpy` as
`__main__` - unmodified - and then asks Blazar and Nova what actually exists.

WAVES, BECAUSE GOLDS NAME THEIR RESOURCES
Several golds call their lease "node-lease" and their instance "node": a gold is
written to be read, not to be run five at a time. Nova permits duplicate names,
so all of them get created, and then `idempotent=True` - which looks resources
up BY NAME - dies with "Multiple matching servers found for name 'node'".
Measured, not predicted: a name-blind parallel run failed exactly three golds
that way, and all three had already reserved and booted correctly.

So golds are grouped into waves where no two share a declared name, AND EACH
WAVE IS TORN DOWN BEFORE THE NEXT STARTS. The teardown placement is not
incidental: with teardown deferred to the end, wave 2's "node" collides with
wave 1's "node" still sitting there, and the wave scheduling buys nothing. That
bug is why this says so at length.

WHAT ADEQUACY MEANS HERE
`exec_expect` claims `server_bound_to_reservation`, and "an instance exists"
does not check it: the documented trap is precisely an instance that boots
while bound to nothing.

Comparing the instance's own `reservation_id` was the obvious check and it does
not work - Nova does not return the reservation on a server it hands back, so
that field is None for every instance we did not construct ourselves, and the
comparison measures nothing. It was tried and it failed on four golds that were
all behaving correctly.

The measurable version comes from the trap experiment. A LEASE id passed where
a RESERVATION id belongs is ACCEPTED by Nova and the instance then reaches
ERROR - confirmed on 2026-09-05 and again on 2026-09-07. It never reaches
ACTIVE. So a bare-metal instance at ACTIVE was bound to a real reservation,
and together with the two checks above - the gold created a lease whose
reservation is for the declared node type, and took the id from it - ACTIVE is
the binding.

AN EXCEPTION IS NOT THE SAME AS A WRONG ANSWER
python-chi raises on things that WORKED: `Server.submit()` defaults
`show="widget"`, which needs a notebook, and raises AFTER the instance is
ACTIVE. Exceptions are classified, and the API is queried regardless of exit
code.

SAFETY
Leaking is the real risk, not the SUs. Everything created is registered to disk
before any assertion runs against it; teardown runs per wave in a `finally`;
and `--sweep` diffs the project against a snapshot taken BEFORE anything was
created, so it needs neither of the other two and never touches resources that
predate the run - this project holds unrelated ones.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
ROOT = BENCH.parent
ITEMS = BENCH / "chameleon_bench" / "data" / "items"
EXPORTS = BENCH / "exports"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "chi-edge-advisor"))

import live_api_probe as P                                # noqa: E402

#: One application credential per site, and in BOTH cases the `_2` file - the
#: August originals are for a different allocation. The August CHI@TACC one
#: also returns keystone 401 now (D63). Listing them explicitly rather than
#: globbing the directory is deliberate: a glob picks up seven openrc files
#: across five sites and two projects, and "whichever matched first" is not a
#: basis for spending someone's allocation.
SITE_RC = {
    "CHI@TACC": "app-cred-vivek_tacc_2-openrc.sh",
    "CHI@UC": "app-cred-vivek_uc_2-openrc.sh",
}
EXPECT_PROJECT = "CHI-231225"
PER_GOLD_TIMEOUT = 1800

JUPYTER_ONLY = (
    ("Invalid show type",
     "Server.submit() defaults show='widget', which needs a notebook; it "
     "raises AFTER the instance is created and ACTIVE."),
    ("'NoneType' object has no attribute 'name'",
     "No keypair: Server() without key_name falls through to update_keypair()."),
)
_NAME_RE = re.compile(r"(?:Lease|Server)\(\s*\n?\s*[\"']([^\"']+)[\"']")


def classify(stderr: str) -> tuple[str, str]:
    for needle, why in JUPYTER_ONLY:
        if needle in stderr:
            return "jupyter_only", why
    return "real", stderr.strip()[-900:]


def declared_names(gold: str) -> set[str]:
    return set(_NAME_RE.findall(gold))


def waves(items: list[dict]) -> list[list[dict]]:
    """Greedy grouping so no two golds in a wave share a resource name."""
    out: list[list[dict]] = []
    for it in items:
        names = declared_names(it["gold"])
        for w in out:
            if all(not (names & declared_names(x["gold"])) for x in w):
                w.append(it)
                break
        else:
            out.append([it])
    return out


# --- credentials ------------------------------------------------------------

def site_env(site: str) -> dict:
    """OS_* for one site, sourced in a subshell. Secrets never printed."""
    from advisor.availability.blazar import load_rc
    rc = ROOT / "credentials" / SITE_RC[site]
    env = load_rc(str(rc))
    if not env.get("OS_APPLICATION_CREDENTIAL_ID"):
        raise SystemExit(f"{rc.name}: no application credential found")
    return env


def use(site: str) -> None:
    """Point python-chi at a site, and REFUSE if it is the wrong allocation.

    This assertion was in `live_api_probe.authenticate()` from the start and I
    dropped it when generalising to two sites - so the first multi-site run
    would have reserved against whatever project the CHI@UC openrc happened to
    carry, without ever saying which. An application credential brings its own
    project scope and cannot be re-scoped (Keystone answers "Application
    credentials cannot request a scope"), so asking Keystone is the ONLY way to
    know which allocation is about to be spent.
    """
    env = site_env(site)
    os.environ.update(env)
    from advisor.availability.blazar import keystone_auth
    _tok, body, err = keystone_auth(env)
    if err:
        raise SystemExit(f"{site}: authentication failed ({err})")
    project = ((body or {}).get("token", {}).get("project", {}) or {}).get("name")
    if project != EXPECT_PROJECT:
        raise SystemExit(
            f"REFUSING TO CONTINUE: {site} credential {SITE_RC[site]} is scoped "
            f"to {project!r}, not {EXPECT_PROJECT!r}. Reserving here would draw "
            "down the wrong allocation.")
    print(f"{site}: scoped to {project}")
    import chi
    chi.use_site(site)


# --- inventory --------------------------------------------------------------

def free_counts(site: str) -> dict:
    """Free hosts per node type, read through THE credential this run uses.

    Globbing the credentials directory would probe every openrc whose region
    matches - two files per site, for two different allocations - and take
    whichever answered. Availability is the same either way, but "whichever
    matched first" is how the wrong credential gets used somewhere that it
    matters, so the glob is narrowed to the one file SITE_RC names.
    """
    from advisor.availability.blazar import fetch_sites
    out: dict[str, int] = {}
    for b in fetch_sites(rc_glob=str(ROOT / "credentials" / SITE_RC[site]),
                         sites={site}):
        if b["error"]:
            continue
        for n in b["nodes"]:
            out.setdefault(n["node_type"], 0)
            if n["status"] == "free":
                out[n["node_type"]] += 1
    return out


def candidates(site: str) -> list[dict]:
    out = []
    for p in sorted(ITEMS.glob("CB*.yaml")):
        item = yaml.safe_load(p.read_text())
        e = item.get("exec_expect") or {}
        if e.get("site") != site:
            continue
        types = [r.get("node_type") for r in (e.get("node_reservations") or [])
                 if r.get("node_type")]
        if not types:
            continue
        out.append({"id": item["id"], "types": types,
                    "gold": item["gold_spec"], "expect": e})
    return out


def plan(site: str, n: int):
    """Select golds whose hardware is free, spending the free pool as we go.

    The budget matters: two golds wanting the same scarce type must not both be
    scheduled, or the second is reported as failing when the first simply took
    the last node - grading the calendar again, one level up.
    """
    free = free_counts(site)
    budget = dict(free)
    runnable, skipped = [], []
    for c in candidates(site):
        short = [t for t in c["types"] if budget.get(t, 0) < 1]
        if short:
            skipped.append((c, f"{short[0]}: {free.get(short[0], 0)} free"))
        elif len(runnable) < n:
            c["free"] = {t: free.get(t, 0) for t in c["types"]}
            for t in c["types"]:
                budget[t] -= 1
            runnable.append(c)
    return runnable, skipped


# --- project snapshot -------------------------------------------------------

def project_now():
    import chi
    from chi import lease as chi_lease
    leases = []
    for lz in chi_lease.list_leases():
        lid = lz["id"] if isinstance(lz, dict) else getattr(lz, "id", None)
        nm = lz["name"] if isinstance(lz, dict) else getattr(lz, "name", "")
        if lid:
            leases.append({"id": lid, "name": nm})
    # By ID, not name. Nova deletion is ASYNCHRONOUS, so a server deleted in
    # wave 2 is still listed while wave 3 starts - and since several golds name
    # their instance "node", a name-diff then reports wave 3's brand-new
    # instance as "not new" and its gold as having booted nothing. Measured:
    # CB27 and CB31 failed exactly that way while having booted correctly.
    try:
        servers = [{"id": s.id, "name": s.name, "status": s.status}
                   for s in chi.clients.connection().compute.servers()]
    except Exception:                                     # noqa: BLE001
        servers = []
    return leases, servers


# --- one gold ---------------------------------------------------------------

WRAPPER = """import runpy
import chi.server as S
S._is_ipynb = lambda: True                       # show='widget' default
_get = S.get_keypair
S.update_keypair = lambda *a, **k: _get({kp!r})   # key_name default
runpy.run_path({gold!r}, run_name="__main__")
"""


def run_one(gold: str, emulate: bool, env: dict) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "gold.py"
        f.write_text(gold)
        if emulate:
            w = Path(td) / "_wrapper.py"
            w.write_text(WRAPPER.format(kp=P.KEYPAIR_NAME, gold=str(f)))
            argv = [sys.executable, str(w)]
        else:
            argv = [sys.executable, str(f)]
        try:
            r = subprocess.run(argv, capture_output=True, text=True,
                               timeout=PER_GOLD_TIMEOUT, cwd=td,
                               env={**os.environ, **env})
            return r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            return 124, "", f"timed out after {PER_GOLD_TIMEOUT}s"


# --- verification -----------------------------------------------------------

def reservation_of(lease_id: str):
    from chi import lease as chi_lease
    try:
        res = chi_lease.get_lease(lease_id).node_reservations or []
        return res[0] if res else None
    except Exception:                                     # noqa: BLE001
        return None


def server_status(sid: str):
    """The instance's status, read back from Nova."""
    import chi
    try:
        return chi.clients.connection().compute.get_server(sid).status
    except Exception:                                     # noqa: BLE001
        return None


def verify(item: dict, new_leases, new_servers) -> list[tuple[str, bool, str]]:
    e = item["expect"]
    names = declared_names(item["gold"])
    want = next((r.get("node_type")
                 for r in (e.get("node_reservations") or [])), None)
    mine = [l for l in new_leases if l["name"] in names]

    if e.get("lease_deleted"):
        # A gold that deletes its own lease has nothing left to find, and that
        # is the gold being RIGHT.
        return [("tore down its own lease, as the item declares", not mine,
                 "nothing left behind" if not mine
                 else f"{mine[0]['name']} survives")]

    checks = [(f"reserved {want}", bool(mine),
               f"lease {mine[0]['name']}" if mine else "no lease found")]
    if not mine:
        return checks

    res = reservation_of(mine[0]["id"])
    blob = json.dumps(res, default=str) if res else ""
    checks.append((f"the reservation is for {want}",
                   bool(want) and want in blob,
                   blob[:110] or "no reservation on the lease"))
    rid = (res or {}).get("id")
    checks.append(("reservation id differs from the lease id",
                   bool(rid) and rid != mine[0]["id"],
                   f"{rid} vs {mine[0]['id']}"))

    if e.get("server_image"):
        srv = [s for s in new_servers if s["name"] in names]
        checks.append(("booted an instance", bool(srv),
                       f"{[x['name'] for x in srv] or 'none'}"))
        if srv and e.get("server_bound_to_reservation"):
            # WHY ACTIVE IS THE BINDING CHECK, and not a reservation_id compare.
            # Nova does not return the reservation on a server it hands back:
            # `get_server(...).reservation_id` is None for every instance we
            # did not construct ourselves, so comparing it measures nothing.
            #
            # ACTIVE does measure it, because of the trap experiment. Passing a
            # LEASE id where a RESERVATION id belongs was ACCEPTED by Nova on
            # both 2026-09-05 and 2026-09-07 and the instance then reached
            # ERROR - never ACTIVE. A bare-metal instance therefore reaches
            # ACTIVE only when it was bound to a real reservation. Combined
            # with the gold having taken that id from the lease it just created
            # and the reservation being for the declared node type - both
            # checked above - ACTIVE is the binding.
            st = server_status(srv[0]["id"]) or srv[0].get("status")
            checks.append(("instance reached ACTIVE, so it bound to a real "
                           "reservation (see the trap result)",
                           st == "ACTIVE",
                           f"status {st}; lease reservation is {rid}"))
    return checks


# --- teardown ---------------------------------------------------------------

def wait_gone(ids, timeout=180) -> None:
    """Block until deleted instances are really gone.

    Nova deletion is ASYNCHRONOUS and `idempotent=True` looks instances up BY
    NAME, so a wave that starts while the previous wave's identically-named
    instance is still dissolving does not create its own instance at all - it
    ADOPTS the corpse and returns. Measured: CB34 exited 0, reserved gpu_mi100
    correctly, and booted nothing, because CB31's "node" from the wave before
    was still listed. Tearing down between waves is not enough; the teardown
    has to have finished.
    """
    import time
    import chi
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            alive = {s.id for s in chi.clients.connection().compute.servers()}
        except Exception:                                 # noqa: BLE001
            return
        if not (set(ids) & alive):
            return
        time.sleep(5)
    print(f"    (still visible after {timeout}s: {sorted(set(ids) & alive)})")


def remove(leases, servers) -> None:
    import chi
    from chi import lease as chi_lease
    conn = chi.clients.connection()
    for rec in servers:
        try:
            conn.compute.delete_server(rec["id"])
            print(f"    deleted server {rec['name']}")
        except Exception as exc:                          # noqa: BLE001
            print(f"    server {rec['name']}: {type(exc).__name__}: {exc}")
    for l in leases:
        try:
            chi_lease.delete_lease(l["id"])
            print(f"    deleted lease {l['name']}")
        except Exception as exc:                          # noqa: BLE001
            print(f"    lease {l['name']}: {type(exc).__name__}: {exc}")


def state_path(site: str) -> Path:
    return HERE / f"live_gold_batch_state_{site.replace('@', '_')}.json"


# --- report -----------------------------------------------------------------

def report(runs, skipped, started, site) -> Path:
    L = [f"# Live gold execution against {site} (V2)\n",
         f"Started {started.isoformat()} · project {EXPECT_PROJECT} · "
         f"python-chi {P.chi_version()}\n",
         "Gold text executed verbatim via `runpy`, then the API asked what "
         "exists. No stub involved.\n",
         "## Results\n",
         "| item | exit | classification | checks | failing |",
         "|---|---|---|---|---|"]
    for r in runs:
        ok = sum(1 for _, p, _ in r["checks"] if p)
        bad = "; ".join(n for n, p, _ in r["checks"] if not p) or "—"
        L.append(f"| {r['item']} | {r['rc']} | {r['kind']} | "
                 f"{ok}/{len(r['checks'])} | {bad} |")
    L.append("")
    for r in runs:
        L.append(f"### {r['item']} — exit {r['rc']}, {r['kind']}\n")
        for name, passed, detail in r["checks"]:
            L.append(f"- **{'PASS' if passed else 'FAIL'}** {name} — {detail}")
        if r["kind"] == "real" and r["why"]:
            L.append(f"\n```\n{r['why']}\n```")
        L.append("")
    if skipped:
        L.append("## Skipped — hardware not free (the calendar, not the gold)\n")
        L.append("| item | reason |")
        L.append("|---|---|")
        L.extend(f"| {c['id']} | {why} |" for c, why in skipped)
    EXPORTS.mkdir(parents=True, exist_ok=True)
    out = EXPORTS / (f"live_gold_batch_{site.replace('@', '_')}_"
                     f"{started.date().isoformat()}.md")
    out.write_text("\n".join(L) + "\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", required=True, choices=sorted(SITE_RC))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true")
    g.add_argument("--run", type=int, metavar="N")
    g.add_argument("--sweep", action="store_true")
    ap.add_argument("--only", default="",
                    help="comma-separated item ids, e.g. CB34")
    ap.add_argument("--emulate-notebook", action="store_true",
                    help="supply the Jupyter-ambient keypair and _is_ipynb "
                         "defaults the golds assume (D66); gold text is still "
                         "run verbatim")
    args = ap.parse_args()
    site, sp = args.site, state_path(args.site)

    use(site)
    st = json.loads(sp.read_text()) if sp.is_file() else {}

    if args.sweep:
        pre = st.get("pre")
        if not pre:
            print("no pre-snapshot; refusing to guess what is ours")
            return 1
        now_l, now_s = project_now()
        el = [l for l in now_l
              if l["id"] not in {x["id"] for x in pre["leases"]}]
        pre_ids = {x["id"] for x in pre["servers"]}
        es = [x for x in now_s if x["id"] not in pre_ids]
        if not el and not es:
            print(f"{site} sweep: nothing exists that did not exist before. "
                  "Clean.")
            return 0
        remove(el, es)
        return 0

    runnable, skipped = plan(site, args.run or 99)
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        runnable = [c for c in runnable if c["id"] in want]
    sched = waves(runnable)
    print(f"\n{site}: {len(runnable)} runnable, {len(skipped)} skipped, "
          f"{len(sched)} wave(s)")
    for i, w in enumerate(sched, 1):
        print(f"  wave {i}: {[c['id'] for c in w]}")
    for c, why in skipped:
        print(f"  SKIP {c['id']}  {why}")
    if args.plan:
        print("plan only; pass --run N to execute")
        return 0
    if not runnable:
        return 0

    started = datetime.datetime.now(datetime.timezone.utc)
    pl, ps = project_now()
    st["pre"] = {"leases": pl, "servers": ps}
    sp.write_text(json.dumps(st, indent=1) + "\n")
    print(f"\npre-snapshot: {len(pl)} lease(s), {len(ps)} server(s) already "
          "present; nothing else is ever deleted\n")

    env, runs = site_env(site), []
    for i, wave in enumerate(sched, 1):
        print(f"  wave {i}: {[c['id'] for c in wave]}")
        before_l, before_s = project_now()
        bl, bs = {l["id"] for l in before_l}, {x["id"] for x in before_s}
        new_l, new_s, results = [], [], {}
        try:
            with cf.ThreadPoolExecutor(max_workers=len(wave)) as pool:
                futs = {pool.submit(run_one, c["gold"],
                                    args.emulate_notebook, env): c
                        for c in wave}
                for fut in cf.as_completed(futs):
                    c = futs[fut]
                    try:
                        rc, _out, err = fut.result()
                    except Exception as exc:              # noqa: BLE001
                        rc, err = -1, str(exc)
                    results[c["id"]] = (rc, err)
                    print(f"    {c['id']:6s} exit {rc}")

            after_l, after_s = project_now()
            new_l = [l for l in after_l if l["id"] not in bl]
            new_s = [x for x in after_s if x["id"] not in bs]
            st["open"] = {"leases": new_l, "servers": new_s}
            sp.write_text(json.dumps(st, indent=1) + "\n")

            for c in wave:
                rc, err = results.get(c["id"], (-1, "no result"))
                kind, why = ("clean", "") if rc == 0 else classify(err)
                runs.append({"item": c["id"], "rc": rc, "kind": kind,
                             "why": why, "checks": verify(c, new_l, new_s)})
        finally:
            # PER WAVE, not at the end: a surviving "node" from wave 1 is
            # exactly what makes wave 2's identically-named gold collide.
            print("    -- wave teardown --")
            remove(new_l, new_s)
            wait_gone([x["id"] for x in new_s])
            st["open"] = {}
            sp.write_text(json.dumps(st, indent=1) + "\n")

    out = report(runs, skipped, started, site)
    full = sum(1 for r in runs
               if r["checks"] and all(p for _, p, _ in r["checks"]))
    print(f"\n{site}: {full}/{len(runs)} gold(s) did everything their item "
          f"declares, live. Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
