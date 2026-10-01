"""extract: pinned tree -> one structured extraction per artifact. Stage 7.

Deterministic, AST-based, no LLM. Every field here is a fact that can be
re-derived from the pinned commit and checked against it, which is what makes
the authored tier (Step 5) auditable: prose is only allowed to describe things
that already appear in this file.

SCHEMA - the key order of chi_edge_bench/data/extractions/A1.yaml, so both wings
read identically:

    artifact_id / repo_url / commit_hash / api_generation
    summary               <- authored, Step 5
    workflow_stages       one entry per provisioning code unit, in file order
    api_calls             module, function, kwargs as literally written
    magic_strings         resource literals with their kind
    preconditions ... uncertainties   <- authored, Step 5

STAGES. The edge wing used site/auth, lease, container, exec, teardown, other -
a container vocabulary. Bare metal needs `server` (instance launch), `network`
(floating IPs), `image` and `storage`, so those are added rather than forced
into `other`. A code unit gets ONE stage: the most specific one present, by
STAGE_PRECEDENCE. `create_container` beats `get_device_reservation` in the same
cell because launching is what that cell is for, which is how A1 labels it.

WHAT THIS DELIBERATELY DOES NOT DO
No summary, no traps, no "not covered". Those require judgement and are Step 5's
job. Emitting a machine-written summary here would produce something that reads
like analysis and is not, which is worse than leaving the field null.

  python corpus_v2/tools/extract.py run
  python corpus_v2/tools/extract.py run --dry-run
  python corpus_v2/tools/extract.py run --only A7
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=SyntaxWarning)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from detect import (STRONG_CALLS, WEAK_CALLS,                     # noqa: E402
                    WEAK_CONSTRUCTORS, _strip_magics)
from rank import FLAVOR_RE, GPU_RE, NODE_TYPE_RE, SITE_RE         # noqa: E402
from render_grounding import (has_provisioning, read_text,        # noqa: E402
                              verify_pin, walk)
from select_wing import (ARTIFACTS_DIR, WING, WORKSPACE,          # noqa: E402
                         load_registry, render_artifact)

EXTRACTIONS_DIR = WING / "extractions"

# ---------------------------------------------------------------- stages

STAGE_CALLS = {
    # Names here must be chi-specific. `destroy`, `terminate`, `run`, `mount`
    # and a bare `set` were in an earlier version and are removed: measured over
    # the corpus they never triggered a stage on their own, so they added no
    # coverage while leaving a live risk that Python's builtin `set()` or a
    # subprocess `run()` would silently label a cell as provisioning.
    "teardown": {"delete_lease", "destroy_container", "delete_server",
                 "delete_volume", "release_floating_ip", "detach_floating_ip",
                 "delete_image"},
    "server": {"create_server", "Server", "get_server", "get_server_id",
               "associate_server"},
    "container": {"create_container", "get_container", "Container",
                  "wait_for_active_container"},
    "image": {"create_image", "snapshot", "get_image", "create_snapshot"},
    "storage": {"attach_volume", "detach_volume", "create_volume",
                "get_volume"},
    "network": {"associate_floating_ip", "create_floating_ip",
                "get_floating_ip", "list_routers", "get_network_id",
                "bind_floating_ip", "add_route", "get_free_floating_ip"},
    "lease": {"create_lease", "lease_duration", "add_node_reservation",
              "add_flavor_reservation", "add_fip_reservation",
              "add_device_reservation", "get_lease", "wait_for_active",
              "get_node_reservation", "get_device_reservation",
              "get_flavor_id", "Lease", "get_reserved_floating_ips",
              # `Lease(...).submit()` is the current-API way to create a lease,
              # so submit belongs here and not under `server` where an earlier
              # version put it - that mislabelled 56 lease cells as server ones.
              "submit"},
    "site/auth": {"use_site", "choose_site", "choose_project"},
    "exec": {"execute", "upload", "download", "ssh"},
}

#: Most specific first. A cell doing create_container(reservation_id=get_...)
#: is a container cell, not a lease cell - that is how A1 labels it.
STAGE_PRECEDENCE = ["teardown", "server", "container", "image", "storage",
                    "network", "lease", "site/auth", "exec"]

# ---------------------------------------------------------------- literals

RESOURCE_KWARGS = {
    "node_type": {"node_type"},
    "machine_type": {"machine_name", "machine_type"},
    "flavor": {"flavor_name", "flavor", "flavor_id"},
    "image_ref": {"image_ref", "image", "image_name"},
    "port": {"exposed_ports", "port"},
    "device_profile": {"device_profiles", "device_profile"},
    "count": {"count", "amount", "node_count"},
}

#: Caps. A1 is 307 lines; an artifact with 500 call sites would produce a file
#: nobody reads and would bury the authored tier underneath it.
MAX_STAGES, MAX_CALLS, MAX_STRINGS = 40, 60, 40
MAX_CODE_CHARS = 1200


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def terminal_name(func) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def dotted_name(func) -> str:
    """`chi.lease.create_lease` from the AST, as written in the source."""
    parts, node = [], func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def literal(node):
    if isinstance(node, ast.Constant) and isinstance(
            node.value, (str, int, float, bool)):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        vals = [literal(e) for e in node.elts]
        return vals if all(v is not None for v in vals) else None
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values
                       if isinstance(v, ast.Constant)
                       and isinstance(v.value, str))
    return None


def classify(calls: set[str]) -> str:
    for stage in STAGE_PRECEDENCE:
        if calls & STAGE_CALLS[stage]:
            return stage
    return "other"


def _expr(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "<expr>"


def render_kwargs(call: ast.Call) -> str:
    """The arguments as literally written, which is the point of the field.

    A1 records `exact_kwargs_as_used: days=1` and `'"CHI@Edge"  (positional)'`.
    Normalising these would destroy the evidence a checker later needs: whether
    an artifact passed platform_version=2 is exactly the sort of thing that must
    not be paraphrased.
    """
    bits = []
    for a in call.args:
        v = literal(a)
        bits.append(f"{v!r} (positional)" if v is not None
                    else f"{_expr(a)} (positional)")
    for kw in call.keywords:
        if kw.arg is None:
            bits.append("**kwargs")
            continue
        v = literal(kw.value)
        bits.append(f"{kw.arg}={v!r}" if v is not None
                    else f"{kw.arg}={_expr(kw.value)}")
    return ", ".join(bits)


def code_units(repo: Path):
    """(source, source_ref) for every provisioning code unit in the tree."""
    for p, rel in walk(repo):
        suffix = p.suffix.lower()
        posix = rel.as_posix()
        if suffix == ".ipynb":
            try:
                nb = json.loads(read_text(p) or "{}")
            except (json.JSONDecodeError, RecursionError):
                continue
            n = 0
            for c in nb.get("cells", []):
                if not isinstance(c, dict) or c.get("cell_type") != "code":
                    continue
                n += 1
                src = c.get("source", "")
                src = "".join(src) if isinstance(src, list) else str(src)
                if src.strip() and has_provisioning(src):
                    yield src, f"{posix} cell {n}"
        elif suffix == ".py":
            src = read_text(p)
            if src.strip() and has_provisioning(src):
                yield src, posix


def extract_one(repo: Path, rec: dict) -> dict:
    stages, calls_out, strings = [], [], []
    seen: set[tuple] = set()
    era_current = era_legacy = 0

    units = list(code_units(repo))

    for src, ref in units:
        try:
            tree = ast.parse(_strip_magics(src))
        except (SyntaxError, ValueError, RecursionError):
            continue
        unit_calls, unit_nodes = set(), []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = terminal_name(node.func)
            if not name:
                continue
            unit_calls.add(name)
            if name in STRONG_CALLS or name in WEAK_CALLS \
                    or name in WEAK_CONSTRUCTORS:
                unit_nodes.append(node)
        if not unit_nodes:
            continue

        if unit_calls & {"choose_site", "choose_project", "submit"}:
            era_current += 1
        if unit_calls & {"use_site", "create_lease", "create_container"}:
            era_legacy += 1

        code = src.strip()
        stages.append({
            "stage": classify(unit_calls),
            "verbatim_code": (code if len(code) <= MAX_CODE_CHARS
                              else code[:MAX_CODE_CHARS] + "\n# ...truncated"),
            "source_ref": ref,
        })

        for node in unit_nodes:
            dotted = dotted_name(node.func)
            module = dotted.rsplit(".", 1)[0] if "." in dotted else ""
            calls_out.append({
                "module": module or None,
                "function": terminal_name(node.func),
                "exact_kwargs_as_used": render_kwargs(node) or "(no arguments)",
                "source_ref": ref,
            })
            for kw in node.keywords:
                if kw.arg is None:
                    continue
                val = literal(kw.value)
                if val is None or (isinstance(val, str) and not val.strip()):
                    continue
                for kind, names in RESOURCE_KWARGS.items():
                    if kw.arg in names and (str(val), kind) not in seen:
                        seen.add((str(val), kind))
                        strings.append({"value": val, "kind": kind,
                                        "source_ref": ref})

    # Vocabulary sweep for literals that are never passed as a kwarg - a node
    # type named only in prose or an f-string still tells the advisor what this
    # artifact runs on. Kept separate from the AST pass because it is weaker
    # evidence, and the `kind` says which is which.
    for src, ref in units:
        for regex, kind in ((SITE_RE, "site"), (NODE_TYPE_RE, "node_type"),
                            (FLAVOR_RE, "flavor"), (GPU_RE, "gpu")):
            for m in regex.finditer(src):
                v = m.group(1)
                if (v, kind) not in seen:
                    seen.add((v, kind))
                    strings.append({"value": v, "kind": kind,
                                    "source_ref": ref})

    api_generation = ("current" if era_current > era_legacy else
                      "imperative" if era_legacy else "unknown")

    truncated = {label: len(seq)
                 for label, seq, cap in
                 (("workflow_stages", stages, MAX_STAGES),
                  ("api_calls", calls_out, MAX_CALLS),
                  ("magic_strings", strings, MAX_STRINGS))
                 if len(seq) > cap}

    return {
        "artifact_id": rec["id"],
        "trovi_slug": rec["artifact_id"],
        "repo_url": rec["repo_url"],
        "commit_hash": rec["pinned_sha"],
        "api_generation": api_generation,
        # Authored tier, filled by Step 5. Present and empty so the schema is
        # complete and a test can assert nothing was invented here.
        "summary": None,
        "workflow_stages": stages[:MAX_STAGES],
        "api_calls": calls_out[:MAX_CALLS],
        "magic_strings": strings[:MAX_STRINGS],
        "preconditions": [],
        "traps_illustrated": [],
        "not_covered": [],
        "memorization_probes": [],
        "uncertainties": [],
        "_truncated": truncated or None,
    }


class _LiteralDumper(__import__("yaml").SafeDumper):
    """Emit multi-line strings as `|` blocks, the way A1.yaml reads.

    Without this, safe_dump renders verbatim_code as one double-quoted string
    with \n and \t escapes - technically correct, unreadable in review, and
    visibly different from the edge wing's extractions. verbatim_code is the
    field a human most needs to be able to skim.
    """


def _literal_str(dumper, data):
    if "\n" in data:
        # A trailing-space line makes `|` illegal, so those are trimmed. This
        # changes whitespace only, never a token a checker could match on.
        data = "\n".join(line.rstrip() for line in data.split("\n"))
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_LiteralDumper.add_representer(str, _literal_str)


def render(doc: dict) -> str:
    import yaml
    head = f"""\
# {doc['artifact_id']} - {doc['trovi_slug']}
#
# DETERMINISTIC TIER, generated by corpus_v2/tools/extract.py from
# {doc['repo_url']} @ {doc['commit_hash']}
# Every value below is an AST fact re-derivable from that commit.
#
# summary / preconditions / traps_illustrated / not_covered /
# memorization_probes / uncertainties are the AUTHORED tier and are filled by
# Step 5, which may only describe things already present in this file.
"""
    return head + yaml.dump(doc, Dumper=_LiteralDumper, sort_keys=False,
                            default_flow_style=False, allow_unicode=True,
                            width=100)


#: Written by Step 5, never by this tool - but this tool rewrites the file they
#: live in, so it has to preserve them.
AUTHORED_FIELDS = ("summary", "preconditions", "traps_illustrated",
                   "not_covered", "memorization_probes", "uncertainties")


def _carry_authored_forward(path: Path, doc: dict) -> None:
    """Keep Step 5's prose across a re-extraction.

    extract.py rebuilds the whole document from the AST, so without this a
    routine re-run silently deletes every authored summary, trap and probe. It
    has happened: a verification pass that ran extract.py wiped 22 authored
    records, and the loss was invisible because the file still looked complete -
    just with summary back to null.

    Third instance of this same shape (select_wing vs pin, select_wing vs
    grounding, now extract vs authored). The rule is simple and absolute: a tool
    that rewrites a shared file must carry forward every field it does not own.
    """
    if not path.exists():
        return
    import yaml
    old = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key in AUTHORED_FIELDS:
        if old.get(key):
            doc[key] = old[key]


def run(dry_run: bool, only: list[str]) -> int:
    reg = load_registry()
    records = [r for r in reg["artifacts"] if not only or r["id"] in only]
    EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[extract] {len(records)} artifacts\n")

    wrote = unchanged = 0
    empty, truncated = [], []
    n_stages = n_calls = n_strings = 0
    stage_tally: dict[str, int] = {}

    for rec in records:
        repo, why = verify_pin(rec)
        if repo is None:
            empty.append((rec["id"], why))
            continue
        doc = extract_one(repo, rec)
        if not doc["workflow_stages"]:
            empty.append((rec["id"], "no provisioning code unit parsed"))
            continue
        if doc["_truncated"]:
            truncated.append(rec["id"])
        n_stages += len(doc["workflow_stages"])
        n_calls += len(doc["api_calls"])
        n_strings += len(doc["magic_strings"])
        for s in doc["workflow_stages"]:
            stage_tally[s["stage"]] = stage_tally.get(s["stage"], 0) + 1

        _carry_authored_forward(EXTRACTIONS_DIR / f"{rec['id']}.yaml", doc)
        text = render(doc)
        rec["extraction_sha256"] = sha256_text(text)
        rec["extraction_calls"] = len(doc["api_calls"])
        if dry_run:
            continue
        path = EXTRACTIONS_DIR / f"{rec['id']}.yaml"
        if path.exists() and path.read_text(encoding="utf-8") == text:
            unchanged += 1
        else:
            path.write_text(text, encoding="utf-8")
            wrote += 1
        apath = ARTIFACTS_DIR / f"{rec['id']}.yaml"
        atext = render_artifact(rec)
        if apath.read_text(encoding="utf-8") != atext:
            apath.write_text(atext, encoding="utf-8")

    ok = len(records) - len(empty)
    print(f"  extracted  {ok}/{len(records)}")
    print(f"  stages     {n_stages} total, by kind: "
          f"{dict(sorted(stage_tally.items(), key=lambda kv: -kv[1]))}")
    print(f"  api_calls  {n_calls}   magic_strings {n_strings}")
    if truncated:
        print(f"  capped     {len(truncated)}: {', '.join(truncated[:10])}")
    if empty:
        print(f"\n  NO EXTRACTION ({len(empty)}):")
        for aid, why in empty:
            print(f"    {aid:<5} {why}")
        print("  These artifacts are in the wing because triage found")
        print("  provisioning; an empty extraction means this tool cannot see")
        print("  it - usually non-Python setup. Worth checking before Step 5.")
    if dry_run:
        print("\n[dry-run] nothing written")
        return 0
    print(f"\n[written] {wrote} new/changed, {unchanged} unchanged -> "
          f"{EXTRACTIONS_DIR.relative_to(WORKSPACE)}/A*.yaml")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("run",))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", nargs="*", default=[])
    args = ap.parse_args()
    return run(args.dry_run, args.only)


if __name__ == "__main__":
    raise SystemExit(main())
