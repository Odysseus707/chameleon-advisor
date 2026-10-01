"""author: drive and apply the authored tier of an extraction. Stage 8a.

Step 5 is the only stage that WRITES rather than derives, so it is fenced on
both sides: `--emit` builds the exact input a model sees, `--apply` validates
what came back and refuses anything the gate rejects.

WHY JSON IN, YAML OUT
The model returns JSON, never YAML. A model emitting YAML directly will sooner
or later write

    - my_lease.add_fip_reservation(1) # include a floating ip

which YAML silently truncates at the `#`, losing the comment with no error. That
is the worst failure shape available - the shortened probe is still verbatim in
the tree, so the gate passes it. JSON has no comment syntax, and yaml.safe_dump
quotes on the way out, so the class of bug cannot occur.

  python corpus_v2/tools/author.py emit A11
  python corpus_v2/tools/author.py apply A11 --json out.json
  python corpus_v2/tools/author.py status
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from select_wing import (ARTIFACTS_DIR, WING, load_registry,      # noqa: E402
                         render_artifact)

EXTRACTIONS_DIR = WING / "extractions"
GROUNDING_DIR = WING / "grounding"

README_CHARS = 1400          # framing is useful; the whole README is not
README_CHARS_BRIEF = 420     # --brief: enough to say what it is, no more
AUTHORED_LISTS = ("preconditions", "traps_illustrated", "not_covered",
                  "memorization_probes", "uncertainties")

#: How many retrieval_tags an authored record needs.
#:
#: Was 8, set when five artifacts were authored and nothing measured routing.
#: At ninety it forced filler: reaching eight meant reaching for vocabulary
#: every artifact shares, and the measurement is unambiguous about what that
#: cost. Authoring all 90 with 11.8 tags each DROPPED tree L2 routing from
#: 25.0% to 17.5%; removing the shared-mechanics tags, leaving 7.6 each, took
#: it to 35.0%; topping those back up to 8 with mined terms pushed it back
#: down to 30.0%. Fewer, sharper tags beat more tags, twice, in the same run.
MIN_RETRIEVAL_TAGS = 5

#: Tags that describe HOW an artifact provisions rather than WHAT it is.
#:
#: Every artifact in this corpus takes a lease, most run in Jupyter, most name
#: a site. `jupyter` reached 58 of 90 artifacts, `floating ip` 32, a site name
#: 60. A tag true of most artifacts identifies none of them, and IDF discounts
#: it without ever removing the noise it adds to every query.
#:
#: The registry loader already refused site names on the FALLBACK path for
#: exactly this reason (registry.py: "every artifact at a site carries the same
#: one, so it separates nothing and only dilutes the tags that do"). This is
#: that same rule, applied to the authored path where it was missing.
MECHANICS_TAGS = {
    "jupyter", "notebook", "lease", "floating ip", "reservation", "idempotent",
    "get_lease", "add_flavor_reservation", "add_node_reservation", "flavor",
    "tutorial", "teaching", "reproduction", "reproducible", "reproducing",
    "reproduced", "trovi", "available_nodes", "start_date", "wait_for_active",
    "choose_site", "use_site", "Lease", "Server", "create_server",
    "delete_server", "keystoneauth1", "blazarclient", "openstack",
    "virtual machine", "bare metal", "experiment", "training",
    "advance reservation", "cleanup", "blazar",
    "CHI@UC", "CHI@TACC", "KVM@TACC", "CHI@Edge",
}


def emit(rec, brief: bool = False) -> str:
    import yaml
    doc = yaml.safe_load(
        (EXTRACTIONS_DIR / f"{rec['id']}.yaml").read_text(encoding="utf-8"))
    ground = (GROUNDING_DIR / f"{rec['id']}.md").read_text(encoding="utf-8")
    body = ground.split("\n---\n", 1)[0]
    body = "\n".join(l for l in body.splitlines() if not l.startswith("<!--"))

    out = [f"### {rec['id']}  {rec['trovi_title']}",
           f"repo {rec['repo_url']} @ {rec['pinned_sha'][:10]}",
           f"site_observed={rec['site_observed']}  "
           f"nodes={rec['node_types_observed']}  "
           f"flavors={rec['flavors_observed']}  gpus={rec['gpus_mentioned']}",
           f"images={rec['image_observed']}  lease_h={rec['lease_hours_declared']}  "
           f"api_family={rec['api_family']}  era={rec['python_chi_era']}",
           f"record_type={rec['record_type']}  "
           f"workload_tags={rec['workload_tags']}",
           "", "--- README (truncated) ---", body[:(README_CHARS_BRIEF if brief else README_CHARS)].strip(), ""]

    out.append("--- workflow_stages ---")
    for s in doc["workflow_stages"]:
        out.append(f"[{s['stage']}] {s['source_ref']}")
        out.append(s["verbatim_code"])
        out.append("")
    out.append("--- api_calls ---")
    for c in doc["api_calls"]:
        out.append(f"  {c['module'] or '-'}.{c['function']}"
                   f"({c['exact_kwargs_as_used'][:90]})")
    out.append("--- magic_strings ---")
    for m in doc["magic_strings"]:
        out.append(f"  {m['kind']:<13} {m['value']!r}")
    return "\n".join(out)


def apply(rec, payload: dict) -> list[str]:
    """Write the authored fields. Returns validation errors, writing nothing
    if there are any - a half-applied record reads as reviewed."""
    import yaml
    errs = []
    if not str(payload.get("summary", "")).strip():
        errs.append("summary is empty")
    for f in AUTHORED_LISTS:
        v = payload.get(f)
        if not isinstance(v, list) or not v:
            errs.append(f"{f} must be a non-empty list")
        elif any(not str(x).strip() for x in v):
            errs.append(f"{f} contains an empty entry")
    for f in ("retrieval_tags", "workload_tags"):
        if not isinstance(payload.get(f), list):
            errs.append(f"{f} must be a list")
    # Demoted tags describe the KIND of record, not the workload, and live in
    # record_type. Caught here rather than by a later test, because by then the
    # bad value is already written and looks reviewed.
    from select_wing import DEMOTED_TO_RECORD_TYPE
    for t in payload.get("workload_tags") or []:
        if t in DEMOTED_TO_RECORD_TYPE:
            errs.append(f"workload_tag {t!r} is a record_type, not a workload")
    tags = payload.get("retrieval_tags") or []
    if len(tags) < MIN_RETRIEVAL_TAGS:
        errs.append(f"retrieval_tags: need at least {MIN_RETRIEVAL_TAGS}, "
                    f"got {len(tags)}")
    mech = sorted(set(tags) & MECHANICS_TAGS)
    if mech:
        errs.append(f"retrieval_tags name how it provisions, not what it is: "
                    f"{mech}. A tag true of most artifacts identifies none.")
    if errs:
        return errs

    ep = EXTRACTIONS_DIR / f"{rec['id']}.yaml"
    doc = yaml.safe_load(ep.read_text(encoding="utf-8"))
    doc["summary"] = payload["summary"].strip()
    for f in AUTHORED_LISTS:
        doc[f] = [str(x) for x in payload[f]]
    from extract import render
    ep.write_text(render(doc), encoding="utf-8")

    rec["retrieval_tags"] = [str(t) for t in payload["retrieval_tags"]]
    if payload.get("workload_tags"):
        rec["workload_tags"] = [str(t) for t in payload["workload_tags"]]
    (ARTIFACTS_DIR / f"{rec['id']}.yaml").write_text(
        render_artifact(rec), encoding="utf-8")
    return []


#: Stratification axes for the authored subset.
#:
#: Authoring all 91 commits effort before Part 2 has shown which authored fields
#: its checkers actually consume. A stratified subset validates the pipeline and
#: gives item-writing real material across every kind of artifact, at a fraction
#: of the cost, and the rest can follow once the requirement is known.
STRATA = ("record_type", "api_family")


def plan(target: int) -> int:
    """Choose a stratified subset, deterministically.

    Every stratum gets at least one artifact, so no kind of artifact is
    invisible to item-writing - `reproducible-research x baremetal` is 44 of 91
    and would otherwise swallow a proportional sample whole. The remaining
    budget is then allocated in proportion to stratum size, so the common case
    is still represented in proportion to how common it is.

    Within a stratum, richer artifacts come first: tier, then number of
    provisioning code units. An artifact with more provisioning is worth more to
    someone writing questions about provisioning.
    """
    import yaml
    reg = load_registry()
    arts = reg["artifacts"]
    done = set()
    for r in arts:
        d = yaml.safe_load(
            (EXTRACTIONS_DIR / f"{r['id']}.yaml").read_text(encoding="utf-8"))
        if d.get("summary"):
            done.add(r["id"])

    # One artifact per content group. Six repo+commit pairs back 15 of the 91,
    # so their grounding is byte-identical; authoring the duplicates produces
    # near-identical prose and buys nothing. Prefer the already-authored member,
    # then the richest, so a group is represented by its best exemplar.
    seen_groups: set = set()
    rank0 = {"A": 0, "B": 1, "C": 2}
    pool = []
    for r in sorted(arts, key=lambda r: (r["id"] not in done,
                                         rank0.get(r["tier"], 9),
                                         -int(r.get("n_provisioning_cells") or 0),
                                         r["id"])):
        g = r.get("content_group") or r["id"]
        if g in seen_groups:
            continue
        seen_groups.add(g)
        pool.append(r)

    cells: dict[tuple, list] = {}
    for r in pool:
        cells.setdefault(tuple(r[k] for k in STRATA), []).append(r)
    rank = {"A": 0, "B": 1, "C": 2}
    for v in cells.values():
        v.sort(key=lambda r: (rank.get(r["tier"], 9),
                              -int(r.get("n_provisioning_cells") or 0),
                              r["id"]))

    quota = {k: 1 for k in cells}
    left = target - len(cells)
    order = sorted(cells, key=lambda k: (-len(cells[k]), k))
    total = sum(len(v) for v in cells.values())
    for k in order:
        if left <= 0:
            break
        extra = min(left, max(0, round(len(cells[k]) / total * (target - len(cells)))),
                    len(cells[k]) - quota[k])
        quota[k] += extra
        left -= extra
    for k in order:                      # spend any rounding remainder
        while left > 0 and quota[k] < len(cells[k]):
            quota[k] += 1
            left -= 1

    chosen = []
    for k in order:
        want = quota[k]
        # Already-authored artifacts count toward their stratum's quota.
        have = [r for r in cells[k] if r["id"] in done]
        chosen += [r["id"] for r in have][:want]
        for r in cells[k]:
            if len(chosen) >= sum(quota.values()):
                break
            if r["id"] not in done and \
                    sum(1 for c in chosen if c in {x["id"] for x in cells[k]}) < want:
                chosen.append(r["id"])

    order_by_id = {r["id"]: r for r in pool}
    chosen = sorted(set(chosen), key=lambda i: int(i[1:]))
    print(f"stratified subset: {len(chosen)} of {len(pool)} distinct-content "
          f"artifacts ({len(arts)} total, {len(arts) - len(pool)} are duplicates "
          f"of another)\n  {len(cells)} strata, all represented\n")
    print(f"  {'stratum':<38}{'quota':>6}{'picked'}")
    for k in order:
        picked = [i for i in chosen if tuple(order_by_id[i][x] for x in STRATA) == k]
        print(f"  {' x '.join(k):<38}{quota[k]:>6}  {' '.join(picked)}")
    todo = [i for i in chosen if i not in done]
    print(f"\n  already authored: {len([i for i in chosen if i in done])}")
    print(f"  to author       : {len(todo)}")
    print("  " + " ".join(todo))
    return 0


def status() -> int:
    """Authored is not the same as accepted.

    `apply` writes before the gate runs, so a rejected record still sits in the
    files. Counting those as done would report progress that does not exist -
    the whole point of the gate is that ungated prose is not evidence. So status
    reports three states, and only `accepted` counts.
    """
    import yaml
    from verify_authored import check, tree_text
    from catalog import normalize_repo
    from fetch import repo_dir

    reg = load_registry()
    accepted, rejected, todo = [], [], []
    for r in reg["artifacts"]:
        d = yaml.safe_load(
            (EXTRACTIONS_DIR / f"{r['id']}.yaml").read_text(encoding="utf-8"))
        if not d.get("summary"):
            todo.append(r["id"])
            continue
        ground = (GROUNDING_DIR / f"{r['id']}.md").read_text(encoding="utf-8")
        fails = check(r, d, tree_text(repo_dir(normalize_repo(r["repo_url"]))),
                      ground)
        (rejected if fails else accepted).append(r["id"])
    n = len(reg["artifacts"])
    print(f"accepted {len(accepted)}/{n}   rejected {len(rejected)}   "
          f"unauthored {len(todo)}")
    if rejected:
        print("REJECTED (authored but not gated - do not count these):",
              " ".join(rejected))
    if todo:
        print("remaining:", " ".join(todo))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("emit", "apply", "status", "plan"))
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--brief", action="store_true",
                    help="shorter README excerpt, for batching many artifacts")
    args = ap.parse_args()
    if args.cmd == "status":
        return status()
    if args.cmd == "plan":
        return plan(int(args.ids[0]) if args.ids else 25)
    reg = {r["id"]: r for r in load_registry()["artifacts"]}
    if args.cmd == "emit":
        for i, aid in enumerate(args.ids):
            if aid not in reg:
                raise SystemExit(f"unknown id {aid}")
            print(("\n" + "=" * 78 + "\n") if i else "", end="")
            print(emit(reg[aid], args.brief))
        return 0
    payloads = json.loads(args.json.read_text(encoding="utf-8"))
    bad = 0
    for aid, payload in payloads.items():
        errs = apply(reg[aid], payload)
        print(f"{aid:<5} {'ok' if not errs else 'INVALID'}")
        for e in errs:
            print(f"      x {e}")
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
