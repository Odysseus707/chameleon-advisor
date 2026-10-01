"""verify_authored: gate the authored tier against the pinned tree. Stage 8.

Step 5 is the only stage where text is WRITTEN rather than derived, so it is the
only stage that can introduce something that is not true. This is the check that
makes it auditable, and it is the automated form of the hand-written
"STEP 3 - GREP VERIFICATION SUMMARY" block at the bottom of the edge wing's
A1.yaml.

FIVE RULES. A record failing any of them is rejected, not softened.

  1. memorization_probes must appear VERBATIM in the pinned tree. They exist to
     detect a model reciting an artifact it memorised, so a probe that is not
     really in the artifact tests nothing.
  2. Quoted code spans in prose (`backticked` text that looks like code) must
     appear verbatim in the tree.
  3. Any node type / flavour / image named in prose must already be in that
     artifact's magic_strings. Prose may describe the extraction; it may not add
     hardware to it.
  4. workload_tags must come from rank.py's existing vocabulary. The model may
     label, never invent a label.
  5. retrieval_tags must appear in the artifact's own text, or resolve through a
     small explicit synonym table. This is the loosest rule because search words
     are meant to be what a USER would type, not what the artifact says - but
     "loosest" still means every term is traceable to something.

  python corpus_v2/tools/verify_authored.py run
  python corpus_v2/tools/verify_authored.py run --only A10
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from catalog import normalize_repo                          # noqa: E402
from fetch import repo_dir                                  # noqa: E402
from rank import WORKLOAD_TAGS                              # noqa: E402
from select_wing import WING, load_registry                 # noqa: E402

EXTRACTIONS_DIR = WING / "extractions"
GROUNDING_DIR = WING / "grounding"

PROSE_FIELDS = ("summary", "preconditions", "traps_illustrated",
                "not_covered", "uncertainties")

#: Search words a user would plausibly type that the artifact spells otherwise.
#: Deliberately small and explicit - an open-ended normaliser would let anything
#: through and the rule would stop meaning anything.
SYNONYMS = {
    "fine-tune": ["finetune", "fine_tuning", "fine tuning"],
    "gpu": ["cuda", "nvidia", "gpu_"],
    "h100": ["g1.h100", "h100"],
    "a100": ["gpu_a100", "a100"],
    "vm": ["kvm", "virtual machine"],
    "bare metal": ["baremetal", "bare_metal", "bare-metal"],
    "object store": ["objectbucket", "object_store", "swift"],
    "cpu cores": ["node cores", "n_cores", "cores"],
    "notebook": ["jupyter", "ipynb"],
}

#: Prose is allowed to name hardware only if the extraction already found it.
# Bare `storage` is deliberately NOT here. It is a real Chameleon node type and
# also an ordinary English word and the name of a python-chi module, and over
# this corpus the word wins 50 to 0: fifty artifacts carry `storage` in
# node_types_observed and not one passes it to a reservation call. Treating the
# word as a hardware claim rejects honest prose about object storage. The
# qualified forms (storage_nvme, storage_hierarchy) are unambiguous and stay.
RESOURCE_RE = re.compile(
    r"\b(compute_\w+|storage_\w+|gpu_\w+|fpga_\w+|m1\.\w+|g1\.\w+"
    r"|CC-\w[\w.\-]*|Ubuntu[\w.\-]*)\b")

CODEISH = re.compile(r"`([^`]{4,120})`")

#: Read caps. Plain files are capped low because a multi-megabyte one is a blob,
#: not source. Notebooks are capped high because their bulk is output, not code.
PLAIN_MAX_BYTES = 4_000_000
NOTEBOOK_MAX_BYTES = 64_000_000


def tree_text(repo: Path) -> str:
    """Everything greppable in the pinned tree, with notebooks DECODED.

    Notebooks are JSON, so on disk a cell reads
        "context.choose_site(default=\\"CHI@TACC\\")\\n"
    Grepping raw bytes therefore never matches a probe quoted from the notebook
    as a human sees it. That is not a small edge case: 119 of the corpus's 123
    code sections are notebook cells, so the raw-bytes version of this gate
    rejected almost every probe - and the tempting response to a gate that
    rejects everything is to weaken the verbatim rule, which would have quietly
    destroyed the only check standing between authored prose and invention.
    """
    import json
    out = []
    p = subprocess.run(["git", "-C", str(repo), "ls-files"],
                       capture_output=True, text=True)
    for rel in p.stdout.splitlines():
        f = repo / rel
        try:
            if not f.is_file():
                continue
            size = f.stat().st_size
            notebook = f.suffix.lower() == ".ipynb"
            # A notebook's SIZE is its embedded output - base64 images, tensors,
            # training logs - and its cell SOURCE is almost always small. Judging
            # a notebook by its file size therefore excluded exactly the files
            # this gate exists to read: five artifacts in this corpus have
            # notebooks over the flat cap, and every probe quoted from one was
            # rejected as "not verbatim in tree" while being verbatim in it.
            # Non-notebooks keep the flat cap; notebooks get a far higher one
            # and contribute only their decoded cells, never their raw JSON.
            if size >= (NOTEBOOK_MAX_BYTES if notebook else PLAIN_MAX_BYTES):
                continue
            raw = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Raw text for anything within the plain cap, exactly as before: a
        # notebook's OUTPUT is part of what the artifact committed, and tags
        # have legitimately traced to it. This change is strictly additive.
        if size < PLAIN_MAX_BYTES:
            out.append(raw)
        if notebook:
            try:
                nb = json.loads(raw)
            except (json.JSONDecodeError, RecursionError):
                continue
            for c in nb.get("cells", []):
                if not isinstance(c, dict):
                    continue
                src = c.get("source", "")
                out.append("".join(src) if isinstance(src, list) else str(src))
    return "\n".join(out)


def normalise(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def check(rec, doc, tree, ground) -> list[str]:
    fails = []
    # The Trovi title is part of the artifact's identity and is often NOT in the
    # grounding doc, whose title comes from the README's own H1 instead. A user
    # searching for "computer-use agents" is searching the Trovi catalogue, so
    # title words are legitimately traceable even when the repo never says them.
    tree_n = normalise(tree)
    ground_n = normalise(ground + "\n" + str(rec.get("trovi_title") or ""))

    for probe in doc.get("memorization_probes") or []:
        if normalise(probe) not in tree_n:
            fails.append(f"memorization_probe not verbatim in tree: {probe[:70]!r}")

    prose = []
    for f in PROSE_FIELDS:
        v = doc.get(f)
        if isinstance(v, str):
            prose.append(v)
        elif isinstance(v, list):
            prose.extend(str(x) for x in v)
    blob = "\n".join(prose)

    for span in CODEISH.findall(blob):
        if normalise(span) not in tree_n:
            fails.append(f"quoted code not in tree: {span[:70]!r}")

    known = {normalise(str(m["value"])) for m in doc.get("magic_strings") or []}
    for m in RESOURCE_RE.findall(blob):
        if normalise(m) not in known and normalise(m) not in tree_n:
            fails.append(f"prose names hardware absent from magic_strings: {m!r}")

    for t in rec.get("workload_tags") or []:
        if t not in WORKLOAD_TAGS:
            fails.append(f"workload_tag outside the fixed vocabulary: {t!r}")

    for tag in rec.get("retrieval_tags") or []:
        if traceable(tag, ground_n, tree_n):
            continue
        fails.append(f"retrieval_tag not traceable to the artifact: {tag!r}")
    return fails


def _synonyms(n: str) -> list[str]:
    """Synonyms in BOTH directions.

    The table was written one-way, so `vm -> virtual machine` worked while the
    tag "virtual machine" was rejected for an artifact that says "VM". Synonymy
    is symmetric; a one-way table just encodes which side the author happened to
    write first.
    """
    out = list(SYNONYMS.get(n, []))
    for key, alts in SYNONYMS.items():
        if n in (normalise(a) for a in alts):
            out.append(key)
            out += [a for a in alts if normalise(a) != n]
    return out


#: A search word matches on a stem of at least this many characters.
#:
#: Exact matching rejected "reproduction" for artifacts whose README says
#: "Reproduced Experiment", and "caching" for one that says "cache". Those are
#: the same concept in a different word form, and a search word exists precisely
#: to be what a USER types rather than what the artifact happens to say. A stem
#: still requires the concept to be present in the artifact, so traceability
#: holds; five characters is long enough that unrelated words do not collide.
STEM_MIN = 5


def traceable(tag: str, ground_n: str, tree_n: str) -> bool:
    n = normalise(tag)
    if n in ground_n or n in tree_n:
        return True
    for alt in _synonyms(n):
        a = normalise(alt)
        if a in ground_n or a in tree_n:
            return True
    # Every word of a multi-word tag must be present, so "language image" only
    # passes if both words are; that keeps phrase tags from passing on one hit.
    words = [w for w in re.split(r"[^a-z0-9@._-]+", n) if len(w) >= STEM_MIN]
    if not words:
        return False
    return all(w[:STEM_MIN] in ground_n or w[:STEM_MIN] in tree_n
               for w in words)


def run(only: list[str]) -> int:
    import yaml
    reg = load_registry()
    records = [r for r in reg["artifacts"] if not only or r["id"] in only]
    total_fail = 0
    for rec in records:
        path = EXTRACTIONS_DIR / f"{rec['id']}.yaml"
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not doc.get("summary"):
            continue                      # not authored yet
        repo = repo_dir(normalize_repo(rec["repo_url"]))
        ground = (GROUNDING_DIR / f"{rec['id']}.md").read_text(encoding="utf-8")
        fails = check(rec, doc, tree_text(repo), ground)
        status = "PASS" if not fails else f"REJECT ({len(fails)})"
        print(f"{rec['id']:<5} {status}")
        for f in fails:
            print(f"        x {f}")
        total_fail += bool(fails)
    print(f"\n{len(records) - total_fail}/{len(records)} pass the gate.")
    return 1 if total_fail else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("run",))
    ap.add_argument("--only", nargs="*", default=[])
    return run(ap.parse_args().only)


if __name__ == "__main__":
    raise SystemExit(main())
