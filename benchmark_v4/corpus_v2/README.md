# corpus_v2: artifact ingestion, stages 1 to 3

Deterministic half of the ingestion pipeline. **No LLM is called anywhere in
this directory**, and no stage here adds an API cost. Tier B extraction is not
implemented and is deliberately out of scope.

## Why everything lives here

`run_bench.py:90` globs `grounding/*.md` and `tier_assign.py:33` globs
`grounding/A*.md`. The frozen provenance hash `bench_grounding_sha256` depends
on both. Physical separation is therefore the enforcement mechanism: nothing
this pipeline produces is written to `benchmark_v4/grounding/`, the workspace
`grounding/`, `benchmark_v4/items/`, or `extractions/`. Those are read only.

## Run order

```bash
V=.venv/bin/python
$V corpus_v2/tools/parity_baseline.py pin      # step 0, before anything else
$V corpus_v2/tools/catalog.py build            # compendium -> catalog.jsonl
$V corpus_v2/tools/fetch.py run --jobs 10      # stage 1 -> cache/repos, fetch_state.jsonl
$V corpus_v2/tools/triage.py run               # stage 2 -> manifest.tsv
$V corpus_v2/tools/phases.py run               # stage 3 -> phases.tsv
$V corpus_v2/tools/parity_baseline.py verify   # must stay green
```

`parity_baseline.py verify` is the gate. Run it on every commit that touches
`harness/` or `benchmark_v4/`. It costs minutes and no API calls.

## Files

| Path | What |
|---|---|
| `parity/` | the pinned v1 measurement surface (step 0), immutable |
| `catalog.jsonl` | 205 artifacts: ids, tags, repo URLs, exclusions, v1 duplicate flags |
| `fetch_state.jsonl` | one record per repo URL: status, size, mode, content hash |
| `cache/repos/<owner>__<name>/` | the clones, keyed by repo so shared repos fetch once |
| `manifest.tsv` | stage 2 output, the 18-column audit manifest |
| `phases.tsv` | stage 3 output, phase 1 / 2 / 3 assignment per artifact |

## FETCH_NOTES

**The live Trovi API is unreachable**, but an offline capture of it is not.
`https://trovi.chameleoncloud.org/api/artifacts` answers 404 on every path tried
(`artifacts`, `artifacts/`, `v1/artifacts`); the root answers 302. However
`compendium/trovi_records.json` is a 460-record dump of that API, and all 205
catalog artifacts match into it by title, so UUID, authors, and the
authoritative `contents` URN are all available offline. `catalog.py` joins it.

Contents URNs come in several schemes. Measured over the 205 catalog artifacts:
`git` 151, `chameleon` 23, `http` 16, `heat_template` 6, `chi-tacc` 4,
`chi-uc` 1, `kvm-tacc` 1, `zenodo` 1, and 2 with no version record. The `git`
form is `urn:trovi:contents:git:<url>@<sha>`, which pins a commit and is
stronger provenance than the HEAD clone stage 1 currently takes.

On the wrapper artifacts specifically. 16 artifacts list
`ChameleonCloud/trovi_external_artifacts_deployment`, and exactly those 16 carry
an `http` contents URN of the form `urn:trovi:contents:http:<uuid>`: a
Trovi-hosted blob, not a git repo. Of the 16, only **4** list the wrapper and
nothing else; the other 12 also link a real repo, which is fetched normally.
So 4 artifacts are genuinely unresolvable here, and the reason is specific:
their body is a Trovi-hosted blob whose only retrieval path is the live API
endpoint that is down. They are recorded `unfetchable` rather than cloned as an
empty shim.

**Size cap.** 200 MB. Above it, sparse-checkout limited to `*.ipynb`, `*.py`,
`README*`, `*.md`, in non-cone mode, because these are file globs that must
apply at every depth. 20 repos took this path, the largest `amalia13977/exp_1`
at 1.4 GB. `tensorflow/models` (644 MB) and `dealii/dealii` (390 MB) are among
them, which is exactly what the cap exists for.

**Known fetch failures.** Six non-wrapper URLs: three repositories no longer
exist at the stated URL, and three fail at checkout (`chi-in-a-box` twice,
`repro-eipsim`). The checkout failures look like case-insensitive filename
collisions on macOS rather than anything upstream.

## Detection, and what it will miss

`detect.py` holds the call vocabulary, taken from the as-built map's measured
python-chi surface. Strong calls are unambiguously Chameleon and sufficient
alone. Weak calls (`execute`, `upload`, `submit`, `Container`, `Lease`,
`Server`) collide with ordinary Python and count only once a strong call or a
chi-family import is already present in the same repo.

Site detection matches `use_site` and `choose_site` both, on the terminal name,
so `chi.use_site`, bare `use_site` after `from chi import`, and
`context.choose_site` all land. The measured split is 11 / 6 / 10, so anchoring
on `chi.use_site` alone would miss roughly a third.

Expected false-negative modes, in order of likelihood:

1. **Provisioning that is not Python.** Setup living in `.sh`, Ansible,
   Terraform, a `Makefile`, or a `docker run` line is invisible to an AST scan
   of `.py` and `.ipynb`. This is the big one.
2. **Provisioning described only in prose.** A README saying "reserve a
   `compute_skylake` node" with no code has no call to match.
3. **Notebook size.** Already bit once: a 9.4 MB notebook was skipped whole by
   the byte cap, hiding 8 provisioning cells, because notebook size is driven by
   embedded output images rather than by code. Fixed by capping notebooks on
   extracted source instead, but any cap can do this again.
4. **Vendored upstream trees.** Deliberately skipped (`site-packages`, `venv`,
   `.ipynb_checkpoints`). Real provisioning code committed inside such a
   directory would be missed.

False positives are constrained by the AST: a `def create_server(...)` or an
`__all__` entry is not a call and does not match, which a regex scan gets wrong.
