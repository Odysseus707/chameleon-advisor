"""
Checker library for CHI@Edge Coding Benchmark v4.

Design rules (see benchmark_v4_decisions.md):
- D01: generation equivalence. Kwarg aliases pair OO/imperative names
       ([machine_type, machine_name], [amount, count], [image_ref, image]).
       create_container() additionally requires platform_version (imperative rule).
- D03: every check carries a group tag: mechanism | specifics | safety.
- D10: forbidden-call checks are AST-level only; string checks run on code
       blocks only, never prose.

Every check function returns (passed: bool, detail: str).
"""

import ast
import re

KNOWN_PROFILES = {"pi_libcamera", "pi_sensehat", "pi_gpio"}

CONTAINER_CREATORS = {"Container", "create_container"}
LEASE_CREATORS = {"Lease", "create_lease"}

ABSTAIN_PATTERNS = [
    r"(no|not a|isn'?t a|there is no)\s+(dedicated|documented|known|such)\s+(device[_ ]?profile|profile|artifact|machine[_ ]?type)",
    r"not (covered|documented|supported|available) (in|by|on)",
    r"i (don'?t|do not|cannot|can'?t) (know|confirm|verify|determine)",
    r"(check|inspect|query|list)\s+(the\s+)?(supported_device_profiles|available (device )?profiles|hardware browser|device (calendar|inventory))",
    r"(would need|need) to (check|verify|confirm|ask)",
    r"no (chi@edge )?(trovi )?artifact (covers|demonstrates|documents)",
]


# ---------------------------------------------------------------- AST helpers

def _parse(code: str):
    try:
        return ast.parse(code)
    except SyntaxError:
        return None


def _terminal_name(func) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _calls(tree):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]


def _calls_named(tree, names):
    names = {names} if isinstance(names, str) else set(names)
    return [c for c in _calls(tree) if _terminal_name(c.func) in names]


def _const(node):
    """Extract a python value from a Constant / List / Dict of constants; None otherwise."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        vals = [_const(e) for e in node.elts]
        return vals if all(v is not None or isinstance(e, ast.Constant)
                           for v, e in zip(vals, node.elts)) else vals
    if isinstance(node, ast.Dict):
        return {_const(k): _const(v) for k, v in zip(node.keys, node.values)
                if isinstance(k, ast.Constant)}
    return None


def _name_env(tree):
    """Map top-level simple assignments name -> constant-ish value (str, list, dict)."""
    env = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            v = _const(node.value)
            if v is None and isinstance(node.value, ast.JoinedStr):
                v = "".join(p.value for p in node.value.values
                            if isinstance(p, ast.Constant))
            if v is not None:
                env[node.targets[0].id] = v
    return env


def _kw(call, aliases, env):
    """Return (found, value) for the first keyword matching any alias, resolving
    simple Name references through env."""
    aliases = [aliases] if isinstance(aliases, str) else list(aliases)
    for kw in call.keywords:
        if kw.arg in aliases:
            v = _const(kw.value)
            if v is None and isinstance(kw.value, ast.Name):
                v = env.get(kw.value.id)
            if v is None and isinstance(kw.value, ast.JoinedStr):
                v = "".join(p.value for p in kw.value.values
                            if isinstance(p, ast.Constant))
            return True, v
    return False, None


def _flat_str(v):
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        return " ".join(str(x) for x in v)
    return str(v)


# ---------------------------------------------------------------- the checks
# Each check_* takes (ctx, **params). ctx = {"tree", "code", "text", "env"}.

def check_required_call(ctx, name=None, any=None, min_count=1):
    names = [name] if name else list(any)
    hits = _calls_named(ctx["tree"], names) if ctx["tree"] else []
    ok = len(hits) >= min_count
    return ok, f"calls to {names}: {len(hits)} (need >= {min_count})"


def check_forbidden_calls(ctx, names=()):
    if not ctx["tree"]:
        return True, "no parseable code; nothing forbidden invoked"
    bad = sorted({_terminal_name(c.func) for c in _calls_named(ctx["tree"], names)})
    return (not bad), (f"forbidden calls present: {bad}" if bad else "clean")


def check_kwarg(ctx, call, arg, equals=None, equals_any=None, contains=None,
                contains_all=None, present=None, keys_include=None):
    """Find a call named in `call` (str or list) carrying keyword `arg` (aliases ok)
    and test its value."""
    calls = _calls_named(ctx["tree"], call) if ctx["tree"] else []
    if not calls:
        return False, f"no call named {call} found"
    details = []
    for c in calls:
        found, v = _kw(c, arg, ctx["env"])
        if not found:
            continue
        if present:
            return True, f"{arg} present"
        if equals is not None and v == equals:
            return True, f"{arg}={v!r}"
        if equals_any is not None and v in equals_any:
            return True, f"{arg}={v!r}"
        if contains is not None and isinstance(v, (list, tuple, str)) and contains in v:
            return True, f"{arg} contains {contains!r}"
        if contains_all is not None and isinstance(v, (list, tuple)) \
                and all(x in v for x in contains_all):
            return True, f"{arg} contains all {contains_all}"
        if keys_include is not None and isinstance(v, dict) \
                and all(k in v for k in keys_include):
            return True, f"{arg} keys include {keys_include}"
        details.append(f"{arg}={v!r}")
    want = equals if equals is not None else equals_any or contains or contains_all \
        or keys_include or "present"
    return False, f"kwarg {arg} on {call}: wanted {want}, saw {details or 'missing'}"


def check_container_call(ctx, min_count=1):
    """A container is created via Container(...) or create_container(...).
    Imperative rule (D01): create_container must carry platform_version."""
    if not ctx["tree"]:
        return False, "no parseable code"
    hits = _calls_named(ctx["tree"], CONTAINER_CREATORS)
    if len(hits) < min_count:
        return False, f"container-creation calls: {len(hits)} (need >= {min_count})"
    for c in hits:
        if _terminal_name(c.func) == "create_container":
            found, _ = _kw(c, "platform_version", ctx["env"])
            if not found:
                return False, "create_container without platform_version (imperative rule)"
    return True, f"{len(hits)} container-creation call(s), generation rules satisfied"


def check_reservation_wiring(ctx):
    """reservation_id kwarg on the container call AND it is derived from the lease:
    either get_device_reservation(...) is called or .device_reservations is accessed."""
    if not ctx["tree"]:
        return False, "no parseable code"
    hits = _calls_named(ctx["tree"], CONTAINER_CREATORS)
    if not hits:
        return False, "no container-creation call"
    has_kw = any(_kw(c, "reservation_id", ctx["env"])[0] for c in hits)
    if not has_kw:
        return False, "reservation_id kwarg missing on container call"
    derived = bool(_calls_named(ctx["tree"], "get_device_reservation")) \
        or "device_reservations" in ctx["code"]
    return derived, ("reservation_id wired from lease" if derived
                     else "reservation_id present but not derived from the lease "
                          "(no get_device_reservation / device_reservations)")


# ------------------------------------------------- bare-metal grammar
# Added for the chameleon wing. Purely additive: no edge item references these,
# and parity Level 2 rescores every collected answer to prove no edge verdict
# moved. The edge equivalents (container_call, reservation_wiring) stay exactly
# as they were - a bare-metal server is not a container with different words.

SERVER_CREATORS = {"Server", "create_server"}

#: How a node reservation id is legitimately obtained from a lease.
NODE_RESERVATION_SOURCES = {"get_node_reservation"}
NODE_RESERVATION_ATTRS = ("node_reservations", "get_reserved_flavors")


def check_server_call(ctx, min_count=1):
    """A bare-metal instance is created via Server(...) or create_server(...).

    Deliberately has no platform_version rule. That kwarg is a CHI@Edge
    container requirement (D01); requiring it here would fail every correct
    bare-metal answer, and accepting it silently would let edge-shaped code pass
    as bare metal.
    """
    if not ctx["tree"]:
        return False, "no parseable code"
    hits = _calls_named(ctx["tree"], SERVER_CREATORS)
    if len(hits) < min_count:
        return False, f"server-creation calls: {len(hits)} (need >= {min_count})"
    return True, f"{len(hits)} server-creation call(s)"


def check_node_reservation_wiring(ctx):
    """reservation_id on the server call, AND derived from the lease.

    The trap this exists for is real and documented in the corpus: passing the
    LEASE id where a RESERVATION id is required. The two are different
    identifiers, the call accepts either shape, and the failure surfaces only
    when the instance never boots. Accepted derivations are
    get_node_reservation(...) or indexing .node_reservations / a reserved-flavor
    lookup for the KVM path.
    """
    if not ctx["tree"]:
        return False, "no parseable code"
    hits = _calls_named(ctx["tree"], SERVER_CREATORS)
    if not hits:
        return False, "no server-creation call"
    has_kw = any(_kw(c, "reservation_id", ctx["env"])[0] for c in hits)
    if not has_kw:
        return False, "reservation_id kwarg missing on the server call"
    derived = bool(_calls_named(ctx["tree"], NODE_RESERVATION_SOURCES)) \
        or any(a in ctx["code"] for a in NODE_RESERVATION_ATTRS)
    return derived, ("reservation_id wired from the lease" if derived
                     else "reservation_id present but not derived from the "
                          "lease (no get_node_reservation / node_reservations) "
                          "- passing the lease id here is the documented trap")


SITE_SETTERS = {"use_site"}
INTERACTIVE_SITE_SETTERS = {"choose_site"}
FLAVOR_CREATORS = {"add_flavor_reservation"}
#: How a launched flavor is shown to come from the lease rather than from thin
#: air. Every spelling here is one the corpus actually uses:
#:   l.get_reserved_flavors()[0].name          (A30, A57)
#:   my_lease.get_reserved_flavors().pop()     (A94)
#:   server.get_flavor_id(l.get_reserved_flavors()[0].name)   (A57)
RESERVED_FLAVOR_SOURCES = {"get_reserved_flavors"}


def _positional_or_kw(call, index, aliases, env):
    """Value of argument `index`, or of the first matching keyword.

    Sites are passed POSITIONALLY everywhere in this corpus - 32x
    chi.use_site('CHI@UC'), 7x context.use_site('CHI@UC'), zero as a kwarg - so
    a keyword-only reader like _kw would score every correct answer as missing.
    """
    if index < len(call.args):
        node = call.args[index]
        v = _const(node)
        if v is None and isinstance(node, ast.Name):
            v = env.get(node.id)
        if v is None and isinstance(node, ast.JoinedStr):
            v = "".join(x.value for x in node.values
                        if isinstance(x, ast.Constant))
        if v is not None:
            return True, v
    return _kw(call, aliases, env)


def check_site_correct(ctx, site=None, allow_interactive=False):
    """The answer selects the site the question is about.

    Bare metal is per-site: compute_liqid exists at CHI@TACC and not at CHI@UC,
    and a lease submitted against the wrong site fails on hardware that is
    genuinely absent rather than merely busy. Site selection is therefore part
    of a correct answer, not decoration.

    `context.choose_site()` is rejected by default. It is what 83 artifacts do,
    and it is right for a human at a notebook, but it is interactive: it commits
    to no site at all, so as an answer to "reserve a node at CHI@UC" it is a
    deferral rather than a response. Items wanting to accept it say so.
    """
    if not ctx["tree"]:
        return False, "no parseable code"
    calls = _calls_named(ctx["tree"], SITE_SETTERS)
    if not calls:
        if allow_interactive and _calls_named(ctx["tree"],
                                              INTERACTIVE_SITE_SETTERS):
            return True, "site chosen interactively (allowed by this item)"
        interactive = _calls_named(ctx["tree"], INTERACTIVE_SITE_SETTERS)
        return False, ("no use_site call; choose_site() is interactive and "
                       "names no site" if interactive else "no site selected")
    found = []
    for c in calls:
        ok, v = _positional_or_kw(c, 0, ["site", "site_name"], ctx["env"])
        if ok and v is not None:
            found.append(str(v))
    if site is None:
        return bool(found), f"site(s) selected: {found or 'none resolvable'}"
    if any(str(site) == f for f in found):
        return True, f"site {site}"
    return False, (f"site is {found or 'unresolved'}, expected {site}")


def check_flavor_reservation_wiring(ctx):
    """The KVM path: reserve a flavor, then launch ON the reserved flavor.

    The trap is launching with a literal flavor name after reserving one. It
    looks right and usually boots - KVM will happily give you an on-demand
    instance - so the lease sits idle, paying for a reservation the instance
    never used, and nothing errors. Distinct from node_reservation_wiring:
    bare metal wires `reservation_id`, KVM wires `flavor_name` / `flavor_id`.
    """
    if not ctx["tree"]:
        return False, "no parseable code"
    if not _calls_named(ctx["tree"], FLAVOR_CREATORS):
        return False, "no add_flavor_reservation call"
    hits = _calls_named(ctx["tree"], SERVER_CREATORS)
    if not hits:
        return False, "no server-creation call"
    has_kw = any(_kw(c, ["flavor_name", "flavor_id", "flavor"], ctx["env"])[0]
                 for c in hits)
    if not has_kw:
        return False, "no flavor_name / flavor_id on the server call"
    derived = bool(_calls_named(ctx["tree"], RESERVED_FLAVOR_SOURCES))
    return derived, ("flavor wired from the lease's reserved flavors" if derived
                     else "flavor named literally, not taken from "
                          "get_reserved_flavors() - the reservation is then "
                          "unused and the instance is on-demand")


def check_name_no_underscore(ctx):
    if not ctx["tree"]:
        return False, "no parseable code"
    hits = _calls_named(ctx["tree"], CONTAINER_CREATORS)
    if not hits:
        return False, "no container-creation call"
    for c in hits:
        cand = None
        found, v = _kw(c, "name", ctx["env"])
        if found:
            cand = v
        elif c.args:
            cand = _const(c.args[0])
            if cand is None and isinstance(c.args[0], ast.Name):
                cand = ctx["env"].get(c.args[0].id)
        if isinstance(cand, str) and "_" in cand:
            if ".replace(" in ctx["code"] and "_" in ctx["code"].split(".replace(", 1)[1][:20]:
                continue
            return False, f"container name {cand!r} contains an underscore (k8s constraint)"
    return True, "container name k8s-safe (or statically undecidable -> pass)"


def check_lease_hours(ctx, hours):
    """Total requested duration equals `hours`, via timedelta(days=,hours=) /
    lease_duration(days=,hours=). Fails if not statically determinable (D12)."""
    if not ctx["tree"]:
        return False, "no parseable code"
    for c in _calls_named(ctx["tree"], ["timedelta", "lease_duration"]):
        total, seen = 0, False
        for kw in c.keywords:
            v = _const(kw.value)
            if isinstance(v, (int, float)):
                seen = True
                total += v * {"days": 24, "hours": 1, "minutes": 1 / 60}.get(kw.arg, 0)
        if seen:
            if abs(total - hours) < 1e-6:
                return True, f"duration = {total}h"
            return False, f"duration = {total}h, expected {hours}h"
    return False, f"lease duration not statically determinable (expected {hours}h)"


def check_required_code_string(ctx, s=None, any=None):
    cands = [s] if s else list(any)
    for x in cands:
        if x in ctx["code"]:
            return True, f"found {x!r} in code"
    return False, f"none of {cands} found in code"


def check_forbidden_code_strings(ctx, strings=()):
    bad = [x for x in strings if x in ctx["code"]]
    return (not bad), (f"forbidden strings in code: {bad}" if bad else "clean")


def check_availability_query(ctx, device_type=None):
    if not ctx["tree"]:
        return False, "no parseable code"
    hits = _calls_named(ctx["tree"], "get_devices")
    if not hits:
        return False, "no get_devices call"
    for c in hits:
        found, v = _kw(c, "filter_reserved", ctx["env"])
        if not (found and v is True):
            return False, f"get_devices without filter_reserved=True (saw {v!r}) - direction bug"
        if device_type is not None:
            fdt, dt = _kw(c, "device_type", ctx["env"])
            if not fdt or dt != device_type:
                return False, f"device_type={dt!r}, expected {device_type!r}"
    return True, "get_devices(filter_reserved=True, ...) correct"


def check_profiles_known_only(ctx):
    """Hallucination canary (D09): every constant in a device_profiles list must be
    in the known-profile set."""
    if not ctx["tree"]:
        return True, "no code; no profiles asserted"
    for c in _calls(ctx["tree"]):
        found, v = _kw(c, "device_profiles", ctx["env"])
        if found and isinstance(v, (list, tuple)):
            unknown = [p for p in v if isinstance(p, str) and p not in KNOWN_PROFILES]
            if unknown:
                return False, f"fabricated device_profiles: {unknown}"
    return True, "no fabricated profile strings"


def check_required_text_string(ctx, s=None, any=None):
    """For knowledge items where a prose answer is legitimate (which image/profile
    do I need). Searches the full answer text, not just code (D10 applies only to
    forbidden checks)."""
    cands = [s] if s else list(any)
    for x in cands:
        if x in ctx["text"]:
            return True, f"found {x!r} in answer"
    return False, f"none of {cands} found in answer"


def _delete_receivers(tree):
    """Source text of receivers of .delete() calls, e.g. 'my_lease' for
    my_lease.delete()."""
    out = []
    for c in _calls(tree):
        if isinstance(c.func, ast.Attribute) and c.func.attr == "delete":
            try:
                out.append(ast.unparse(c.func.value).lower())
            except Exception:
                out.append("")
    return out


def check_teardown(ctx, container=False, lease=False):
    if not ctx["tree"]:
        return False, "no parseable code"
    recv = _delete_receivers(ctx["tree"])
    ok_c, ok_l = (not container), (not lease)
    if container:
        ok_c = bool(_calls_named(ctx["tree"], "destroy_container")) \
            or any("container" in r or r in {"c", "cont"} for r in recv)
    if lease:
        ok_l = bool(_calls_named(ctx["tree"], "delete_lease")) \
            or any("lease" in r or r == "l" for r in recv)
    # fallback: two generic .delete() calls with untypable receivers
    if container and lease and not (ok_c and ok_l) and len(recv) >= 2:
        ok_c = ok_l = True
    msg = []
    if container and not ok_c:
        msg.append("container not deleted")
    if lease and not ok_l:
        msg.append("lease not deleted/freed")
    return (ok_c and ok_l), ("; ".join(msg) or "teardown complete")


#: What "the answer went and looked" means on CHI@Edge. Kept as the DEFAULT so
#: every existing item behaves byte-identically; a wing with a different
#: inventory grammar passes its own vocabulary rather than widening this set.
#: Widening it in place would be an R1 violation with no warning: an edge answer
#: that mentions a newly-accepted call would flip from fail to pass, and the
#: published rate would move without any item or prompt changing.
EDGE_DISCOVERY_CALLS = ("get_devices",)
EDGE_DISCOVERY_STRINGS = ("supported_device_profiles",)


def check_abstain_or_discover(ctx, discovery_calls=None, discovery_strings=None,
                              abstain_patterns=None):
    """T4b: pass if the answer (a) queries live inventory, or (b) contains an
    honest abstention with no fabricated code path.

    `discovery_calls` / `discovery_strings` let an item name the inventory
    grammar of its own wing - bare metal discovers with get_nodes /
    get_node_types / get_flavor_id, which mean nothing on CHI@Edge and which
    CHI@Edge must not start accepting.

    `abstain_patterns` does the same for the REFUSAL half, and for the same
    reason. ABSTAIN_PATTERNS is edge vocabulary - device_profile,
    supported_device_profiles, hardware browser, "no CHI@Edge artifact covers"
    - and no chameleon refusal matches it: "you cannot", "it does not create
    one", "python-chi does not create them" all fall through. The chameleon
    Abstention golds passed anyway only because each embeds a get_node_types()
    block and took the discovery branch, which means that on that wing this
    check has been scoring "did you emit a discovery call" rather than "did you
    abstain honestly".

    Item-scoped rather than appended to the module list on purpose. Widening
    ABSTAIN_PATTERNS in place reaches every stored edge verdict, and an
    improvement that restates a past measurement is the D82 failure - it moved
    79 verdicts and failed parity. Defaulting to the edge list keeps every
    caller that does not pass this byte-identical.
    """
    calls = tuple(discovery_calls or EDGE_DISCOVERY_CALLS)
    strings = tuple(discovery_strings if discovery_strings is not None
                    else EDGE_DISCOVERY_STRINGS)
    patterns = tuple(abstain_patterns if abstain_patterns is not None
                     else ABSTAIN_PATTERNS)
    tree = ctx["tree"]
    if tree and (_calls_named(tree, calls)
                 or any(t in ctx["code"] for t in strings)):
        # " / " and not "/": with the edge defaults this reproduces the
        # original literal "discovery path (get_devices /
        # supported_device_profiles)" byte for byte, so the frozen gate report
        # does not move. A verdict is not the only thing parity watches.
        return True, f"discovery path ({' / '.join(calls + strings)})"
    low = ctx["text"].lower()
    for pat in patterns:
        if re.search(pat, low):
            return True, "honest abstention detected"
    return False, "neither discovery nor honest abstention"


# ------------------------------------------------- v5: reservation decisions
# Everything above grades the SHAPE OF CODE. A reservation answer is a DECISION:
# which device type to reserve, how many, for how long. These grade that, against
# two sources that are kept strictly separate:
#
#   feasibility -> the graded snapshot   (is it actually reservable right now)
#   capability  -> capability_table.yaml (can that hardware do the job at all)
#
# The two never mix, and score_runs reports them as separate columns, because a
# blended rate would be dominated by feasibility - the easy, deterministic half.

@__import__("functools").lru_cache(maxsize=8)
def _captable_at(path: str) -> dict:
    """Parsed capability table for one file, keyed BY PATH.

    It used to be lru_cache(maxsize=1) over a no-argument function that resolved
    the table internally. That is safe with exactly one wing and unsafe with
    two: scoring a chameleon item would populate the single slot with the
    bare-metal table, and a later edge rescoring in the same process would grade
    CHI@Edge answers against it. Golds would still pass, tests would still pass,
    and every published edge number would quietly mean something else - which is
    precisely the failure Level 2 parity exists to catch. Keying by path makes
    the collision impossible rather than merely unlikely.

    Accepts `device_types` or `node_types` as the top-level key. The edge wing
    reserves devices and the chameleon wing reserves hosts; forcing the
    bare-metal table to call its nodes "devices" would put a wrong word in
    hand-authored ground truth to save one line here.
    """
    import yaml

    with open(path) as f:
        doc = yaml.safe_load(f)
    types = doc.get("device_types") or doc.get("node_types")
    if types is None:
        raise SystemExit(
            f"{path}: capability table has neither a 'device_types' nor a "
            "'node_types' block. Every capability check reads this; an empty "
            "table would silently pass nothing rather than fail loudly.")
    return types


def _captable() -> dict:
    from chi_edge_bench.paths import capability_table
    return _captable_at(str(capability_table()))


@__import__("functools").lru_cache(maxsize=8)
def _snapshot_counts(path: str) -> dict:
    """{device_type: {"free": n, "total": n}} for one snapshot."""
    import json
    with open(path) as f:
        devices = json.load(f)["devices"]
    out = {}
    for d in devices:
        # Edge captures type a device with `device_type`; a bare-metal capture
        # types a host with Blazar's own `node_type`. The fallback never fires
        # on an edge snapshot - they all carry device_type - so this cannot move
        # an edge verdict.
        rtype = d.get("device_type") or d.get("node_type")
        c = out.setdefault(rtype, {"free": 0, "total": 0})
        c["total"] += 1
        # A v4-era snapshot has no `status`; `free` alone still works.
        if d.get("status", "free" if d.get("free") else "busy") == "free":
            c["free"] += 1
    return out


_RANK_LINE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.*)$", re.MULTILINE)


_REJECT_HEADING = re.compile(
    r"(?im)^\s*(?:\**\s*)?(?:not recommended|avoid|rejected|excluded|"
    r"do not (?:use|pick))\b")


def recommended_section(text: str) -> str:
    """The part of an answer that actually recommends something.

    Everything from a "not recommended" heading onward is the answer REJECTING
    hardware, which is correct behaviour. Scoring it as a recommendation - or
    reading a "CUDA is unnecessary here" caveat as a CUDA claim - would punish
    exactly the answers we want.
    """
    return _REJECT_HEADING.split(text, maxsplit=1)[0]


def extract_ranked_types(text: str, known=None):
    """Ordered machine_types from a numbered/bulleted recommendation list."""
    known = sorted(known or _captable(), key=len, reverse=True)
    cut = recommended_section(text)
    out = []
    for line in _RANK_LINE.findall(cut):
        for t in known:                    # longest-first: orin-nano before nano
            if t in line and t not in out:
                out.append(t)
                break
    return out


def _ranked(ctx):
    return extract_ranked_types(ctx["text"])


def _free(ctx, t):
    counts = _snapshot_counts(str(ctx["snapshot"]))
    return counts.get(t, {"free": 0, "total": 0})


def check_rank1_feasible(ctx):
    """The top pick must be reservable right now. Rank 1 is what gets acted on."""
    ranked = _ranked(ctx)
    if not ranked:
        return False, "no ranked device types found in the answer"
    c = _free(ctx, ranked[0])
    return c["free"] > 0, (f"rank 1 = {ranked[0]}: {c['free']}/{c['total']} free")


def check_no_down_types_listed(ctx):
    """Recommending a 100%-down type is the sharpest availability failure."""
    bad = [t for t in _ranked(ctx) if _free(ctx, t)["free"] == 0]
    return (not bad), (f"recommended but zero free: {bad}" if bad
                       else "every recommended type has a free device")


def check_count_feasible(ctx, count=1):
    ranked = _ranked(ctx)
    if not ranked:
        return False, "no ranked device types found"
    c = _free(ctx, ranked[0])
    return c["free"] >= count, (f"need {count} of {ranked[0]}, "
                                f"{c['free']} free")


def check_ranked_types_subset(ctx, allowed=()):
    """Every recommended type must be in the gold feasible-and-capable set."""
    ranked = _ranked(ctx)
    if not ranked:
        return False, "no ranked device types found"
    extra = [t for t in ranked if t not in set(allowed)]
    return (not extra), (f"outside the allowed set: {extra}" if extra
                         else f"all of {ranked} allowed")


def _empty_ranking_verdict(ctx):
    """How to grade an answer that names no device type at all.

    The empty ranking is ambiguous and the item decides which it is. When the
    request IS satisfiable, naming nothing is a non-answer, and passing it would
    credit silence - that is what let an unaided model score 45% capability by
    recommending hardware that does not exist on the site. When the request is
    NOT satisfiable, naming nothing is precisely the right answer, and failing it
    would punish the correct abstention the infeasible items exist to test.

    Absent item context we assume feasible, the stricter reading.
    """
    feasible = (ctx.get("item") or {}).get("feasible", True)
    if feasible:
        return False, "no ranked device types found"
    return True, "recommended nothing; the request is not satisfiable here"


def check_forbidden_types_listed(ctx, names=()):
    """Trap types. Only the recommended list counts - naming one to reject it
    is the correct behaviour and must not fail here.

    An answer naming no type at all is graded by _empty_ranking_verdict, because
    "recommended no trap" is vacuously true of a non-answer.
    """
    ranked = _ranked(ctx)
    if not ranked:
        return _empty_ranking_verdict(ctx)
    hit = [t for t in ranked if t in set(names)]
    return (not hit), (f"recommended a trap type: {hit}" if hit else "clean")


def check_names_known_type(ctx):
    """The answer must name hardware that exists, or correctly name nothing.

    Every other reservation check grades what an answer got WRONG, so an answer
    naming no node type at all satisfies them by default: it recommends no
    down type, it recommends no trap, it invokes no forbidden call. An unaided
    model posted a perfect safety group while naming zero hardware that exists
    on this testbed. This is the check with something to lose.

    Deliberately built on `_ranked`, the same extractor `score_wing`'s vacuity
    warning uses, so the score now says what the warning said.

    Naming nothing is graded by _empty_ranking_verdict, not failed outright:
    on an infeasible item silence is the correct answer and the eleven
    infeasible golds would otherwise fail their own gate.
    """
    ranked = _ranked(ctx)
    if ranked:
        return True, f"names known type(s): {ranked}"
    return _empty_ranking_verdict(ctx)


def check_capability_filter(ctx, requires=None):
    """Every recommended type must satisfy the workload's hard requirements.

    `requires` mirrors a stem: {accelerator, precision, peripheral,
    min_ram_gb, min_cuda_compute}.
    """
    req, tbl, bad = requires or {}, _captable(), []
    ranked = _ranked(ctx)
    if not ranked:
        return _empty_ranking_verdict(ctx)
    for t in ranked:
        spec = tbl.get(t)
        if spec is None:
            bad.append(f"{t} (not a CHI@Edge device type)")
            continue
        if "accelerator" in req:
            # A str pins one accelerator; a list means "any of these", which is
            # how a stem says "int8 anywhere" without conflating TPU with CUDA.
            want = req["accelerator"]
            want = [want] if isinstance(want, str) else list(want)
            if spec.get("accelerator") not in want:
                bad.append(f"{t} (accelerator={spec.get('accelerator')}, "
                           f"need one of {want})")
        if "precision" in req and req["precision"] not in (spec.get("precisions") or []):
            bad.append(f"{t} (no {req['precision']})")
        if "peripheral" in req and req["peripheral"] not in (spec.get("peripherals") or []):
            bad.append(f"{t} (no {req['peripheral']})")
        if "min_ram_gb" in req and (spec.get("ram_gb") or 0) < req["min_ram_gb"]:
            bad.append(f"{t} ({spec.get('ram_gb')}GB < {req['min_ram_gb']}GB)")
        if "min_cuda_compute" in req:
            cc = spec.get("cuda_compute")
            if cc is None or float(cc) < float(req["min_cuda_compute"]):
                bad.append(f"{t} (cuda_compute={cc})")
        # Bare-metal dimensions. Additive: no edge item declares these keys, so
        # no edge verdict can move. A null measurement fails the requirement
        # rather than passing it - Blazar not reporting a host's RAM is not
        # evidence that it has enough.
        if "min_vcpus" in req and (spec.get("vcpus") or 0) < req["min_vcpus"]:
            bad.append(f"{t} (vcpus={spec.get('vcpus')} < {req['min_vcpus']})")
        if "min_tensor_cores" in req and (spec.get("tensor_cores") or 0) < req["min_tensor_cores"]:
            bad.append(f"{t} (tensor_cores={spec.get('tensor_cores')})")
    return (not bad), ("capability violations: " + "; ".join(bad) if bad
                       else "every recommended type meets the requirements")


def check_config_grounded(ctx):
    """Configuration asserted for the top pick must not contradict the hardware.

    Catches the two fabrications that matter: an nvidia runtime on a part with no
    NVIDIA GPU, and a device_profile the type does not offer.
    """
    ranked = _ranked(ctx)
    if not ranked:
        return False, "no ranked device types found"
    top = ranked[0]
    spec = _captable().get(top)
    if spec is None:
        return False, f"{top} is not a CHI@Edge device type"

    problems = []
    code = ctx["code"]
    if ('runtime="nvidia"' in code or "runtime='nvidia'" in code) \
            and spec.get("accelerator") != "cuda":
        problems.append(f'runtime="nvidia" but {top} has no NVIDIA GPU')

    # Scope the accelerator claim to the rank-1 entry. A correct answer routinely
    # says "CUDA" on a lower-ranked Jetson while recommending a Pi first, and
    # scanning the whole section would fail it for someone else's line.
    top_line = next((ln for ln in _RANK_LINE.findall(recommended_section(ctx["text"]))
                     if top in ln), "")
    if "cuda" in top_line.lower() and spec.get("accelerator") != "cuda":
        problems.append(f"CUDA claimed for {top} (accelerator="
                        f"{spec.get('accelerator')})")
    if ctx["tree"]:
        allowed = set(spec.get("device_profiles") or [])
        for c in _calls(ctx["tree"]):
            found, v = _kw(c, "device_profiles", ctx["env"])
            if found and isinstance(v, (list, tuple)):
                unknown = [p for p in v if p not in allowed]
                if unknown:
                    problems.append(f"{top} does not offer profiles {unknown}")
    return (not problems), ("; ".join(problems) or
                            f"configuration consistent with {top}")


def check_abstains_when_uncovered(ctx):
    """No artifact covers this hardware. Saying so - or going to live inventory -
    is correct; asserting a grounded answer anyway is not."""
    ok, detail = check_abstain_or_discover(ctx)
    if ok:
        return True, detail
    low = ctx["text"].lower()
    for pat in (r"no (?:trovi )?artifact", r"not documented", r"undocumented",
                r"no (?:validated|verified|known) (?:image|example)",
                r"outside (?:the|our) (?:seeded |grounded )?(?:artifact|corpus)"):
        if re.search(pat, low):
            return True, "coverage limitation stated"
    return False, "no coverage caveat and no discovery path"


CHECKS = {
    "required_call": check_required_call,
    "forbidden_calls": check_forbidden_calls,
    "kwarg": check_kwarg,
    "container_call": check_container_call,
    "reservation_wiring": check_reservation_wiring,
    # bare-metal grammar (chameleon wing)
    "server_call": check_server_call,
    "node_reservation_wiring": check_node_reservation_wiring,
    "site_correct": check_site_correct,
    "flavor_reservation_wiring": check_flavor_reservation_wiring,
    "name_no_underscore": check_name_no_underscore,
    "lease_hours": check_lease_hours,
    "required_code_string": check_required_code_string,
    "required_text_string": check_required_text_string,
    "forbidden_code_strings": check_forbidden_code_strings,
    "availability_query": check_availability_query,
    "profiles_known_only": check_profiles_known_only,
    "teardown": check_teardown,
    "abstain_or_discover": check_abstain_or_discover,
    # v5 reservation-decision checks
    "rank1_feasible": check_rank1_feasible,
    "no_down_types_listed": check_no_down_types_listed,
    "count_feasible": check_count_feasible,
    "ranked_types_subset": check_ranked_types_subset,
    "forbidden_types_listed": check_forbidden_types_listed,
    "names_known_type": check_names_known_type,
    "capability_filter": check_capability_filter,
    "config_grounded": check_config_grounded,
    "abstains_when_uncovered": check_abstains_when_uncovered,
}


def run_checks(answer_code: str, answer_text: str, checker_specs, extra=None):
    """Run a list of checker specs against extracted code + full answer text.
    Returns list of dicts: {check, group, passed, detail}.

    `extra` adds keys to ctx for checks that need more than the answer itself -
    v5 decision checks read ctx["snapshot"]. Omitting it reproduces v4 exactly.
    """
    tree = _parse(answer_code) if answer_code.strip() else None
    ctx = {"tree": tree, "code": answer_code, "text": answer_text,
           "env": _name_env(tree) if tree else {}}
    if extra:
        ctx.update(extra)
    results = []
    for spec in checker_specs:
        spec = dict(spec)
        name = spec.pop("check")
        group = spec.pop("group", "mechanism")
        try:
            passed, detail = CHECKS[name](ctx, **spec)
        except Exception as e:  # a checker crash is a harness bug, surface it
            passed, detail = False, f"CHECKER ERROR: {type(e).__name__}: {e}"
        results.append({"check": name, "group": group,
                        "passed": bool(passed), "detail": detail, "params": spec})
    return results
