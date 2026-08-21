# Table A7: Router ablation — tree vs flat

*Generated 2026-07-16 | embedder=hashing-fallback | L1 top-k=2 | L2 top-k=3 | budget=6 | items=50 (covered 45, uncovered 5)*

Hit = the item's source artifact (`target_artifact`) lands in the top-k
at that level. Aggregates are over covered items only; uncovered items
(A4 targets — the bare-metal distractor with no router counterpart — and
items with an empty `target_artifact`) are listed but not scored.

## Aggregate hit rates

| level | tree | flat |
|---|---|---|
| L0 site | 100.0% | n/a (no site level) |
| L1 use-case @2 | 73.3% | n/a (no use-case level) |
| L2 artifact @3 | 68.9% | 86.7% |
| chunk-level | 68.9% | 86.7% |

## Per-item results

| item | target | covered | tree L0 | tree L1 | tree L2 | tree chunk | flat L2 | flat chunk |
|---|---|---|---|---|---|---|---|---|
| AV01 | A2 | yes | Y | . | . | . | Y | Y |
| AV02 | A2 | yes | Y | . | . | . | Y | Y |
| AV03 | A2 | yes | Y | . | . | . | Y | Y |
| AV04 | A2 | yes | Y | Y | Y | Y | Y | Y |
| N01 | A1 | yes | Y | Y | Y | Y | Y | Y |
| N02 | A2 | yes | Y | Y | Y | Y | Y | Y |
| N03 | A2 | yes | Y | Y | Y | Y | Y | Y |
| N04 | A3 | yes | Y | Y | Y | Y | Y | Y |
| N05 | A4 | no (uncovered) | - | - | - | - | - | - |
| N06 | A2 | yes | Y | Y | Y | Y | Y | Y |
| N07 | A1 | yes | Y | Y | Y | Y | Y | Y |
| N08 | A5 | yes | Y | Y | Y | Y | Y | Y |
| N09 | A2,A6 | yes | Y | Y | Y | Y | Y | Y |
| N10 | A2,A3 | yes | Y | Y | Y | Y | Y | Y |
| N11 | A2,A5 | yes | Y | Y | Y | Y | Y | Y |
| N12 | A2,A6 | yes | Y | Y | Y | Y | Y | Y |
| N13 | A6 | yes | Y | . | . | . | . | . |
| N14 | - | no (uncovered) | - | - | - | - | - | - |
| N15 | A5 | yes | Y | Y | Y | Y | Y | Y |
| N16 | A4 | no (uncovered) | - | - | - | - | - | - |
| N17 | - | no (uncovered) | - | - | - | - | - | - |
| N18 | - | no (uncovered) | - | - | - | - | - | - |
| P01 | A2 | yes | Y | . | . | . | Y | Y |
| P02 | A3 | yes | Y | Y | . | . | . | . |
| P03 | A2 | yes | Y | Y | Y | Y | Y | Y |
| P04 | A3 | yes | Y | Y | . | . | . | . |
| P05 | A2 | yes | Y | . | . | . | . | . |
| P06 | A2 | yes | Y | . | . | . | Y | Y |
| P07 | A1 | yes | Y | Y | Y | Y | Y | Y |
| P08 | A2 | yes | Y | Y | Y | Y | Y | Y |
| P09 | A2 | yes | Y | . | . | . | . | . |
| P10 | A2 | yes | Y | . | . | . | Y | Y |
| P11 | A1 | yes | Y | Y | Y | Y | Y | Y |
| P12 | A1 | yes | Y | Y | Y | Y | Y | Y |
| P13 | A1 | yes | Y | Y | Y | Y | Y | Y |
| P14 | A1 | yes | Y | Y | Y | Y | Y | Y |
| P15 | A2 | yes | Y | Y | Y | Y | Y | Y |
| P16 | A2 | yes | Y | Y | Y | Y | Y | Y |
| P17 | A2 | yes | Y | Y | Y | Y | Y | Y |
| P18 | A2 | yes | Y | Y | Y | Y | Y | Y |
| P19 | A2 | yes | Y | Y | Y | Y | Y | Y |
| P20 | A3 | yes | Y | Y | Y | Y | Y | Y |
| P21 | A3 | yes | Y | Y | Y | Y | Y | Y |
| P22 | A3 | yes | Y | Y | Y | Y | Y | Y |
| P23 | A3 | yes | Y | Y | Y | Y | Y | Y |
| P24 | A3 | yes | Y | Y | Y | Y | Y | Y |
| P25 | A2 | yes | Y | . | . | . | Y | Y |
| P26 | A2 | yes | Y | . | . | . | Y | Y |
| P27 | A2 | yes | Y | . | . | . | . | . |
| P28 | A1 | yes | Y | Y | Y | Y | Y | Y |
