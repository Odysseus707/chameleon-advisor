# Reference baselines

Two scored CSVs, shipped so that anyone installing this package has a yardstick
to compare their own model against. Collected 2026-08-21.

| file | arms | conditions | rows |
|---|---|---|---|
| `tejas_scores.csv` | `s10-…-noadv`, `s10-…-adv` | blind, matched, heldout, uncovered | 660 |
| `isolation_scores.csv` | the two above plus `s11-…-heuristic-adv` | blind | 402 |

All three arms are **`Meta-Llama-3.3-70B-Instruct`** served through the TACC
Tejas gateway, scored with the checkers in this package.

| arm | advisor | advisor's reasoner |
|---|---|---|
| `s10-llama70b-tejas-noadv` | off | — |
| `s11-llama70b-heuristic-adv` | on | `_heuristic` (`LLM_PROVIDER=none`) |
| `s10-llama70b-tejas-adv` | on | the same 70B model |

`s11` exists to separate *the advisory* from *the model that writes it*: it is
identical to `s10-adv` in model, corpus, prompts and gating, differing only in
which reasoner produced the advisory.

## What they show

Blind condition, 134 paired items:

| group | OFF | + heuristic advisor | + 70B advisor |
|---|---|---|---|
| mechanism | 7.8% | **46.1%** | 45.2% |
| specifics | 9.2% | **51.3%** | 47.9% |
| safety | 92.5% | 97.0% | **99.0%** |
| feasibility | 36.8% | 62.7% | **71.5%** |
| capability | 45.0% | 58.9% | **66.2%** |

Of the +21.2 capability gain, the heuristic advisory supplies +14.0 and the 70B
reasoner adds +7.2. On mechanism and specifics the heuristic is *slightly
better*. The reasoner earns its keep only on the two axes fed by live state.

## What they are not comparable to

Read this before quoting any number.

- **Not a leaderboard.** One model on one gateway. The arms are controlled
  against *each other*, and against nothing else.
- **Not comparable to the earlier `s3`/`s4` node-era pair.** Three things differ
  at once: the model (`qwen2.5:32b` → Llama-3.3-70B), the corpus (July docs → a
  fresh scrape), and the advisor's own reasoner. Treat `s10`/`s11` as a separate,
  internally-controlled experiment.
- **The corpus is a fresh scrape.** Retrieval quality may differ from any other
  run, including your own.
- **Uncovered `mechanism` is n=3.** Not meaningful; keep it out of summaries.
- **The snapshot underlying feasibility is synthetic** unless an item names its
  own recorded one.

## The finding worth knowing before you interpret your own numbers

The *same* heuristic advisory produced **+0.6** capability on `qwen2.5:32b` and
**+14.0** on Llama-3.3-70B. The advisory text barely changed; what changed is
the model's ability to consume injected grounding.

So grounding appears to pay off only above a model-capability threshold. If you
evaluate retrieval augmentation on a small local model and conclude retrieval
does not help, the more likely reading is that your model cannot exploit it.
Compare against the OFF arm *of a comparable model* before drawing that
conclusion.

## Reproducing

The answer files these were scored from are not shipped (2100 files); only the
scores. In a checkout of the source repo, where the record is present:

```bash
chi-edge-bench score-runs \
  --systems s10-llama70b-tejas-noadv,s10-llama70b-tejas-adv \
  --csv /tmp/check.csv
diff /tmp/check.csv chi_edge_bench/data/baselines/tejas_scores.csv
```

`tests/test_scoring_stable.py` runs exactly this and fails on any difference, so
a refactor cannot silently change a published measurement.

## Schema

One row per (condition, system, item):

```
condition,system,item,status,fences,recovered,code_seen,all_passed,
failed_checks,rank1,
mechanism_passed,mechanism_total,specifics_passed,specifics_total,
safety_passed,safety_total,feasibility_passed,feasibility_total,
capability_passed,capability_total
```

A group's `_total` is 0 when that group does not apply to the item — the core
and reservation group families never co-occur.
