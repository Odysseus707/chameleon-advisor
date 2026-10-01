#!/usr/bin/env python3
"""live_api_probe: the live API-idiom assertions, one spending step per call.

  python live_api_probe.py auth              # free
  python live_api_probe.py images            # free
  python live_api_probe.py lease             # SPENDS: creates one lease
  python live_api_probe.py idioms            # free, needs `lease`
  python live_api_probe.py boot              # SPENDS: boots one server
  python live_api_probe.py teardown          # deletes everything, always safe
  python live_api_probe.py report            # print + write the results file

WHY THIS EXISTS ALONGSIDE THE NOTEBOOK
`verify_golds_live.ipynb` already does this work and is the artifact a human
should read. What it cannot do is stop between two spending cells when the
operator is a process rather than a person: a notebook run is all-or-nothing
from a shell. Each step here is a separate invocation, so a lease is created
only when someone types the word `lease`, and the operator sees the result of
every assertion before authorising the next one.

The assertions live HERE and the notebook calls into them, so there is exactly
one copy. The notebook keeps its own auth cell, its own teardown cell and its
own narrative; it gains no second implementation to drift against.

THE REGISTRY IS ON DISK, NOT IN MEMORY
Separate invocations share no variables, so a lease created by one process
would be invisible to the next - and an invisible lease is a leaked lease,
which is the real risk here, not the SUs. Every created id is written to
live_probe_state.json the instant it exists, before any assertion runs against
it. `teardown` reads that file and needs nothing else to have gone right.

NEGATIVE TESTS MUST FAIL FOR THE RIGHT REASON
A bare `except Exception` cannot tell "Chameleon rejected this" from "our own
code broke", and the notebook's first run recorded a PASS on the trap test when
what actually happened was a NameError. Preconditions are therefore checked
before anything is attempted, and a missing one raises rather than records.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import traceback
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
RC = WORKSPACE / "credentials" / "app-cred-vivek_tacc_2-openrc.sh"
STATE = HERE / "live_probe_state.json"
RESULTS_FILE = HERE / "live_verification_results.json"

EXPECT_PROJECT = "CHI-231225"
SITE = "CHI@TACC"

#: 13 of 17 free at the time of writing, and the type the 2026-09-05 run used,
#: so a disagreement between the two runs is about the API and not the machine.
TEST_NODE_TYPE = "compute_haswell_ib"
LEASE_HOURS = 1

#: An existing keypair in CHI-231225. Passed EXPLICITLY, because the default
#: path is a trap this probe walked straight into on 2026-09-07.
#:
#: chi.server.Server(...) with neither `keypair` nor `key_name` falls through to
#: update_keypair(), which defaults the name to f"{USER}-jupyter" and then needs
#: a public-key path from the `keypair_public_key` context var. On Chameleon's
#: hosted Jupyter both are ambient and it works. Anywhere else - a laptop, CI, a
#: container - both are unset, self.keypair stays None, and submit() dies at
#: chi/server.py:198 with `AttributeError: 'NoneType' object has no attribute
#: 'name'`: an error that names neither keypairs nor the missing setting.
#:
#: Every gold that boots a server omits key_name, so every one of them carries
#: this dependency silently. That is a finding about the golds, not about this
#: file, and it is recorded as one rather than papered over here.
KEYPAIR_NAME = "vivek"

#: Every image name any gold or artifact asserts. Checked against Glance in one
#: free call: a retired image makes a gold unrunnable while every checker still
#: passes it, because the checkers only ever see the string.
IMAGE_NAMES = [
    "CC-Ubuntu22.04", "CC-Ubuntu20.04", "CC-Ubuntu24.04",
    "CC-Ubuntu22.04-CUDA", "CC-Ubuntu20.04-CUDA", "CC-Ubuntu24.04-CUDA",
]


# --- state ------------------------------------------------------------------

def load_state() -> dict:
    if STATE.is_file():
        return json.loads(STATE.read_text())
    return {"leases": [], "servers": [], "results": [], "meta": {}}


def save_state(st: dict) -> None:
    STATE.write_text(json.dumps(st, indent=1) + "\n")


def record(st: dict, name: str, passed: bool, detail: str = "") -> None:
    st["results"].append({"test": name,
                          "result": "PASS" if passed else "FAIL",
                          "detail": detail})
    save_state(st)
    print(f"{'PASS' if passed else 'FAIL'}  {name}"
          + (f"  - {detail}" if detail else ""))


def require(**names) -> None:
    missing = [k for k, v in names.items() if v is None]
    if missing:
        raise RuntimeError(
            f"precondition not met: {missing} is None - an earlier step did "
            "not complete. Not recording a result.")


# --- auth -------------------------------------------------------------------

def authenticate() -> dict:
    """Load OS_* from the openrc and return the Keystone token body.

    The secret is sourced in a subshell with stdin closed so a password-
    prompting openrc fails fast instead of hanging, and it is never printed.
    """
    out = subprocess.run(
        ["bash", "-c", f'set -a; . "{RC}" >/dev/null 2>&1; set +a; env'],
        capture_output=True, text=True, stdin=subprocess.DEVNULL)
    for line in out.stdout.splitlines():
        if line.startswith("OS_"):
            k, _, v = line.partition("=")
            os.environ[k] = v

    body = {"auth": {"identity": {
        "methods": ["application_credential"],
        "application_credential": {
            "id": os.environ["OS_APPLICATION_CREDENTIAL_ID"],
            "secret": os.environ["OS_APPLICATION_CREDENTIAL_SECRET"]}}}}
    req = urllib.request.Request(
        os.environ["OS_AUTH_URL"].rstrip("/") + "/auth/tokens",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        token = json.load(r)["token"]

    project = token["project"]["name"]
    print(f"site     : {os.environ['OS_REGION_NAME']}")
    print(f"project  : {project}")
    print(f"expires  : {token['expires_at']}")
    if project != EXPECT_PROJECT:
        raise SystemExit(
            f"REFUSING TO CONTINUE: token is scoped to {project!r}, not "
            f"{EXPECT_PROJECT!r}. Reserving here would draw down the wrong "
            "allocation.")
    return token


def use_site():
    """python-chi, pointed at the site. NEVER chi.set('project_name', ...).

    An application credential carries its own project scope and Keystone
    answers "Application credentials cannot request a scope. (HTTP 401)" to
    anything that tries to set one. The first run of the notebook failed
    exactly this way.
    """
    import chi
    chi.use_site(SITE)
    return chi


def chi_version() -> str:
    try:
        from importlib.metadata import version
        return version("python-chi")
    except Exception:                                    # noqa: BLE001
        return "unknown"


# --- steps ------------------------------------------------------------------

def step_auth(st):
    authenticate()
    st["meta"] = {"project": EXPECT_PROJECT, "site": SITE,
                  "node_type": TEST_NODE_TYPE,
                  "python_chi": chi_version(),
                  "utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    save_state(st)
    print(f"\npython-chi {st['meta']['python_chi']} - OK, scoped to "
          f"{EXPECT_PROJECT}. Nothing reserved.")


def step_images(st):
    """Free. Does every image name the corpus asserts still exist?"""
    authenticate()
    chi = use_site()
    try:
        from chi import image as chi_image
        names = {i.name for i in chi_image.list_images()}
    except Exception:                                    # noqa: BLE001
        conn = chi.clients.connection()
        names = {i.name for i in conn.image.images()}
    print(f"{len(names)} images visible at {SITE}\n")
    for want in IMAGE_NAMES:
        record(st, f"image {want} exists at {SITE}", want in names,
               "present" if want in names else "NOT FOUND - a gold naming "
               "this image cannot run")
    extra = sorted(n for n in names if n.startswith("CC-Ubuntu"))
    print(f"\nall CC-Ubuntu images live: {extra}")


def step_lease(st):
    """SPENDS. One lease, one node, LEASE_HOURS."""
    authenticate()
    use_site()
    from chi import lease as chi_lease
    name = f"goldtest-wiring-{datetime.datetime.now():%H%M%S}"
    l = chi_lease.Lease(name, duration=datetime.timedelta(hours=LEASE_HOURS))
    # THE RB GRAMMAR: node_type= plus amount=, which no live test had run.
    l.add_node_reservation(amount=1, node_type=TEST_NODE_TYPE)
    l.submit(idempotent=True, wait_for_active=True)

    # Registered BEFORE any assertion: an assertion that raises must not be
    # able to strand the lease it was asserting about.
    st["leases"].append({"id": l.id, "name": name})
    save_state(st)
    print(f"lease {l.id} ({name}) created and registered for teardown\n")

    record(st, "RB grammar add_node_reservation(node_type=, amount=) submits",
           True, f"{TEST_NODE_TYPE} x1, {LEASE_HOURS}h")
    has = bool(l.node_reservations) and "id" in l.node_reservations[0]
    record(st, 'node_reservations[0]["id"] is populated after submit', has,
           str(l.node_reservations[0].get("id")) if has else "absent")
    rid = l.node_reservations[0]["id"] if has else None
    record(st, "reservation id differs from lease id", rid != l.id,
           f"{rid} vs {l.id}")
    st["reservation_id"], st["lease_id"] = rid, l.id
    save_state(st)


def step_idioms(st):
    """Free. Both spellings of the reservation id, on the existing lease."""
    require(lease_id=st.get("lease_id"), reservation_id=st.get("reservation_id"))
    authenticate()
    use_site()
    from chi import lease as chi_lease
    lease_id, rid = st["lease_id"], st["reservation_id"]

    # The 2026-09-05 finding, re-confirmed against whatever ships today.
    try:
        via_fn = chi_lease.get_node_reservation(lease_id)
        record(st, "deprecated get_node_reservation still works",
               via_fn == rid, f"{via_fn} vs {rid}")
    except Exception as e:                               # noqa: BLE001
        record(st, "deprecated get_node_reservation still works", False,
               f"BROKEN in python-chi {chi_version()} - "
               f"{type(e).__name__}: {str(e)[:90]}")

    # The working spelling, re-read from a freshly fetched lease rather than
    # the object we already hold: a gold's reader starts from an id.
    try:
        fresh = chi_lease.get_lease(lease_id)
        got = fresh.node_reservations[0]["id"]
        record(st, 'node_reservations[0]["id"] on a re-fetched lease',
               got == rid, f"{got} vs {rid}")
    except Exception as e:                               # noqa: BLE001
        record(st, 'node_reservations[0]["id"] on a re-fetched lease', False,
               f"{type(e).__name__}: {str(e)[:90]}")


def step_boot(st):
    """SPENDS. Boots one server bound to the reservation."""
    require(reservation_id=st.get("reservation_id"))
    authenticate()
    use_site()
    from chi import server as chi_server
    rid = st["reservation_id"]
    name = f"goldtest-node-{datetime.datetime.now():%H%M%S}"
    s = chi_server.Server(name, image_name="CC-Ubuntu22.04", reservation_id=rid,
                          key_name=KEYPAIR_NAME)
    # show="text", not the "widget" default: chi/server.py:391 renders the
    # widget only when _is_ipynb() is true and RAISES otherwise - after the
    # instance is already ACTIVE. See D66; the golds all take the default.
    s.submit(idempotent=True, show="text")
    st["servers"].append({"id": getattr(s, "id", None), "name": name})
    save_state(st)
    print(f"server {name} submitted and registered for teardown\n")
    # submit(wait_for_active=True) is the default and has ALREADY waited by the
    # time it returns; the status is then read back rather than waited on again.
    # An earlier version called s.wait_for_active(), which does not exist on
    # Server - only the module-level deprecated function does - and recorded the
    # resulting AttributeError as a testbed FAIL on a server that had booted
    # fine. A harness bug scored as a finding is worse than no test.
    try:
        status = getattr(chi_server.get_server(name), "status", "unknown")
        record(st, f"server boots on {TEST_NODE_TYPE} with CC-Ubuntu22.04",
               status == "ACTIVE", status)
    except Exception as e:                               # noqa: BLE001
        record(st, f"server boots on {TEST_NODE_TYPE} with CC-Ubuntu22.04",
               False, f"{type(e).__name__}: {str(e)[:90]}")


def step_trap(st):
    """SPENDS. The documented trap: a LEASE id where a RESERVATION id belongs.

    The whole danger is that this is QUIET. On 2026-09-05 Nova ACCEPTED the
    lease id, created the instance, and only then let it reach ERROR - it did
    not reject the request. stub_chi/chi/server.py:36-42 models exactly that,
    and this re-confirms the model against today's stack.

    A rejection at construction would ALSO be a finding, and the opposite one:
    it would mean the stub is now wrong in the other direction. So both
    outcomes are recorded rather than only the expected one.
    """
    require(lease_id=st.get("lease_id"))
    authenticate()
    use_site()
    from chi import server as chi_server
    lease_id = st["lease_id"]
    name = f"goldtest-trap-{datetime.datetime.now():%H%M%S}"

    try:
        bad = chi_server.Server(name, image_name="CC-Ubuntu22.04",
                                reservation_id=lease_id,   # WRONG on purpose
                                key_name=KEYPAIR_NAME)
        bad.submit(idempotent=True, show="text", wait_for_active=False)
        st["servers"].append({"id": getattr(bad, "id", None), "name": name})
        save_state(st)
        print(f"server {name} ACCEPTED with a lease id - registered for teardown")
    except Exception as e:                               # noqa: BLE001
        record(st, "lease-id-as-reservation-id is REJECTED at submit", True,
               f"rejected loudly: {type(e).__name__}: {str(e)[:80]} - "
               "STUB IS NOW WRONG, it models this as quiet")
        return

    # Accepted. Did it then fail, as the stub says it does?
    status = "unknown"
    try:
        bad.wait_for_active()
        status = "ACTIVE"
    except Exception as e:                               # noqa: BLE001
        status = f"{type(e).__name__}: {str(e)[:80]}"
    try:
        status = getattr(chi_server.get_server(name), "status", status)
    except Exception:                                    # noqa: BLE001
        pass
    record(st, "lease-id-as-reservation-id is REJECTED at submit", False,
           f"ACCEPTED, reached {status} - quiet failure, as the stub models")


def step_teardown(st):
    """Delete everything registered. Safe to run repeatedly, and unconditional."""
    authenticate()
    use_site()
    from chi import lease as chi_lease
    from chi import server as chi_server

    for rec in list(st["servers"]):
        try:
            chi_server.get_server(rec["name"]).delete()
            print(f"  deleted server {rec['name']}")
            st["servers"].remove(rec)
        except Exception as e:                           # noqa: BLE001
            print(f"  server {rec['name']}: {type(e).__name__}: {e}")
    for rec in list(st["leases"]):
        try:
            chi_lease.delete_lease(rec["id"])
            print(f"  deleted lease {rec['name']} ({rec['id']})")
            st["leases"].remove(rec)
        except Exception as e:                           # noqa: BLE001
            print(f"  lease {rec['name']}: {type(e).__name__}: {e}")
    save_state(st)

    # Sweep: anything this probe's naming convention made and lost track of.
    leftover = []
    try:
        for lz in chi_lease.list_leases():
            nm = lz["name"] if isinstance(lz, dict) else getattr(lz, "name", "")
            if nm.startswith("goldtest-"):
                leftover.append(nm)
    except Exception as e:                               # noqa: BLE001
        print(f"  sweep failed: {e}")
    print(f"\nregistry now: {len(st['leases'])} lease(s), "
          f"{len(st['servers'])} server(s)")
    print(f"goldtest-* leases still visible in the project: {leftover or 'none'}")


def step_report(st):
    doc = {**st.get("meta", {}), "results": st["results"]}
    print(f"{'result':<6} {'test':<62} detail")
    for r in st["results"]:
        print(f"{r['result']:<6} {r['test']:<62} {r['detail'][:60]}")
    RESULTS_FILE.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"\nwrote {RESULTS_FILE}")


STEPS = {"auth": step_auth, "images": step_images, "lease": step_lease,
         "trap": step_trap,
         "idioms": step_idioms, "boot": step_boot,
         "teardown": step_teardown, "report": step_report}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in STEPS:
        print(f"usage: {sys.argv[0]} {{{'|'.join(STEPS)}}}")
        return 2
    st = load_state()
    try:
        STEPS[sys.argv[1]](st)
    except Exception:                                    # noqa: BLE001
        traceback.print_exc()
        if st["leases"] or st["servers"]:
            print(f"\n!! {len(st['leases'])} lease(s) and "
                  f"{len(st['servers'])} server(s) are still registered. "
                  f"Run: python {Path(__file__).name} teardown")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
