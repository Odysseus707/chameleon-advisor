#!/usr/bin/env python3
"""
Calibrate the v4 checker against human scores from the v3 workbook.

For every graded cell in benchmark_v3.xlsx / sheet "Output" we run the v4
checker (harness.runner.evaluate, snapshot=None) on the pasted model output and
compare the checker's PASS/FAIL verdict to the human 0-2 score. Writes a
per-cell CSV and prints checker-vs-human agreement + Cohen's kappa.

Dependencies: pyyaml, openpyxl, stdlib only. Reads harness/ and items/ but
never modifies them.

Usage:
  python -m tools.calibrate_v3
  python tools/calibrate_v3.py
  python tools/calibrate_v3.py --wrap-code   # recover stripped code fences

The v3 workbook stored model outputs with their ```python fences stripped on
paste, so harness.runner.extract_code() (which needs a fence, or the whole
answer to be pure Python) recovers no code and almost every cell scores FAIL.
--wrap-code applies a self-validating heuristic (see wrap_code_blocks) that
re-fences the embedded Python before evaluation.
"""

import argparse
import ast
import csv
import re
import sys
import textwrap
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.runner import evaluate, load_item  # noqa: E402

WORKBOOK = ROOT / "benchmark_v3.xlsx"
ITEMS_DIR = ROOT / "items"
OUT_CSV = ROOT / "exports" / "calibration_v3.csv"

GROUPS = ("mechanism", "specifics", "safety")


# --------------------------------------------------------------------------- #
# Code-fence recovery heuristic (--wrap-code)
#
# v3 outputs lost their ```python fences on paste. This re-detects contiguous
# Python regions embedded in prose and wraps each in a fence so extract_code()
# can recover them. Caveats handled (empirically derived from the 84 graded
# cells): glued language labels ("pythonimport chi", "python#", "bashdocker"),
# blank lines and comments inside blocks, multi-line calls with indented args
# and lone closing brackets, multiple interconnected blocks per answer, prose
# that merely mentions API calls, and pure-prose abstentions. Non-Python blocks
# (bash/dockerfile) and prose fail the ast.parse gate and are left alone.
# --------------------------------------------------------------------------- #

# Language labels that can appear glued to code when a ``` fence collapses.
# Longest-first so `python` is tried before `py`.
_LANG_LABELS = sorted(
    ("python", "py3", "py", "bash", "shell", "sh", "zsh", "console",
     "dockerfile", "docker", "json", "yaml", "yml", "toml", "ini",
     "text", "code", "plaintext"),
    key=len, reverse=True,
)

# Python statement keywords that unambiguously start a line of code.
_KEYWORDS = {
    "import", "from", "def", "class", "async", "await", "for", "while",
    "if", "elif", "else", "try", "except", "finally", "with", "return",
    "raise", "yield", "assert", "global", "nonlocal", "del", "pass",
    "break", "continue", "lambda", "print", "not", "in", "and", "or",
}

# python-chi domain roots seen leading real code lines; used only to decide
# whether a glued label is safe to strip (root, or root + "_suffix").
_DOMAIN_ROOTS = (
    "chi", "container", "lease", "context", "hardware", "reservation",
    "reservations", "reservation_id", "devs", "device", "devices",
    "available", "available_devices", "picamera_devs", "my_lease",
    "my_container", "ip", "is_free", "target", "start_date", "end_date",
    "node_type", "lease_name",
)

_ANCHOR_ASSIGN_CALL = re.compile(r"^[A-Za-z_][\w.]*(\[[^\]\n]*\])?\s*(=(?!=)|\()")
_LEAD_IDENT = re.compile(r"^([A-Za-z_]\w*)")
_CLOSE_BRACKET = re.compile(r"^\s*[)\]}][\s,)\]}]*(#.*)?$")


def _looks_code_start(s: str) -> bool:
    """Would this string plausibly begin a Python statement?"""
    t = s.strip()
    if not t:
        return False
    if t.startswith("#"):
        return True
    m = _LEAD_IDENT.match(t)
    if m and m.group(1) in _KEYWORDS:
        return True
    if t.startswith("@") and len(t) > 1 and (t[1].isalpha() or t[1] == "_"):
        return True
    return bool(_ANCHOR_ASSIGN_CALL.match(t))


def _strip_label(line: str) -> str:
    """Repair a glued language label at the very start of a line.

    Strip only when a known label prefixes the line AND the remainder starts
    with a Python keyword, `#`, or a known python-chi domain root (exact or
    root + "_suffix"). That gate keeps real identifiers safe: `shutil.copy` ->
    label `sh`, remainder head `util` is neither keyword nor root, left intact;
    `bashdocker run` -> `docker` not a root, left intact and later dropped as
    prose; `containment = 5` -> `contain` is not a root prefix, left intact."""
    for label in _LANG_LABELS:
        if line.startswith(label) and len(line) > len(label):
            rest = line[len(label):]
            stripped = rest.lstrip()
            if stripped.startswith("#") and _looks_code_start(rest):
                return rest
            head = _LEAD_IDENT.match(stripped)
            if head:
                h = head.group(1)
                root_ok = any(h == r or h.startswith(r + "_")
                              for r in _DOMAIN_ROOTS)
                if (h in _KEYWORDS or root_ok) and _looks_code_start(rest):
                    return rest
    return line


def _is_anchor(s: str) -> bool:
    """A line that can START a top-level code region."""
    t = s.strip()
    if not t or t.startswith("#"):
        return False
    m = _LEAD_IDENT.match(t)
    if m and m.group(1) in _KEYWORDS:
        return True
    if t.startswith("@") and len(t) > 1 and (t[1].isalpha() or t[1] == "_"):
        return True
    return bool(_ANCHOR_ASSIGN_CALL.match(t))


def _is_cont(s: str) -> bool:
    """Continuation/interior line: blank, comment, indented, or bracket close."""
    if s.strip() == "":
        return True
    if s.lstrip().startswith("#"):
        return True
    if s[:1] in (" ", "\t"):
        return True
    return bool(_CLOSE_BRACKET.match(s))


def _validate(block_lines):
    """Return (kept_lines, code_str) for the largest leading slice of
    block_lines that dedents+parses as non-empty Python, else None. Trims up to
    a few trailing lines that may be stray prose swept in by the segmenter."""
    for cut in range(0, min(5, len(block_lines))):
        sub = block_lines[: len(block_lines) - cut] if cut else block_lines
        while sub and sub[-1].strip() == "":
            sub = sub[:-1]
        if not sub:
            continue
        code = textwrap.dedent("\n".join(sub))
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        if tree.body:
            return sub, code
    return None


def wrap_code_blocks(text: str):
    """Return (wrapped_text, n_blocks). Contiguous Python regions embedded in
    prose are each wrapped in a ```python fence. Text that already contains a
    fence is returned unchanged."""
    if "```" in text:
        return text, text.count("```") // 2

    raw = text.split("\n")
    cleaned = [_strip_label(l) for l in raw]
    n = len(cleaned)

    regions = []  # (start_idx, end_idx_exclusive, code_str)
    i = 0
    while i < n:
        if _is_anchor(cleaned[i]) or _is_cont(cleaned[i]):
            j = i
            while j < n and (_is_anchor(cleaned[j]) or _is_cont(cleaned[j])):
                j += 1
            a, b = i, j
            while a < b and cleaned[a].strip() == "":
                a += 1
            while b > a and cleaned[b - 1].strip() == "":
                b -= 1
            if a < b and any(_is_anchor(cleaned[k]) for k in range(a, b)):
                v = _validate(cleaned[a:b])
                if v is not None:
                    sub, code = v
                    regions.append((a, a + len(sub), code))
            i = j
        else:
            i += 1

    if not regions:
        return text, 0

    out = []
    idx = 0
    reg = 0
    while idx < n:
        if reg < len(regions) and idx == regions[reg][0]:
            _, end, code = regions[reg]
            out.append("```python")
            out.append(code)
            out.append("```")
            idx = end
            reg += 1
        else:
            out.append(raw[idx])
            idx += 1
    return "\n".join(out), len(regions)


def condition_for(setup: str):
    """Map a Setup string to a fed-set condition. blind wins if both appear."""
    low = (setup or "").lower()
    if "blind" in low:
        return "blind"
    if "artifact" in low:
        return "matched"
    return None


def group_rate(groups: dict, name: str):
    """passed/total for a checker group, or '' if the item has no such group."""
    g = groups.get(name)
    if not g or not g.get("total"):
        return ""
    return round(g["passed"] / g["total"], 4)


def failed_checks(rep: dict):
    return [r["check"] for r in rep["results"] if not r["passed"]]


def load_cells(wrap_code=False):
    """Yield one dict per graded, non-empty-output row in the Output sheet.

    If wrap_code is set, the pasted output is run through wrap_code_blocks() to
    re-fence embedded Python before evaluation."""
    wb = openpyxl.load_workbook(WORKBOOK, data_only=True)
    ws = wb["Output"]
    item_cache = {}
    rows = ws.iter_rows(min_row=2, values_only=True)  # skip header
    for raw in rows:
        # ID, Category, Setup, Model output, Screenshot, Score, Notes
        item_id, _category, setup, output, _shot, score, _notes = (
            list(raw) + [None] * 7
        )[:7]

        if score is None or str(score).strip() == "":
            continue
        if output is None or str(output).strip() == "":
            continue

        try:
            human_score = int(str(score).strip())
        except ValueError:
            continue

        condition = condition_for(str(setup))
        if condition is None:
            continue

        item_id = str(item_id).strip()
        if item_id not in item_cache:
            path = ITEMS_DIR / f"{item_id}.yaml"
            if not path.exists():
                sys.stderr.write(f"[skip] no item file for {item_id}\n")
                item_cache[item_id] = None
            else:
                item_cache[item_id] = load_item(path)
        item = item_cache[item_id]
        if item is None:
            continue

        answer = str(output)
        n_blocks = 0
        if wrap_code:
            answer, n_blocks = wrap_code_blocks(answer)

        rep = evaluate(item, answer, snapshot=None)
        verdict = "PASS" if rep["all_passed"] else "FAIL"

        yield {
            "ID": item_id,
            "condition": condition,
            "setup": str(setup),
            "human_score": human_score,
            "checker_verdict": verdict,
            "mechanism_pass_rate": group_rate(rep["groups"], "mechanism"),
            "specifics_pass_rate": group_rate(rep["groups"], "specifics"),
            "safety_pass_rate": group_rate(rep["groups"], "safety"),
            "_failed": failed_checks(rep),
            "_n_blocks": n_blocks,
        }


def cohen_kappa(pairs):
    """Cohen's kappa for two binary raters. pairs = list of (a: bool, b: bool)."""
    n = len(pairs)
    if n == 0:
        return float("nan")
    a11 = sum(1 for a, b in pairs if a and b)
    a00 = sum(1 for a, b in pairs if not a and not b)
    po = (a11 + a00) / n
    pa1 = sum(1 for a, _ in pairs if a) / n
    pb1 = sum(1 for _, b in pairs if b) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    if pe == 1.0:  # both raters constant -> kappa undefined; report perfect/none
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def agreement(pairs):
    n = len(pairs)
    if n == 0:
        return float("nan")
    return sum(1 for a, b in pairs if a == b) / n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wrap-code", action="store_true",
                    help="re-fence embedded Python in pasted outputs before "
                         "evaluation (recovers stripped ```python fences)")
    args = ap.parse_args()

    cells = list(load_cells(wrap_code=args.wrap_code))

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "ID", "condition", "setup", "human_score", "checker_verdict",
        "mechanism_pass_rate", "specifics_pass_rate", "safety_pass_rate",
    ]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for c in cells:
            w.writerow({k: c[k] for k in fields})

    # (checker PASS?, human meets threshold?) pairs for the two thresholds
    strict = [(c["checker_verdict"] == "PASS", c["human_score"] == 2) for c in cells]
    lenient = [(c["checker_verdict"] == "PASS", c["human_score"] >= 1) for c in cells]

    print(f"Wrote {OUT_CSV.relative_to(ROOT)}  ({len(cells)} cells)")
    if args.wrap_code:
        recovered = sum(1 for c in cells if c["_n_blocks"])
        print(f"--wrap-code: ON  (recovered code fences in {recovered}/"
              f"{len(cells)} cells)")
    else:
        print("--wrap-code: OFF  (pass --wrap-code to recover stripped "
              "```python fences)")
    print()
    print("=== Checker PASS vs human score ===")
    print(f"(a) agreement  PASS <-> human==2 : {agreement(strict):.3f}")
    print(f"(b) agreement  PASS <-> human>=1 : {agreement(lenient):.3f}")
    print(f"(c) Cohen's kappa (human==2)     : {cohen_kappa(strict):.3f}")
    print(f"    Cohen's kappa (human>=1)     : {cohen_kappa(lenient):.3f}")
    print()

    print("(d) disagreeing cells (checker verdict vs human threshold):")
    any_dis = False
    for c in cells:
        passed = c["checker_verdict"] == "PASS"
        flags = []
        if passed != (c["human_score"] == 2):
            flags.append("==2")
        if passed != (c["human_score"] >= 1):
            flags.append(">=1")
        if not flags:
            continue
        any_dis = True
        failed = ", ".join(c["_failed"]) if c["_failed"] else "(none failed)"
        print(
            f"  {c['ID']:<5} {c['condition']:<7} "
            f"human={c['human_score']} checker={c['checker_verdict']:<4} "
            f"disagrees@[{'/'.join(flags)}]  failed: {failed}"
        )
    if not any_dis:
        print("  (none)")


if __name__ == "__main__":
    main()
