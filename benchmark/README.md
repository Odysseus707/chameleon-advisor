# chi-edge-bench

Executable-checker benchmark for CHI@Edge (Chameleon Cloud) coding assistance.

Built for the OSRE 2026 project *From Lookup to Reasoning*. It measures whether
grounding an LLM in Trovi reproducibility artifacts produces broadly
transferable CHI@Edge competence (H1) or task-specific lookup (H0) — and it is
the fixed yardstick the `chi-edge-advisor` system is evaluated against.

Every item ships AST-based checkers and a gold answer that was admitted only
after passing 100% of its own checkers, so **scoring needs no human grader, no
network and no API key**.

```bash
pip install "git+https://github.com/<you>/chameleon-work.git#subdirectory=benchmark"
chi-edge-bench selftest        # 134/134 golds pass their own checkers
```

## The benchmark

134 items in two suites:

| suite | items | groups scored | what it asks |
|---|---|---|---|
| `core` | 50 (P01–P28, N01–N18, AV01–AV04) | mechanism, specifics, safety | can it write correct python-chi? |
| `reservation` | 84 (R01–R84) | feasibility, capability, safety | can it pick a device that is both free *and* able to do the job? |

Each item declares which **conditions** it is graded under — `blind` (nothing
fed), `matched`, `heldout`, `uncovered` — and reservation items additionally
name the Blazar **snapshot** they are graded against, so live-state reasoning is
testable offline and deterministically.

## Four ways to get answers, cheapest first

### 1. Drop-in — no key, no network, no SDK

The whole loop with one dependency (PyYAML):

```bash
chi-edge-bench prompts                       # 414 prompt files -> workspace
# answer them however you like, writing:
#   runs/<condition>/<system>/<ITEM>.md
chi-edge-bench score-runs --systems s20-my-model
chi-edge-bench compare --csv <the CSV that printed>
```

### 2. Any OpenAI-compatible endpoint

One adapter reaches OpenAI, a local Ollama, vLLM, and LiteLLM gateways. A key is
required only for `api.openai.com`, because only it requires one:

```bash
pip install "chi-edge-bench[openai]"

chi-edge-bench collect openai \
  --base-url http://localhost:11434/v1 \
  --model qwen2.5:7b-instruct \
  --system s20-my-model
```

### 3. Anthropic

```bash
pip install "chi-edge-bench[anthropic]"
export ANTHROPIC_API_KEY=...
chi-edge-bench collect anthropic --model claude-sonnet-5 --system s21-sonnet
```

### 4. The full RAG + advisor pipeline

Needs the `RAG-docs-chameleon` app, a built vectorstore and `chi-edge-advisor`:

```bash
pip install "chi-edge-bench[fork]"
chi-edge-bench collect fork --advisor on  --system s22-mine-adv
chi-edge-bench collect fork --advisor off --system s22-mine-noadv
```

## Where things live

Read-only benchmark data ships **inside** the package; everything a run produces
is written **outside** it. `chi-edge-bench where` prints both.

The workspace is resolved as, first match winning:

1. `--workspace PATH`
2. `$CHI_BENCH_WORKSPACE`
3. the nearest directory at or above the cwd holding a `.chi-edge-bench` file
4. `./chi-edge-bench-work`

Rule 3 is why running any command from inside this repo reads and writes the
real measurement record in `benchmark/runs/` rather than starting an empty one.

## Reference baselines

`chi-edge-bench compare` puts your arm beside three shipped reference arms, all
`Meta-Llama-3.3-70B-Instruct` via the TACC Tejas gateway on the blind condition:

```
group          advisor OFF   + heuristic advisor   + 70B advisor
mechanism             7.8%                 46.1%           45.2%
specifics             9.2%                 51.3%           47.9%
feasibility          36.8%                 62.7%           71.5%
capability           45.0%                 58.9%           66.2%
```

See `chi_edge_bench/data/baselines/baselines_summary.md` for what these are and
are **not** comparable to before quoting them.

## Scoring model

1. **Checker verdict (primary).** AST-level checks, generation-equivalent (D01):
   golds are OO python-chi, and imperative code earns full credit iff it is
   trap-free, including `platform_version=2` on `create_container`.
   Forbidden-call checks are AST-only and string checks run on code blocks only,
   so prose like "do NOT use `add_node_reservation`" is never penalised (D10).
2. **Human 0–2 directiveness (secondary).** For qualities checkers cannot see.
3. **Group reporting (the H0/H1 instrument, D03).** Every check is tagged
   `mechanism` / `specifics` / `safety` / `feasibility` / `capability`, and rates
   are reported per group per condition — never blended. Under held-out feeding,
   H1 predicts mechanism passes while specifics fail; H0 predicts both fail.

The two group families never co-occur in one item, and `feasibility` (fed by the
snapshot) is kept separate from `capability` (fed by `capability_table.yaml`)
because a blended rate would be dominated by the easy deterministic half.

## Verification levels

- **V0** — static AST checking only. Golds are never executed.
- **V1** (AV01–AV04) — additionally executed against a Blazar snapshot via
  `harness/stub_chi`, with stdout compared to expectations.
- **V2** (live testbed execution) — **dropped by decision of the fellow** (D05).
  This benchmark never creates a lease.

> **V1 scoring executes model-generated code in a subprocess.** Run it in a
> disposable environment.

## Limitations — state these in any writeup

- The default snapshot is **synthetic** (flagged in-file, D13). Record a real
  Blazar snapshot before reporting availability numbers.
- Duration checks require statically determinable durations; answers using
  manual start/end dates fail and need hand adjudication (D12).
- Checker-vs-human agreement is not yet measured. Running the checkers over the
  168 graded v3 cells (same prompts, P01–P28) and reporting Cohen's kappa is the
  outstanding validation.
- Benchmark checkers are independent of, and a superset of, the advisor's own
  validator (D07); advisor evaluation must report validator ON and OFF.
- The reference baselines are a single model on a single gateway. They are an
  internally-controlled A/B, not a leaderboard.

## Development

```bash
pip install -e ".[dev]"
pytest                      # 203 tests, ~6 s, no network
chi-edge-bench selftest     # the same gold gate, via the CLI
```

Editing items: change `chi_edge_bench/tools/build_items.py` — the single source
of truth — rerun it, then rerun both gates. Log any gold rejection or token fix
in `benchmark_v4_decisions.md`.

`tools/provenance.py` binds every collected answer to `sha256(prompt)`, so
editing an item's wording invalidates the runs that answered it rather than
silently changing what a number means. `chi-edge-bench provenance` checks this.

## License

MIT. See `LICENSE`.
