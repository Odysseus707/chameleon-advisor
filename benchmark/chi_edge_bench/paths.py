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
              never written to.

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
"""
from __future__ import annotations

import os
from pathlib import Path

#: Read-only benchmark data, shipped inside the package.
DATA = Path(__file__).resolve().parent / "data"

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


# -- convenience accessors for the shipped data ----------------------------

def items_dir() -> Path:
    return DATA / "items"


def snapshots_dir() -> Path:
    return DATA / "snapshots"


def grounding_dir() -> Path:
    return DATA / "grounding"


def extractions_dir() -> Path:
    return DATA / "extractions"


def baselines_dir() -> Path:
    return DATA / "baselines"


def capability_table() -> Path:
    return DATA / "capability_table.yaml"


def default_snapshot() -> Path:
    """The v4 default. Reservation items name their own snapshot and
    runner.resolve_snapshot honours the item over this."""
    return snapshots_dir() / "snapshot_synthetic_2026-07-04.json"


# -- convenience accessors for the workspace -------------------------------

def runs_dir() -> Path:
    return workspace() / "runs"


def exports_dir() -> Path:
    return workspace() / "exports"


def prompts_dir() -> Path:
    return workspace() / "prompts"
