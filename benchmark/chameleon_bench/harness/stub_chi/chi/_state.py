"""Shared state for the bare-metal execution stub.

WHAT THIS IS FOR
An AST checker proves an answer has the right SHAPE. It cannot prove the answer
would do the right THING. This stub runs the answer against the real recorded
state of the testbed and records what it actually did, so "the golds are
verified" means the gold was executed and its effect compared to an expectation
- not that it parsed.

WHAT IS AN ERROR AND WHAT IS MERELY RECORDED
  hard error   naming hardware that does not exist at the site you selected.
               gpu_rtx_6000 lives at CHI@UC and nowhere else; asking CHI@TACC
               for one is wrong in a way no amount of waiting fixes.
  recorded     the type exists but nothing is free right now. That is a
               scheduling fact, not a mistake in the code, and it is the
               reservation suite's question rather than this suite's. Blazar
               itself accepts such a lease; it simply does not start yet.

Conflating the two would make every core gold fail whenever the testbed happens
to be busy, which would make the suite measure the calendar.
"""
import atexit
import json
import os
from pathlib import Path

TRACE = {
    "site": None,
    "project": None,
    "leases": [],
    "servers": [],
    "notes": [],
}

_SNAPSHOTS = {}


def snapshot_dir() -> Path:
    return Path(os.environ["CHI_SNAPSHOT_DIR"])


def _load_site(site: str) -> dict:
    """{node_type: {"free": n, "total": n}} for one site, from the real capture."""
    if site in _SNAPSHOTS:
        return _SNAPSHOTS[site]
    for p in sorted(snapshot_dir().glob("*.json")):
        if p.name.startswith("_"):
            continue
        doc = json.loads(p.read_text())
        meta = doc.get("_meta", {})
        if meta.get("site") != site:
            continue
        counts = {}
        for d in doc["devices"]:
            t = d.get("node_type") or d.get("device_type")
            c = counts.setdefault(t, {"free": 0, "total": 0})
            c["total"] += 1
            if d.get("free"):
                c["free"] += 1
        _SNAPSHOTS[site] = counts
        return counts
    raise RuntimeError(
        f"no snapshot for site {site!r} under {snapshot_dir()}. The stub refuses "
        "to pretend a site exists: an answer graded against an absent snapshot "
        "would pass for naming anything at all.")


def known_sites() -> list:
    out = []
    for p in sorted(snapshot_dir().glob("*.json")):
        if p.name.startswith("_"):
            continue
        s = json.loads(p.read_text()).get("_meta", {}).get("site")
        if s:
            out.append(s)
    return out


def require_site() -> str:
    if TRACE["site"] is None:
        raise RuntimeError(
            "no site selected. Call chi.use_site(...) or context.use_site(...) "
            "before reserving: bare-metal hardware is per-site, and a "
            "reservation with no site is not a request anyone can fill.")
    return TRACE["site"]


def set_site(name):
    if name is None:
        return None
    sites = known_sites()
    if name not in sites:
        raise RuntimeError(
            f"unknown site {name!r}; this capture covers {sites}.")
    TRACE["site"] = name
    return name


def check_node_type(node_type: str):
    """Hard-error on hardware absent from the selected site. Record scarcity."""
    site = require_site()
    counts = _load_site(site)
    if node_type not in counts:
        raise RuntimeError(
            f"node_type {node_type!r} does not exist at {site}. Types there: "
            f"{sorted(counts)}. This is a cross-site mistake, not a busy "
            "testbed - waiting will never produce one.")
    c = counts[node_type]
    if c["free"] == 0:
        TRACE["notes"].append(
            f"{node_type} at {site}: 0 of {c['total']} free at capture time; "
            "the lease is well-formed but would not start immediately")
    return c


@atexit.register
def _dump():
    out = os.environ.get("CHI_TRACE")
    if out:
        Path(out).write_text(json.dumps(TRACE, indent=1))

#: Addresses handed out by fip reservations, so a Server can tell a
#: reserved address from an arbitrary one.
RESERVED_FIPS = set()
