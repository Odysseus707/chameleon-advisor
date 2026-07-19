# CHI@Edge Coding Benchmark v4

Executable-checker benchmark for CHI@Edge (Chameleon Cloud) coding assistance.
Built for the OSRE 2026 project "From Lookup to Reasoning": it measures whether
grounding LLMs in Trovi reproducibility artifacts produces broadly transferable
CHI@Edge competence (H1) or task-specific lookup (H0), and it is the fixed
yardstick the chi-edge-advisor system will be evaluated against end to end.

v4 upgrades v3 (28 prompts, single human grader) with SWE-bench-style
machine-verifiable ground truth: every item ships AST-based checkers, and a gold
answer is admitted only after passing 100% of its own checkers.

## Layout

```
items/            50 item YAMLs (P01-P28 ported from v3, N01-N18 new, AV01-AV04 availability)
harness/          checks.py (checker library) · runner.py (evaluate answers)
                  validate_golds.py (admission gate) · tier_assign.py (computed tiers)
                  stub_chi/ (offline chi package for snapshot execution)
snapshots/        synthetic Blazar snapshot (flagged; replace with a recorded one)
grounding/        A1-A6 flattened artifact grounding files (fed as context in runs)
extractions/      A1-A6 structured extractions (Opus, grep-verified) = gold provenance
notebooks/        validate_golds.ipynb (gate + tier + single/batch scoring)
exports/          benchmark_v4.xlsx (grading workspace) · gate/tier reports (JSON)
tools/            build_items.py (single source of truth) · export_xlsx.py · v3_prompts.jsonl
benchmark_v4_decisions.md   decision & reroute log D01-D17 (milestone-report raw material)
```

## Quick start

```bash
python harness/validate_golds.py      # gate: 50/50 golds must pass own checkers
python harness/tier_assign.py         # computed tiers; exits nonzero on mismatch
python -m harness.runner --item items/P16.yaml --answer my_answer.md
jupyter lab notebooks/validate_golds.ipynb   # same, plus batch scoring of runs/
```

Editing items: change `tools/build_items.py` (never the YAMLs directly), rerun
it, then rerun both gates. Log any gold rejection or token fix in the decisions
file.

## Scoring model

1. **Checker verdict (primary).** AST-level checks; generation-equivalent (D01):
   golds are OO python-chi; imperative earns full credit iff trap-free,
   including `platform_version=2` on `create_container`. Forbidden-call checks
   are AST-only and string checks run on code blocks only, so prose like "do NOT
   use add_node_reservation" is never penalized (D10).
2. **Human 0-2 directiveness (secondary).** Same rubric as v3, for continuity
   and for qualities checkers cannot see.
3. **Group reporting (the H0/H1 instrument, D03).** Every check is tagged
   `mechanism` / `specifics` / `safety`; pass rates are reported per group per
   condition. Under held-out feeding, H1 (transfer) predicts mechanism passes
   while specifics fail; H0 predicts both fail.

## Conditions and computed tiers (D04/D14)

Each item declares fed_sets (blind / matched / heldout / uncovered).
`tier_assign.py` computes the tier of every (item, fed_set) pair from key-token
coverage of the fed grounding files - tiers are measured, never asserted.
Current distribution (114 pairs, 0 intent mismatches):

- matched: T1 x32, T2 x7, T3 x6, T4 x2 (P27 and AV04 are honestly T4 even
  matched: `supported_device_profiles` is documented in no artifact)
- heldout (GEN subset, 14 items): all T4 by construction
- uncovered (T4b abstention items N14/N17/N18): T4 with hallucination canaries

Key-token policy: only CHI@Edge-specific load-bearing tokens count;
prompt-supplied values and world knowledge are excluded; tokens must be
generation-agnostic (D16 documents the one violation the gate itself caught).

## Verification levels

- **V0** (46 items): static AST checking only. Golds are never executed.
- **V1** (AV01-AV04): additionally executed against the Blazar snapshot via
  `harness/stub_chi`; stdout compared to expectations (catches the
  filter_reserved direction bug at runtime, not just statically).
- **V2** (live testbed execution): **dropped for this cycle by decision of the
  fellow** (D05). No lease is ever created by this benchmark.

## Limitations (state these in any writeup)

- The shipped snapshot is **synthetic** (flagged in-file, D13). Record a real
  Blazar snapshot with the advisor's replay harness (same schema) before
  reporting availability numbers.
- V1 scoring executes model-generated code in a subprocess. Run in a disposable
  environment.
- Duration checks require statically determinable durations; manual start/end
  date answers fail and need hand adjudication (D12).
- Checker-vs-human agreement is not yet measured: run the checkers over the 168
  graded v3 cells (same prompts, P01-P28) and report agreement + Cohen's kappa.
- Benchmark checkers are independent of and a superset of the advisor's
  validator (D07); advisor evaluation must report validator ON and OFF.

## Milestone mini-report

Every milestone gets a concise two-page report. For this milestone the draft is
`reports/milestone_benchmark_v4.tex` (IEEEtran, matching prior deliverables);
its factual content is drawn from `benchmark_v4_decisions.md` and the two JSON
reports in `exports/`. The decisions log is the failure/reroute record the
fellowship documentation requirement asks for - keep appending to it.
