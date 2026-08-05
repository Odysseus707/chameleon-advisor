"""detect: the Chameleon provisioning grammar, as a reusable scanner.

Stage 2's detection half, kept separate because later stages (fragment
extraction, api_family validation) must match on exactly the same call sets.
One definition, one place to fix it.

The call vocabulary below is not invented. It is the measured python-chi call
surface across both grounding corpora and the notebooks, from the as-built
map's Q4 table, with the grammar labels (shared / OO / imperative / edge /
KVM / baremetal) it assigns.

Two facts from that measurement drive the design:

1. Site declarations split three ways: chi.use_site 11, context.choose_site 10,
   bare use_site 6. A scan anchored only on chi.use_site misses roughly a third
   of them, so all spellings are matched, via terminal-name matching
   (checks.py:42-56 technique), which treats chi.lease.create_lease and a bare
   create_lease after `from chi import lease` identically.

2. add_node_reservation and create_server, the baremetal grammar, appear ZERO
   times as real calls in this workspace. They exist only inside forbidden_calls
   trap lists. Every baremetal pattern here is therefore unvalidated against any
   positive local example, which is why phase 1 slot 1 exists.

Strong versus weak signals. execute, upload, download, submit and friends are
shared grammar whose names collide with ordinary Python (df.execute, s3.upload).
They count only once a strong, unambiguously Chameleon signal or a chi-family
import is already present in the same repo. Otherwise a pandas notebook would
triage as provisioning code.

Notebooks are scanned cell-wise, because density and fragment boundaries are
per-cell properties.

  python corpus_v2/tools/detect.py <repo_path>
"""
from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- call sets

# Unambiguously Chameleon. Any one of these is sufficient on its own.
EDGE_CALLS = {"add_device_reservation", "get_device_reservation",
              "create_container", "destroy_container", "get_devices"}
KVM_CALLS = {"add_flavor_reservation", "get_flavor_id"}
BAREMETAL_CALLS = {"add_node_reservation", "create_server"}
SITE_CALLS = {"use_site", "choose_site"}
LEASE_CALLS = {"create_lease", "lease_duration", "delete_lease",
               "get_lease", "add_fip_reservation"}
PROJECT_CALLS = {"choose_project"}

STRONG_CALLS = (EDGE_CALLS | KVM_CALLS | BAREMETAL_CALLS | SITE_CALLS
                | LEASE_CALLS | PROJECT_CALLS)

# Shared grammar: real python-chi, but the names collide with ordinary Python.
WEAK_CALLS = {"execute", "upload", "download", "associate_floating_ip",
              "wait_for_active", "submit", "set"}
WEAK_CONSTRUCTORS = {"Lease", "Container", "Server"}

# python_chi_era. The OO surface (Lease/Container/Server, context.*, .submit())
# is the current API; the free-function surface is the legacy one.
CURRENT_MARKERS = {"choose_site", "choose_project", "submit",
                   "Lease", "Container", "Server"}
LEGACY_MARKERS = {"use_site", "create_lease", "create_container",
                  "destroy_container", "get_device_reservation",
                  "lease_duration", "delete_lease", "get_lease"}

IMPORT_ROOTS = {"chi", "blazarclient", "novaclient", "glanceclient",
                "neutronclient", "keystoneauth1", "keystoneclient",
                "zunclient", "openstack", "openstackclient", "heatclient",
                "swiftclient", "cinderclient", "python_chi"}

SKIP_DIRS = {".git", ".github", "node_modules", "__pycache__",
             ".ipynb_checkpoints", "venv", ".venv", "site-packages"}

# A repo carrying vendored upstream source would otherwise dominate density.
# Applies to .py only. A notebook's byte size is driven by embedded output
# images, not by code: a 9.4 MB notebook with 33 code cells and real
# chi.use_site calls is ordinary. Applying this cap to .ipynb silently dropped
# a whole provisioning artifact (agw2005/pbp-reproduced), so notebooks get their
# own, much higher raw ceiling and are capped on extracted source instead.
MAX_FILE_BYTES = 2_000_000
MAX_NOTEBOOK_BYTES = 200_000_000
MAX_NOTEBOOK_SOURCE_BYTES = 4_000_000


@dataclass
class TriageSignals:
    matched_calls: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    n_notebooks: int = 0
    n_py: int = 0
    n_code_units: int = 0
    n_provisioning_cells: int = 0
    provisioning_density: float = 0.0
    n_fragments_predicted: int = 0
    dispersed: bool = False
    site_call_style: str = "none"
    api_family_detected: str = "none"
    python_chi_era: str = "unknown"
    strong_hits: int = 0
    weak_hits: int = 0
    total_bytes: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _terminal_name(node: ast.Call) -> str | None:
    """Terminal name of a call target: chi.lease.create_lease -> create_lease."""
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def _strip_magics(src: str) -> str:
    """Neutralize IPython magics and shell escapes so ast.parse has a chance.

    Code cells routinely start lines with !pip, %%bash, %matplotlib. Those are
    syntax errors to ast, and replacing them loses no provisioning calls, which
    are always plain Python.
    """
    out = []
    for line in src.splitlines():
        s = line.lstrip()
        out.append("pass" if s.startswith(("!", "%", "?")) else line)
    return "\n".join(out)


def _scan_source(src: str) -> tuple[set[str], set[str]]:
    """(call terminal names, import roots) from one code unit.

    AST first. On SyntaxError, fall back to a regex sweep: a cell that will not
    parse can still contain the calls we care about, and dropping it silently is
    exactly the failure mode this exercise exists to avoid.
    """
    calls: set[str] = set()
    imports: set[str] = set()
    try:
        tree = ast.parse(_strip_magics(src))
    except (SyntaxError, ValueError, RecursionError):
        for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", src):
            calls.add(m.group(1))
        for m in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", src, re.M):
            imports.add(m.group(1).split(".")[0])
        return calls, imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _terminal_name(node)
            if name:
                calls.add(name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                imports.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
    return calls, imports


def _notebook_cells(path: Path) -> list[str]:
    try:
        nb = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError, RecursionError):
        return []
    cells = []
    for c in nb.get("cells", []):
        if not isinstance(c, dict) or c.get("cell_type") != "code":
            continue
        src = c.get("source", "")
        cells.append("".join(src) if isinstance(src, list) else str(src))
    return cells


def _relevant_files(root: Path, suffix: str) -> list[Path]:
    out = []
    for p in root.rglob(f"*{suffix}"):
        if not p.is_file() or p.is_symlink():
            continue
        if SKIP_DIRS & set(p.relative_to(root).parts):
            continue
        out.append(p)
    return out


def _iter_code_units(root: Path):
    """Yield (unit_id, source) for every notebook code cell and .py file.

    A notebook contributes one unit per code cell; a .py file contributes one
    unit. Density is measured over these units, and fragment runs are computed
    in this deterministic sorted order.
    """
    paths = sorted(set(_relevant_files(root, ".ipynb"))
                   | set(_relevant_files(root, ".py")))
    for path in paths:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        is_nb = path.suffix == ".ipynb"
        if size > (MAX_NOTEBOOK_BYTES if is_nb else MAX_FILE_BYTES):
            continue
        if is_nb:
            budget = MAX_NOTEBOOK_SOURCE_BYTES
            for i, src in enumerate(_notebook_cells(path)):
                budget -= len(src)
                if budget < 0:
                    break
                yield f"{path.relative_to(root)}#c{i}", src
        else:
            try:
                yield (str(path.relative_to(root)),
                       path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue


def scan_repo(root: Path) -> TriageSignals:
    sig = TriageSignals()
    if not root.exists():
        return sig

    sig.n_notebooks = len(_relevant_files(root, ".ipynb"))
    sig.n_py = len(_relevant_files(root, ".py"))

    units: list[tuple[set[str], set[str]]] = []
    all_calls: set[str] = set()
    all_imports: set[str] = set()
    for _unit_id, src in _iter_code_units(root):
        calls, imports = _scan_source(src)
        units.append((calls, imports))
        all_calls |= calls
        all_imports |= imports
        sig.total_bytes += len(src.encode("utf-8", errors="replace"))

    sig.n_code_units = len(units)
    sig.imports = sorted(all_imports & IMPORT_ROOTS)

    strong_present = all_calls & STRONG_CALLS
    has_chi_context = bool(strong_present or sig.imports)

    matched = set(strong_present)
    if has_chi_context:
        matched |= all_calls & (WEAK_CALLS | WEAK_CONSTRUCTORS)
    sig.matched_calls = sorted(matched)
    sig.strong_hits = len(strong_present)
    sig.weak_hits = len(matched) - len(strong_present)

    # Per-unit provisioning flags, for density and fragment prediction.
    prov_flags = [
        bool(calls & STRONG_CALLS)
        or bool(has_chi_context and (calls & (WEAK_CALLS | WEAK_CONSTRUCTORS)))
        for calls, _ in units
    ]
    sig.n_provisioning_cells = sum(prov_flags)
    sig.provisioning_density = (round(sig.n_provisioning_cells / len(units), 4)
                                if units else 0.0)

    # A fragment is a maximal run of consecutive provisioning units. Many short
    # runs spread across many units means the boundary heuristic has little to
    # hold on to, which is what `dispersed` records.
    fragments = 0
    prev = False
    for f in prov_flags:
        if f and not prev:
            fragments += 1
        prev = f
    sig.n_fragments_predicted = fragments
    sig.dispersed = bool(sig.n_provisioning_cells >= 3
                         and fragments >= 3
                         and fragments / sig.n_provisioning_cells >= 0.6)

    has_use = "use_site" in all_calls
    has_choose = "choose_site" in all_calls
    sig.site_call_style = ("mixed" if has_use and has_choose else
                           "choose_site" if has_choose else
                           "use_site" if has_use else "none")

    fams = [n for n, s in (("edge", EDGE_CALLS), ("kvm", KVM_CALLS),
                           ("baremetal", BAREMETAL_CALLS)) if all_calls & s]
    sig.api_family_detected = (fams[0] if len(fams) == 1 else
                               "mixed" if len(fams) > 1 else "none")

    cur = bool(all_calls & CURRENT_MARKERS)
    leg = bool(all_calls & LEGACY_MARKERS)
    sig.python_chi_era = ("mixed" if cur and leg else "current" if cur else
                          "legacy" if leg else "unknown")
    return sig


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.splitlines()[0])
        print("usage: detect.py <repo_path>")
        return 2
    print(json.dumps(scan_repo(Path(sys.argv[1]).resolve()).as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
