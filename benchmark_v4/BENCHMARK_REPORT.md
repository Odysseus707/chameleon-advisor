# Benchmark v4 — Session Report

Summary of the work completed in this Claude Code session: the tooling built, the
calibration findings, the decisions taken, and the pitfalls hit along the way.

---

## 1. Scope of the session

- **Calibrate the automated checker against human scores** (v3 data) — measure how well `harness.runner.evaluate()` agrees with human graders.
- **Recover code fences** stripped when model outputs were pasted into Excel.
- **Generate run prompts** for every item × condition (blind + fed).
- **Scaffold empty answer files** so responses can just be pasted in.
- **This report.**

Hard constraints held throughout: **pyyaml + openpyxl + stdlib only**; **never modify anything under `harness/` or `items/`** (read-only).

---

## 2. Deliverables

| File | Purpose |
|---|---|
| `tools/calibrate_v3.py` | Grade every scored v3 cell with the checker; emit `exports/calibration_v3.csv`; print agreement + Cohen's κ + disagreements. Has a `--wrap-code` flag. |
| `exports/calibration_v3.csv` | One row per cell: ID, condition, setup, human_score, checker_verdict, per-group pass rates. |
| `tools/make_run_prompts.py` | Build `prompts/<condition>/<ITEM>.txt` for all 50 items (114 files). |
| `prompts/` | Blind = prompt verbatim; fed = fixed reference-material wrapper + question. |
| `runs/<condition>/<system>/<ITEM>.md` | 342 empty placeholders (3 systems) for pasting raw answers; layout the notebook batch cell expects. |
| `BENCHMARK_REPORT.md` | This file. |

---

## 3. Key decisions

- **Condition mapping (v3):** Setup contains "blind" → `blind`; contains "artifact" → `matched`. Only rows with **both** a score and an output are scored.
- **Two agreement thresholds:** `human==2` (fully correct) and `human>=1` (any credit). Cohen's κ computed for both, in pure stdlib.
- **Checker verdict = binary** PASS/FAIL (`all_passed`), because the checker cannot award partial credit — this shapes how it lines up with human 0/1/2.
- **Code-fence recovery is opt-in** (`--wrap-code`) and **self-validating**: a candidate block is only fenced if it `ast.parse()`s as Python. Prose and bash/dockerfile blocks fail the gate and are left alone — no false code.
- **Fed-prompt wrapper is fixed verbatim** (intro line → `=== REFERENCE MATERIAL ===` → artifacts in listed order, blank-line separated → `=== END REFERENCE MATERIAL ===` → blank → `Question: <prompt>`).
- **Systems chosen:** `s1-chatbot`, `s2-gpt`, `s3-sonnet`. Placeholder generation **never clobbers** an existing (already-pasted) file.

---

## 4. Calibration findings

- **Root problem:** 0/84 pasted outputs kept their ``` fences (stripped on paste). Without them the checker saw no code → near-universal FAIL → **κ ≈ 0**.
- **After `--wrap-code`:** 55/84 cells recovered code.

| Threshold | Agreement (before → after) | κ (before → after) |
|---|---|---|
| `human==2` | 0.536 → **0.893** | 0.000 → **0.783** |
| `human>=1` | 0.393 → **0.798** | 0.000 → **0.611** |

- **κ 0.78 = substantial agreement.** The checker is a trustworthy proxy for "fully correct."
- **Errors are one-directional (the safe way):** almost all disagreements are checker-FAIL where the human was more generous. The checker essentially never rubber-stamps a bad answer (≈ no false positives).
- **κ(==2) > κ(>=1) is meaningful:** the checker models *correct*, not *partially useful*. It won't credit prose that merely describes the right API — appropriate for a code-generation benchmark.

### The 20 disagreements, categorised

- **Style docks** (checker PASS, human=1): P04, P05 — working answer, human deducted polish. Benign.
- **Partial-credit prose** (human=1, checker FAIL): human credited a described-but-not-executable approach. Checker correctly demands working code.
- **Checker false-negatives** (human=2, checker FAIL): **P03, P08** — real, fixable checker gaps (see below).
- **Human-generous on trap code** (human=2, checker FAIL): P28 matched — answer emitted bare-metal `add_node_reservation`; checker correctly flagged it.

### Two concrete checker gaps (actionable)

- **P03** — expects `machine_type`/`machine_name` kwarg, but all 3 accepted answers used `add_device_reservation(devices=[...])` (pin a discovered device). Valid equivalent the check doesn't accept.
- **P08** — expects `execute` call + `['output']`/`["output"]` capture tokens; all 3 accepted answers used a different capture idiom. Check is under-specified.
- Fixing both would likely lift κ(==2) toward ~0.85–0.9. **Not done** — requires editing `harness/checks.py`, which was off-limits without explicit go-ahead.

---

## 5. Code-fence recovery — how it works

- **Skip if already fenced:** text containing ``` is returned unchanged.
- **Repair glued labels:** a collapsed fence like `pythonimport chi` is un-glued **only** when the remainder starts with a Python keyword, `#`, or a known python-chi domain root (`chi`, `container`, `lease`, …). Real words (`shutil` → `sh`+`util`) are left intact.
- **Classify lines** anchor / continuation / prose; prose segments the text; a segment with ≥1 anchor is a code candidate.
- **Parse gate:** dedent + `ast.parse()`; fence only if it parses (trims up to 5 trailing prose lines swept in).
- **Multiple blocks per answer** are each fenced separately; `extract_code()` concatenates them.

---

## 6. Pitfalls & how we got through them

- **Wrong Python interpreter** — `python3` resolved to Homebrew without openpyxl (`ModuleNotFoundError`). *Fix:* always invoke `.venv/bin/python` explicitly; venv activation hadn't taken in that shell.
- **Stripped fences → κ = 0** — the calibration looked broken until we traced it to Excel dropping ``` on paste. *Fix:* the `--wrap-code` heuristic.
- **Residual glued label** `pythoncontainer_name` not stripped (head ≠ exact root). *Fix:* boundary match `h == r or h.startswith(r + "_")` — catches `container_name`, `reservation_id`; rejects `containment`.
- **Over-eager fencing risk** (bash/dockerfile blocks, prose). *Fix:* the `ast.parse()` gate — non-Python fails and is left alone. Verified: forbidden calls in *comments* correctly PASS (AST ignores comments); real forbidden code correctly FAILS.
- **CSV column leakage** — private helper keys (`_failed`, `_n_blocks`) could bleed into output. *Fix:* fixed 8-column field list projected explicitly.
- **Fact-Forcing gate** blocked each first Bash / Write, requiring stated facts (callers, no-duplicate, data shape, verbatim instruction). *Handled* by presenting those facts before each operation.

---

## 7. Layout produced

```
prompts/<condition>/<ITEM>.txt      114 files  (blind + fed conditions)
runs/<condition>/<system>/<ITEM>.md 342 empty  (s1-chatbot, s2-gpt, s3-sonnet)
exports/calibration_v3.csv          84 rows
```

- Conditions present: `blind` (50), `matched` (47), `heldout` (14), `uncovered` (3) — each item only gets folders for the conditions in its `fed_sets`.
- Notebook batch cell globs `runs/*/*/*.md` and scores whatever is present. **Empty files score FAIL until filled** (no code) — harmless, but a `if not text.strip(): continue` guard can skip blanks if wanted.

---

## 8. Recommended next steps

1. Paste answers into `runs/…`, run the notebook batch cell.
2. Patch the **P03** (`devices=` equivalence) and **P08** (capture idioms) checks in `harness/checks.py`, then re-run calibration to confirm the κ lift.
3. Decide whether prose-only answers should earn any credit — currently they don't (by design).
