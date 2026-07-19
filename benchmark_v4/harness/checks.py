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


def check_abstain_or_discover(ctx):
    """T4b: pass if the answer (a) queries live inventory / supported_device_profiles,
    or (b) contains an honest abstention with no fabricated code path."""
    tree = ctx["tree"]
    if tree and (_calls_named(tree, "get_devices")
                 or "supported_device_profiles" in ctx["code"]):
        return True, "discovery path (get_devices / supported_device_profiles)"
    low = ctx["text"].lower()
    for pat in ABSTAIN_PATTERNS:
        if re.search(pat, low):
            return True, "honest abstention detected"
    return False, "neither discovery nor honest abstention"


CHECKS = {
    "required_call": check_required_call,
    "forbidden_calls": check_forbidden_calls,
    "kwarg": check_kwarg,
    "container_call": check_container_call,
    "reservation_wiring": check_reservation_wiring,
    "name_no_underscore": check_name_no_underscore,
    "lease_hours": check_lease_hours,
    "required_code_string": check_required_code_string,
    "required_text_string": check_required_text_string,
    "forbidden_code_strings": check_forbidden_code_strings,
    "availability_query": check_availability_query,
    "profiles_known_only": check_profiles_known_only,
    "teardown": check_teardown,
    "abstain_or_discover": check_abstain_or_discover,
}


def run_checks(answer_code: str, answer_text: str, checker_specs):
    """Run a list of checker specs against extracted code + full answer text.
    Returns list of dicts: {check, group, passed, detail}."""
    tree = _parse(answer_code) if answer_code.strip() else None
    ctx = {"tree": tree, "code": answer_code, "text": answer_text,
           "env": _name_env(tree) if tree else {}}
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
