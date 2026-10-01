"""Where the benchmark reads from, and where it writes to.

These are two different places and conflating them is what stopped this code
from being installable. Every tool used to compute

    ROOT = Path(__file__).resolve().parent.parent

and then use ROOT for both `ROOT/"items"` (read the benchmark) and
`ROOT/"runs"` (write model answers). That works in a git checkout and nowhere
else: installed as a wheel, ROOT is inside site-packages, which is read-only on
managed installs and the wrong place for measurement output regardless.

So:

  DATA        the benchmark itself - items, snapshots, grounding, extractions,
              capability_table.yaml, reference baselines. Ships in the wheel,
              never written to. DATA is the EDGE wing specifically; see below.

  workspace() runs/, exports/, prompts/ - everything a run produces. Always
              outside the installed package.

Resolution order for the workspace, first match wins:

  1. set_workspace() - the CLI's --workspace flag
  2. $CHI_BENCH_WORKSPACE
  3. the nearest directory at or above the cwd containing a `.chi-edge-bench`
     marker file
  4. ./chi-edge-bench-work

Rule 3 is what keeps an existing record addressable: `benchmark/` in the source
repo carries the marker, so a command run from anywhere inside the repo reads
and writes the real 1816-answer record instead of quietly starting an empty one
next to wherever the shell happened to be.

WINGS
There is now more than one benchmark in this tree. A "wing" is a sibling
package directory shipping a data/ tree - chi_edge_bench (CHI@Edge) and
chameleon_bench (bare metal + KVM) - which is the same definition
parity_baseline.discover_wings() uses, so the drift gate and the harness cannot
disagree about what they are protecting.

The shipped-data accessors below resolve the wing pinned by set_wing(), which
defaults to chi_edge_bench. That default is load-bearing: the edge wing's 134
items and 3231 collected answer cells are frozen and already published, so a
caller that does not ask for a wing must get byte-identical behaviour to before
wings existed. Only validate_golds and tier_assign expose a --wing flag; the
edge builders bind these accessors at module import and stay edge-only by
design.
"""
from __future__ import annotations

import os
from pathlib import Path

#: Read-only benchmark data for the EDGE wing, shipped inside the package.
#: Kept as a module constant because tests/test_paths.py asserts it never
#: escapes the package, and because it is the anchor wing_data() resolves
#: siblings against.
DATA = Path(__file__).resolve().parent / "data"

#: The wing whose data the accessors below resolve. A "wing" is a package
#: directory shipping a data/ tree - the same notion parity_baseline's
#: discover_wings() uses, so the drift gate and the harness agree on what a
#: wing is. Edge is the default, which is what keeps every existing call site
#: byte-identical: nothing that does not ask for a wing can get one.
DEFAULT_WING = "chi_edge_bench"

_wing: str = DEFAULT_WING

#: Filename that marks a directory as a workspace (see rule 3 above).
MARKER = ".chi-edge-bench"

#: Directory created when nothing else identifies a workspace (rule 4).
DEFAULT_WORKSPACE_NAME = "chi-edge-bench-work"

_explicit: Path | None = None


def set_workspace(path: str | os.PathLike[str] | None) -> None:
    """Pin the workspace for this process. `None` restores discovery."""
    global _explicit
    _explicit = Path(path).expanduser().resolve() if path is not None else None


def find_marker(start: Path | None = None) -> Path | None:
    """Nearest directory at or above `start` holding a MARKER file."""
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / MARKER).is_file():
            return d
    return None


def workspace() -> Path:
    """The writable root for runs/, exports/ and prompts/.

    Not created here - callers mkdir the specific subdirectory they write, so
    a read-only command never leaves a directory behind as a side effect.

    Call this inside functions, not at module import: a module-level constant is
    bound before the CLI can apply --workspace, which silently ignores the flag.
    """
    if _explicit is not None:
        return _explicit
    env = os.environ.get("CHI_BENCH_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    found = find_marker()
    if found is not None:
        return found
    return Path.cwd() / DEFAULT_WORKSPACE_NAME


def workspace_source() -> str:
    """How the current workspace was chosen. For `--help`-adjacent reporting;
    a user who scores 0 answers needs to know which directory was searched."""
    if _explicit is not None:
        return "--workspace"
    if os.environ.get("CHI_BENCH_WORKSPACE"):
        return "$CHI_BENCH_WORKSPACE"
    if find_marker() is not None:
        return f"{MARKER} marker"
    return "default (no marker found)"


# -- which wing -------------------------------------------------------------

def set_wing(name: str | None = None) -> None:
    """Pin the wing for this process. `None` restores the edge default.

    Validated eagerly. A typo would otherwise resolve to a directory that does
    not exist and surface much later as an empty glob - which reads as "this
    wing has no items" rather than "you named a wing that is not there", and an
    empty item set is exactly the shape a benchmark failure takes when it is
    silently measuring nothing.
    """
    global _wing
    if name is None:
        _wing = DEFAULT_WING
        return
    data = _wing_data_for(name)
    if not data.is_dir():
        raise SystemExit(
            f"unknown wing {name!r}: expected a data/ tree at {data}. "
            f"Known wings here: {', '.join(known_wings())}.")
    _wing = name


def wing() -> str:
    """The wing the shipped-data accessors currently resolve."""
    return _wing


def _wing_data_for(name: str) -> Path:
    """Resolve a wing's data/ tree without validating it.

    The default returns DATA itself rather than recomputing it, so the edge
    path is guaranteed identical rather than merely equal - no resolve() or
    symlink difference can creep in between the two spellings.

    A wing is a sibling package of chi_edge_bench, which holds in a git
    checkout (benchmark/<wing>/data) and in site-packages alike.
    """
    if name == DEFAULT_WING:
        return DATA
    return DATA.parent.parent / name / "data"


def known_wings() -> list[str]:
    """Sibling package directories that ship a data/ tree, edge always first."""
    root = DATA.parent.parent
    found = [d.name for d in sorted(root.iterdir())
             if d.is_dir() and not d.name.startswith((".", "_"))
             and (d / "data").is_dir()]
    return ([DEFAULT_WING] + [w for w in found if w != DEFAULT_WING]
            if DEFAULT_WING in found else found)


def wing_data(name: str | None = None) -> Path:
    """The data/ tree of `name`, or of the currently pinned wing."""
    return _wing_data_for(name or _wing)


# -- convenience accessors for the shipped data ----------------------------
# These resolve the CURRENT wing at call time, never at import. Binding one to
# a module-level constant defeats set_wing() exactly the way the workspace()
# docstring above describes - and the edge builders that do bind at module
# level (build_reservation_items, make_snapshots, coverage_report) are edge-only
# on purpose, so their frozen behaviour is unaffected.

def items_dir() -> Path:
    return wing_data() / "items"


def snapshots_dir() -> Path:
    return wing_data() / "snapshots"


def grounding_dir() -> Path:
    return wing_data() / "grounding"


def extractions_dir() -> Path:
    return wing_data() / "extractions"


def baselines_dir() -> Path:
    return wing_data() / "baselines"


def artifacts_dir() -> Path:
    """The wing's pinned artifact registry. Present on the chameleon wing only;
    the edge wing's six artifacts predate the registry and are not recorded this
    way. Callers must tolerate its absence rather than assume both wings have
    one - parity_baseline makes the same allowance for the same reason."""
    return wing_data() / "artifacts"


def capability_table() -> Path:
    return wing_data() / "capability_table.yaml"


def default_snapshot() -> Path:
    """The v4 default. Reservation items name their own snapshot and
    runner.resolve_snapshot honours the item over this.

    Wing-relative, so it points somewhere that does not exist on a wing without
    this file. That is deliberate and harmless: V0 code items never read a
    snapshot, and every reservation item names its own. A wing needing a
    different fallback should say so in its items, not here."""
    return snapshots_dir() / "snapshot_synthetic_2026-07-04.json"


# -- convenience accessors for the workspace -------------------------------

def runs_dir() -> Path:
    return workspace() / "runs"


def exports_dir() -> Path:
    return workspace() / "exports"


def prompts_dir() -> Path:
    return workspace() / "prompts"
