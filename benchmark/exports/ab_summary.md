# Run scores summary

## Fill status (non-empty / total answer files)

condition s3-chatbot-noadvs4-chatbot-adv
----------------------------------------
blind            134/134       134/134
matched            95/95         95/95
heldout            62/62         62/62
uncovered          39/39         39/39

## Overall PASS rate (all checkers green; scored answers only)

condition s3-chatbot-noadvs4-chatbot-adv
----------------------------------------
blind         7/134 (5%)  13/134 (10%)
matched      22/95 (23%)   46/95 (48%)
heldout      10/62 (16%)    9/62 (15%)
uncovered      3/39 (8%)     0/39 (0%)

## Rates on COMMON items only (selection-bias guard)

### blind — 134 items answered by all of: s3-chatbot-noadv, s4-chatbot-adv

metric    s3-chatbot-noadvs4-chatbot-adv
----------------------------------------
PASS          7/134 (5%)  13/134 (10%)
mechanism     9/115 (8%)    8/115 (7%)
specifics   16/119 (13%)  27/119 (23%)
safety     182/199 (91%) 181/199 (91%)
feasibility  84/228 (37%) 151/228 (66%)
capability 173/358 (48%) 175/358 (49%)

### matched — 95 items answered by all of: s3-chatbot-noadv, s4-chatbot-adv

metric    s3-chatbot-noadvs4-chatbot-adv
----------------------------------------
PASS         22/95 (23%)   46/95 (48%)
mechanism   44/112 (39%)  50/112 (45%)
specifics   68/119 (57%)  72/119 (61%)
safety     119/132 (90%) 121/132 (92%)
feasibility  64/140 (46%) 116/140 (83%)
capability 111/208 (53%) 178/208 (86%)

### heldout — 62 items answered by all of: s3-chatbot-noadv, s4-chatbot-adv

metric    s3-chatbot-noadvs4-chatbot-adv
----------------------------------------
PASS         10/62 (16%)    9/62 (15%)
mechanism     9/35 (26%)   11/35 (31%)
specifics     6/41 (15%)   13/41 (32%)
safety     104/109 (95%) 105/109 (96%)
feasibility  99/140 (71%) 116/140 (83%)
capability 132/208 (63%) 135/208 (65%)

### uncovered — 39 items answered by all of: s3-chatbot-noadv, s4-chatbot-adv

metric    s3-chatbot-noadvs4-chatbot-adv
----------------------------------------
PASS           3/39 (8%)     0/39 (0%)
mechanism     3/3 (100%)      0/3 (0%)
specifics              —             —
safety       66/67 (99%)  67/67 (100%)
feasibility   48/88 (55%)   71/88 (81%)
capability  51/150 (34%)  22/150 (15%)

## Checker-group pass rates (checks passed / checks run)

### mechanism

condition s3-chatbot-noadvs4-chatbot-adv
----------------------------------------
blind         9/115 (8%)    8/115 (7%)
matched     44/112 (39%)  50/112 (45%)
heldout       9/35 (26%)   11/35 (31%)
uncovered     3/3 (100%)      0/3 (0%)

### specifics

condition s3-chatbot-noadvs4-chatbot-adv
----------------------------------------
blind       16/119 (13%)  27/119 (23%)
matched     68/119 (57%)  72/119 (61%)
heldout       6/41 (15%)   13/41 (32%)
uncovered              —             —

### safety

condition s3-chatbot-noadvs4-chatbot-adv
----------------------------------------
blind      182/199 (91%) 181/199 (91%)
matched    119/132 (90%) 121/132 (92%)
heldout    104/109 (95%) 105/109 (96%)
uncovered    66/67 (99%)  67/67 (100%)

### feasibility

condition s3-chatbot-noadvs4-chatbot-adv
----------------------------------------
blind       84/228 (37%) 151/228 (66%)
matched     64/140 (46%) 116/140 (83%)
heldout     99/140 (71%) 116/140 (83%)
uncovered    48/88 (55%)   71/88 (81%)

### capability

condition s3-chatbot-noadvs4-chatbot-adv
----------------------------------------
blind      173/358 (48%) 175/358 (49%)
matched    111/208 (53%) 178/208 (86%)
heldout    132/208 (63%) 135/208 (65%)
uncovered   51/150 (34%)  22/150 (15%)

## State-sensitivity (does the pick track the environment?)

system           tracked/moved
------------------------------
s3-chatbot-noadv        0/98 (0%)
s4-chatbot-adv       0/278 (0%)

## Uncovered items (abstain-or-discover)

  N14   s3-chatbot-noadv PASS
  N14   s4-chatbot-adv FAIL [abstain_or_discover]
  N17   s3-chatbot-noadv PASS
  N17   s4-chatbot-adv FAIL [abstain_or_discover]
  N18   s3-chatbot-noadv FAIL [profiles_known_only]
  N18   s4-chatbot-adv FAIL [abstain_or_discover]
  R49   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded abstains_when_uncovered]
  R49   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter config_grounded abstains_when_uncovered]
  R50   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded abstains_when_uncovered]
  R50   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter config_grounded abstains_when_uncovered]
  R51   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded abstains_when_uncovered]
  R51   s4-chatbot-adv FAIL [rank1_feasible no_down_types_listed count_feasible ranked_types_subset forbidden_types_listed capability_filter config_grounded abstains_when_uncovered]
  R52   s3-chatbot-noadv FAIL [abstains_when_uncovered]
  R52   s4-chatbot-adv FAIL [forbidden_types_listed abstains_when_uncovered]
  R53   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded abstains_when_uncovered]
  R53   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter config_grounded abstains_when_uncovered]
  R54   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded abstains_when_uncovered]
  R54   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter config_grounded abstains_when_uncovered]
  R55   s3-chatbot-noadv FAIL [forbidden_types_listed abstains_when_uncovered]
  R55   s4-chatbot-adv FAIL [forbidden_types_listed abstains_when_uncovered]
  R56   s3-chatbot-noadv FAIL [forbidden_types_listed abstains_when_uncovered]
  R56   s4-chatbot-adv FAIL [forbidden_types_listed abstains_when_uncovered]
  R57   s3-chatbot-noadv FAIL [no_down_types_listed forbidden_types_listed abstains_when_uncovered]
  R57   s4-chatbot-adv FAIL [no_down_types_listed forbidden_types_listed abstains_when_uncovered]
  R58   s3-chatbot-noadv FAIL [no_down_types_listed forbidden_types_listed abstains_when_uncovered]
  R58   s4-chatbot-adv FAIL [forbidden_types_listed abstains_when_uncovered]
  R59   s3-chatbot-noadv FAIL [forbidden_types_listed abstains_when_uncovered]
  R59   s4-chatbot-adv FAIL [forbidden_types_listed abstains_when_uncovered]
  R60   s3-chatbot-noadv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R60   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R61   s3-chatbot-noadv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R61   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R62   s3-chatbot-noadv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R62   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter config_grounded abstains_when_uncovered]
  R63   s3-chatbot-noadv FAIL [rank1_feasible no_down_types_listed count_feasible ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R63   s4-chatbot-adv FAIL [rank1_feasible no_down_types_listed count_feasible ranked_types_subset forbidden_types_listed capability_filter config_grounded abstains_when_uncovered]
  R64   s3-chatbot-noadv FAIL [forbidden_types_listed abstains_when_uncovered]
  R64   s4-chatbot-adv FAIL [forbidden_types_listed abstains_when_uncovered]
  R65   s3-chatbot-noadv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R65   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter config_grounded abstains_when_uncovered]
  R66   s3-chatbot-noadv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R66   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter config_grounded abstains_when_uncovered]
  R67   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded abstains_when_uncovered]
  R67   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R68   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded]
  R68   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R69   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded]
  R69   s4-chatbot-adv FAIL [rank1_feasible no_down_types_listed count_feasible ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R70   s3-chatbot-noadv PASS
  R70   s4-chatbot-adv FAIL [forbidden_types_listed abstains_when_uncovered]
  R71   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded]
  R71   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R72   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded]
  R72   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R73   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded abstains_when_uncovered]
  R73   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R74   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded abstains_when_uncovered]
  R74   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R75   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded abstains_when_uncovered]
  R75   s4-chatbot-adv FAIL [rank1_feasible no_down_types_listed count_feasible ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R76   s3-chatbot-noadv FAIL [abstains_when_uncovered]
  R76   s4-chatbot-adv FAIL [no_down_types_listed forbidden_types_listed abstains_when_uncovered]
  R77   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded abstains_when_uncovered]
  R77   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R78   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded abstains_when_uncovered]
  R78   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R79   s3-chatbot-noadv FAIL [rank1_feasible count_feasible ranked_types_subset config_grounded]
  R79   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R80   s3-chatbot-noadv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R80   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter]
  R81   s3-chatbot-noadv FAIL [rank1_feasible no_down_types_listed count_feasible ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R81   s4-chatbot-adv FAIL [rank1_feasible no_down_types_listed count_feasible ranked_types_subset forbidden_types_listed capability_filter]
  R82   s3-chatbot-noadv FAIL [forbidden_types_listed abstains_when_uncovered]
  R82   s4-chatbot-adv FAIL [forbidden_types_listed]
  R83   s3-chatbot-noadv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R83   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter]
  R84   s3-chatbot-noadv FAIL [ranked_types_subset forbidden_types_listed capability_filter abstains_when_uncovered]
  R84   s4-chatbot-adv FAIL [ranked_types_subset forbidden_types_listed capability_filter]

## Fence lint (scored answers where the extractor sees NO code)

  These score near-zero mechanically. If the answer visibly contains
  code, the fences were stripped on paste — re-paste or --wrap-code.
  (Prose-only answers to abstention items are fine here.)

  blind/s3-chatbot-noadv/AV01.md  [no fences]
  blind/s3-chatbot-noadv/AV02.md  [no fences]
  blind/s3-chatbot-noadv/AV03.md  [no fences]
  blind/s3-chatbot-noadv/AV04.md  [no fences]
  blind/s3-chatbot-noadv/N01.md  [no fences]
  blind/s3-chatbot-noadv/N02.md  [no fences]
  blind/s3-chatbot-noadv/N03.md  [no fences]
  blind/s3-chatbot-noadv/N04.md  [no fences]
  blind/s3-chatbot-noadv/N10.md  [no fences]
  blind/s3-chatbot-noadv/N12.md  [no fences]
  blind/s3-chatbot-noadv/N13.md  [no fences]
  blind/s3-chatbot-noadv/N14.md  [no fences]
  blind/s3-chatbot-noadv/N15.md  [no fences]
  blind/s3-chatbot-noadv/N18.md  [no fences]
  blind/s3-chatbot-noadv/P04.md  [no fences]
  blind/s3-chatbot-noadv/P05.md  [no fences]
  blind/s3-chatbot-noadv/P06.md  [no fences]
  blind/s3-chatbot-noadv/P07.md  [no fences]
  blind/s3-chatbot-noadv/P10.md  [no fences]
  blind/s3-chatbot-noadv/P12.md  [no fences]
  blind/s3-chatbot-noadv/P13.md  [no fences]
  blind/s3-chatbot-noadv/P14.md  [no fences]
  blind/s3-chatbot-noadv/P15.md  [no fences]
  blind/s3-chatbot-noadv/P16.md  [no fences]
  blind/s3-chatbot-noadv/P17.md  [no fences]
  blind/s3-chatbot-noadv/P18.md  [no fences]
  blind/s3-chatbot-noadv/P19.md  [no fences]
  blind/s3-chatbot-noadv/P20.md  [no fences]
  blind/s3-chatbot-noadv/P21.md  [no fences]
  blind/s3-chatbot-noadv/P23.md  [no fences]
  blind/s3-chatbot-noadv/P24.md  [no fences]
  blind/s3-chatbot-noadv/P25.md  [no fences]
  blind/s3-chatbot-noadv/P26.md  [no fences]
  blind/s3-chatbot-noadv/R01.md  [no fences]
  blind/s3-chatbot-noadv/R02.md  [no fences]
  blind/s3-chatbot-noadv/R03.md  [no fences]
  blind/s3-chatbot-noadv/R04.md  [no fences]
  blind/s3-chatbot-noadv/R05.md  [no fences]
  blind/s3-chatbot-noadv/R06.md  [no fences]
  blind/s3-chatbot-noadv/R07.md  [no fences]
  blind/s3-chatbot-noadv/R08.md  [no fences]
  blind/s3-chatbot-noadv/R09.md  [no fences]
  blind/s3-chatbot-noadv/R10.md  [no fences]
  blind/s3-chatbot-noadv/R11.md  [no fences]
  blind/s3-chatbot-noadv/R12.md  [no fences]
  blind/s3-chatbot-noadv/R13.md  [no fences]
  blind/s3-chatbot-noadv/R14.md  [no fences]
  blind/s3-chatbot-noadv/R15.md  [no fences]
  blind/s3-chatbot-noadv/R16.md  [no fences]
  blind/s3-chatbot-noadv/R17.md  [no fences]
  blind/s3-chatbot-noadv/R18.md  [no fences]
  blind/s3-chatbot-noadv/R19.md  [no fences]
  blind/s3-chatbot-noadv/R20.md  [no fences]
  blind/s3-chatbot-noadv/R21.md  [no fences]
  blind/s3-chatbot-noadv/R22.md  [no fences]
  blind/s3-chatbot-noadv/R23.md  [no fences]
  blind/s3-chatbot-noadv/R24.md  [no fences]
  blind/s3-chatbot-noadv/R25.md  [no fences]
  blind/s3-chatbot-noadv/R26.md  [no fences]
  blind/s3-chatbot-noadv/R27.md  [no fences]
  blind/s3-chatbot-noadv/R28.md  [no fences]
  blind/s3-chatbot-noadv/R29.md  [no fences]
  blind/s3-chatbot-noadv/R30.md  [no fences]
  blind/s3-chatbot-noadv/R31.md  [no fences]
  blind/s3-chatbot-noadv/R32.md  [no fences]
  blind/s3-chatbot-noadv/R33.md  [no fences]
  blind/s3-chatbot-noadv/R34.md  [no fences]
  blind/s3-chatbot-noadv/R35.md  [no fences]
  blind/s3-chatbot-noadv/R36.md  [no fences]
  blind/s3-chatbot-noadv/R37.md  [no fences]
  blind/s3-chatbot-noadv/R38.md  [no fences]
  blind/s3-chatbot-noadv/R39.md  [no fences]
  blind/s3-chatbot-noadv/R40.md  [no fences]
  blind/s3-chatbot-noadv/R41.md  [no fences]
  blind/s3-chatbot-noadv/R42.md  [no fences]
  blind/s3-chatbot-noadv/R43.md  [no fences]
  blind/s3-chatbot-noadv/R44.md  [no fences]
  blind/s3-chatbot-noadv/R45.md  [no fences]
  blind/s3-chatbot-noadv/R46.md  [no fences]
  blind/s3-chatbot-noadv/R47.md  [no fences]
  blind/s3-chatbot-noadv/R48.md  [no fences]
  blind/s3-chatbot-noadv/R49.md  [no fences]
  blind/s3-chatbot-noadv/R50.md  [no fences]
  blind/s3-chatbot-noadv/R51.md  [no fences]
  blind/s3-chatbot-noadv/R52.md  [no fences]
  blind/s3-chatbot-noadv/R53.md  [no fences]
  blind/s3-chatbot-noadv/R54.md  [no fences]
  blind/s3-chatbot-noadv/R55.md  [no fences]
  blind/s3-chatbot-noadv/R56.md  [no fences]
  blind/s3-chatbot-noadv/R57.md  [no fences]
  blind/s3-chatbot-noadv/R58.md  [no fences]
  blind/s3-chatbot-noadv/R59.md  [no fences]
  blind/s3-chatbot-noadv/R60.md  [no fences]
  blind/s3-chatbot-noadv/R61.md  [no fences]
  blind/s3-chatbot-noadv/R62.md  [no fences]
  blind/s3-chatbot-noadv/R63.md  [no fences]
  blind/s3-chatbot-noadv/R64.md  [no fences]
  blind/s3-chatbot-noadv/R65.md  [no fences]
  blind/s3-chatbot-noadv/R66.md  [no fences]
  blind/s3-chatbot-noadv/R67.md  [no fences]
  blind/s3-chatbot-noadv/R68.md  [no fences]
  blind/s3-chatbot-noadv/R69.md  [no fences]
  blind/s3-chatbot-noadv/R70.md  [no fences]
  blind/s3-chatbot-noadv/R71.md  [no fences]
  blind/s3-chatbot-noadv/R72.md  [no fences]
  blind/s3-chatbot-noadv/R73.md  [no fences]
  blind/s3-chatbot-noadv/R74.md  [no fences]
  blind/s3-chatbot-noadv/R75.md  [no fences]
  blind/s3-chatbot-noadv/R76.md  [no fences]
  blind/s3-chatbot-noadv/R77.md  [no fences]
  blind/s3-chatbot-noadv/R78.md  [no fences]
  blind/s3-chatbot-noadv/R79.md  [no fences]
  blind/s3-chatbot-noadv/R80.md  [no fences]
  blind/s3-chatbot-noadv/R81.md  [no fences]
  blind/s3-chatbot-noadv/R82.md  [no fences]
  blind/s3-chatbot-noadv/R83.md  [no fences]
  blind/s3-chatbot-noadv/R84.md  [no fences]
  blind/s4-chatbot-adv/AV01.md  [no fences]
  blind/s4-chatbot-adv/AV02.md  [no fences]
  blind/s4-chatbot-adv/AV03.md  [no fences]
  blind/s4-chatbot-adv/AV04.md  [no fences]
  blind/s4-chatbot-adv/N01.md  [no fences]
  blind/s4-chatbot-adv/N09.md  [no fences]
  blind/s4-chatbot-adv/P07.md  [no fences]
  blind/s4-chatbot-adv/P09.md  [no fences]
  blind/s4-chatbot-adv/P10.md  [no fences]
  blind/s4-chatbot-adv/P12.md  [no fences]
  blind/s4-chatbot-adv/P13.md  [no fences]
  blind/s4-chatbot-adv/P18.md  [no fences]
  blind/s4-chatbot-adv/P24.md  [no fences]
  blind/s4-chatbot-adv/P25.md  [no fences]
  blind/s4-chatbot-adv/P26.md  [no fences]
  blind/s4-chatbot-adv/R01.md  [no fences]
  blind/s4-chatbot-adv/R02.md  [no fences]
  blind/s4-chatbot-adv/R03.md  [no fences]
  blind/s4-chatbot-adv/R04.md  [no fences]
  blind/s4-chatbot-adv/R05.md  [no fences]
  blind/s4-chatbot-adv/R06.md  [no fences]
  blind/s4-chatbot-adv/R07.md  [no fences]
  blind/s4-chatbot-adv/R08.md  [no fences]
  blind/s4-chatbot-adv/R09.md  [no fences]
  blind/s4-chatbot-adv/R10.md  [no fences]
  blind/s4-chatbot-adv/R11.md  [no fences]
  blind/s4-chatbot-adv/R12.md  [no fences]
  blind/s4-chatbot-adv/R13.md  [no fences]
  blind/s4-chatbot-adv/R14.md  [no fences]
  blind/s4-chatbot-adv/R15.md  [no fences]
  blind/s4-chatbot-adv/R16.md  [no fences]
  blind/s4-chatbot-adv/R17.md  [no fences]
  blind/s4-chatbot-adv/R18.md  [no fences]
  blind/s4-chatbot-adv/R19.md  [no fences]
  blind/s4-chatbot-adv/R20.md  [no fences]
  blind/s4-chatbot-adv/R21.md  [no fences]
  blind/s4-chatbot-adv/R22.md  [no fences]
  blind/s4-chatbot-adv/R23.md  [no fences]
  blind/s4-chatbot-adv/R24.md  [no fences]
  blind/s4-chatbot-adv/R25.md  [no fences]
  blind/s4-chatbot-adv/R26.md  [no fences]
  blind/s4-chatbot-adv/R27.md  [no fences]
  blind/s4-chatbot-adv/R28.md  [no fences]
  blind/s4-chatbot-adv/R29.md  [no fences]
  blind/s4-chatbot-adv/R30.md  [no fences]
  blind/s4-chatbot-adv/R31.md  [no fences]
  blind/s4-chatbot-adv/R32.md  [no fences]
  blind/s4-chatbot-adv/R33.md  [no fences]
  blind/s4-chatbot-adv/R34.md  [no fences]
  blind/s4-chatbot-adv/R35.md  [no fences]
  blind/s4-chatbot-adv/R36.md  [no fences]
  blind/s4-chatbot-adv/R37.md  [no fences]
  blind/s4-chatbot-adv/R38.md  [no fences]
  blind/s4-chatbot-adv/R39.md  [no fences]
  blind/s4-chatbot-adv/R40.md  [no fences]
  blind/s4-chatbot-adv/R41.md  [no fences]
  blind/s4-chatbot-adv/R42.md  [no fences]
  blind/s4-chatbot-adv/R43.md  [no fences]
  blind/s4-chatbot-adv/R44.md  [no fences]
  blind/s4-chatbot-adv/R45.md  [no fences]
  blind/s4-chatbot-adv/R46.md  [no fences]
  blind/s4-chatbot-adv/R47.md  [no fences]
  blind/s4-chatbot-adv/R48.md  [no fences]
  blind/s4-chatbot-adv/R49.md  [no fences]
  blind/s4-chatbot-adv/R50.md  [no fences]
  blind/s4-chatbot-adv/R51.md  [no fences]
  blind/s4-chatbot-adv/R52.md  [no fences]
  blind/s4-chatbot-adv/R53.md  [no fences]
  blind/s4-chatbot-adv/R54.md  [no fences]
  blind/s4-chatbot-adv/R55.md  [no fences]
  blind/s4-chatbot-adv/R56.md  [no fences]
  blind/s4-chatbot-adv/R57.md  [no fences]
  blind/s4-chatbot-adv/R58.md  [no fences]
  blind/s4-chatbot-adv/R59.md  [no fences]
  blind/s4-chatbot-adv/R60.md  [no fences]
  blind/s4-chatbot-adv/R61.md  [no fences]
  blind/s4-chatbot-adv/R62.md  [no fences]
  blind/s4-chatbot-adv/R63.md  [no fences]
  blind/s4-chatbot-adv/R64.md  [no fences]
  blind/s4-chatbot-adv/R65.md  [no fences]
  blind/s4-chatbot-adv/R66.md  [no fences]
  blind/s4-chatbot-adv/R67.md  [no fences]
  blind/s4-chatbot-adv/R68.md  [no fences]
  blind/s4-chatbot-adv/R69.md  [no fences]
  blind/s4-chatbot-adv/R70.md  [no fences]
  blind/s4-chatbot-adv/R71.md  [no fences]
  blind/s4-chatbot-adv/R72.md  [no fences]
  blind/s4-chatbot-adv/R73.md  [no fences]
  blind/s4-chatbot-adv/R74.md  [no fences]
  blind/s4-chatbot-adv/R75.md  [no fences]
  blind/s4-chatbot-adv/R76.md  [no fences]
  blind/s4-chatbot-adv/R77.md  [no fences]
  blind/s4-chatbot-adv/R78.md  [no fences]
  blind/s4-chatbot-adv/R79.md  [no fences]
  blind/s4-chatbot-adv/R80.md  [no fences]
  blind/s4-chatbot-adv/R81.md  [no fences]
  blind/s4-chatbot-adv/R82.md  [no fences]
  blind/s4-chatbot-adv/R83.md  [no fences]
  blind/s4-chatbot-adv/R84.md  [no fences]
  heldout/s3-chatbot-noadv/N02.md  [no fences]
  heldout/s3-chatbot-noadv/N04.md  [no fences]
  heldout/s3-chatbot-noadv/P13.md  [no fences]
  heldout/s3-chatbot-noadv/P16.md  [no fences]
  heldout/s3-chatbot-noadv/P21.md  [no fences]
  heldout/s3-chatbot-noadv/P24.md  [no fences]
  heldout/s3-chatbot-noadv/R07.md  [no fences]
  heldout/s3-chatbot-noadv/R08.md  [no fences]
  heldout/s3-chatbot-noadv/R09.md  [no fences]
  heldout/s3-chatbot-noadv/R10.md  [no fences]
  heldout/s3-chatbot-noadv/R11.md  [no fences]
  heldout/s3-chatbot-noadv/R12.md  [no fences]
  heldout/s3-chatbot-noadv/R13.md  [no fences]
  heldout/s3-chatbot-noadv/R14.md  [no fences]
  heldout/s3-chatbot-noadv/R15.md  [no fences]
  heldout/s3-chatbot-noadv/R16.md  [no fences]
  heldout/s3-chatbot-noadv/R17.md  [no fences]
  heldout/s3-chatbot-noadv/R18.md  [no fences]
  heldout/s3-chatbot-noadv/R19.md  [no fences]
  heldout/s3-chatbot-noadv/R20.md  [no fences]
  heldout/s3-chatbot-noadv/R21.md  [no fences]
  heldout/s3-chatbot-noadv/R22.md  [no fences]
  heldout/s3-chatbot-noadv/R23.md  [no fences]
  heldout/s3-chatbot-noadv/R24.md  [no fences]
  heldout/s3-chatbot-noadv/R25.md  [no fences]
  heldout/s3-chatbot-noadv/R26.md  [no fences]
  heldout/s3-chatbot-noadv/R27.md  [no fences]
  heldout/s3-chatbot-noadv/R28.md  [no fences]
  heldout/s3-chatbot-noadv/R29.md  [no fences]
  heldout/s3-chatbot-noadv/R30.md  [no fences]
  heldout/s3-chatbot-noadv/R31.md  [no fences]
  heldout/s3-chatbot-noadv/R32.md  [no fences]
  heldout/s3-chatbot-noadv/R33.md  [no fences]
  heldout/s3-chatbot-noadv/R34.md  [no fences]
  heldout/s3-chatbot-noadv/R35.md  [no fences]
  heldout/s3-chatbot-noadv/R36.md  [no fences]
  heldout/s3-chatbot-noadv/R37.md  [no fences]
  heldout/s3-chatbot-noadv/R38.md  [no fences]
  heldout/s3-chatbot-noadv/R39.md  [no fences]
  heldout/s3-chatbot-noadv/R40.md  [no fences]
  heldout/s3-chatbot-noadv/R41.md  [no fences]
  heldout/s3-chatbot-noadv/R42.md  [no fences]
  heldout/s4-chatbot-adv/P21.md  [no fences]
  heldout/s4-chatbot-adv/P24.md  [no fences]
  heldout/s4-chatbot-adv/R07.md  [no fences]
  heldout/s4-chatbot-adv/R08.md  [no fences]
  heldout/s4-chatbot-adv/R09.md  [no fences]
  heldout/s4-chatbot-adv/R10.md  [no fences]
  heldout/s4-chatbot-adv/R11.md  [no fences]
  heldout/s4-chatbot-adv/R12.md  [no fences]
  heldout/s4-chatbot-adv/R13.md  [no fences]
  heldout/s4-chatbot-adv/R14.md  [no fences]
  heldout/s4-chatbot-adv/R15.md  [no fences]
  heldout/s4-chatbot-adv/R16.md  [no fences]
  heldout/s4-chatbot-adv/R17.md  [no fences]
  heldout/s4-chatbot-adv/R18.md  [no fences]
  heldout/s4-chatbot-adv/R19.md  [no fences]
  heldout/s4-chatbot-adv/R20.md  [no fences]
  heldout/s4-chatbot-adv/R21.md  [no fences]
  heldout/s4-chatbot-adv/R22.md  [no fences]
  heldout/s4-chatbot-adv/R23.md  [no fences]
  heldout/s4-chatbot-adv/R24.md  [no fences]
  heldout/s4-chatbot-adv/R25.md  [no fences]
  heldout/s4-chatbot-adv/R26.md  [no fences]
  heldout/s4-chatbot-adv/R27.md  [no fences]
  heldout/s4-chatbot-adv/R28.md  [no fences]
  heldout/s4-chatbot-adv/R29.md  [no fences]
  heldout/s4-chatbot-adv/R30.md  [no fences]
  heldout/s4-chatbot-adv/R31.md  [no fences]
  heldout/s4-chatbot-adv/R32.md  [no fences]
  heldout/s4-chatbot-adv/R33.md  [no fences]
  heldout/s4-chatbot-adv/R34.md  [no fences]
  heldout/s4-chatbot-adv/R35.md  [no fences]
  heldout/s4-chatbot-adv/R36.md  [no fences]
  heldout/s4-chatbot-adv/R43.md  [no fences]
  heldout/s4-chatbot-adv/R44.md  [no fences]
  heldout/s4-chatbot-adv/R45.md  [no fences]
  heldout/s4-chatbot-adv/R46.md  [no fences]
  heldout/s4-chatbot-adv/R47.md  [no fences]
  heldout/s4-chatbot-adv/R48.md  [no fences]
  matched/s3-chatbot-noadv/AV03.md  [no fences]
  matched/s3-chatbot-noadv/N15.md  [no fences]
  matched/s3-chatbot-noadv/P13.md  [no fences]
  matched/s3-chatbot-noadv/P24.md  [no fences]
  matched/s3-chatbot-noadv/P25.md  [no fences]
  matched/s3-chatbot-noadv/R07.md  [no fences]
  matched/s3-chatbot-noadv/R08.md  [no fences]
  matched/s3-chatbot-noadv/R09.md  [no fences]
  matched/s3-chatbot-noadv/R10.md  [no fences]
  matched/s3-chatbot-noadv/R11.md  [no fences]
  matched/s3-chatbot-noadv/R12.md  [no fences]
  matched/s3-chatbot-noadv/R13.md  [no fences]
  matched/s3-chatbot-noadv/R14.md  [no fences]
  matched/s3-chatbot-noadv/R15.md  [no fences]
  matched/s3-chatbot-noadv/R16.md  [no fences]
  matched/s3-chatbot-noadv/R17.md  [no fences]
  matched/s3-chatbot-noadv/R18.md  [no fences]
  matched/s3-chatbot-noadv/R19.md  [no fences]
  matched/s3-chatbot-noadv/R20.md  [no fences]
  matched/s3-chatbot-noadv/R21.md  [no fences]
  matched/s3-chatbot-noadv/R22.md  [no fences]
  matched/s3-chatbot-noadv/R23.md  [no fences]
  matched/s3-chatbot-noadv/R24.md  [no fences]
  matched/s3-chatbot-noadv/R25.md  [no fences]
  matched/s3-chatbot-noadv/R26.md  [no fences]
  matched/s3-chatbot-noadv/R27.md  [no fences]
  matched/s3-chatbot-noadv/R28.md  [no fences]
  matched/s3-chatbot-noadv/R29.md  [no fences]
  matched/s3-chatbot-noadv/R30.md  [no fences]
  matched/s3-chatbot-noadv/R31.md  [no fences]
  matched/s3-chatbot-noadv/R32.md  [no fences]
  matched/s3-chatbot-noadv/R33.md  [no fences]
  matched/s3-chatbot-noadv/R34.md  [no fences]
  matched/s3-chatbot-noadv/R35.md  [no fences]
  matched/s3-chatbot-noadv/R36.md  [no fences]
  matched/s3-chatbot-noadv/R37.md  [no fences]
  matched/s3-chatbot-noadv/R38.md  [no fences]
  matched/s3-chatbot-noadv/R39.md  [no fences]
  matched/s3-chatbot-noadv/R40.md  [no fences]
  matched/s3-chatbot-noadv/R41.md  [no fences]
  matched/s3-chatbot-noadv/R42.md  [no fences]
  matched/s3-chatbot-noadv/R43.md  [no fences]
  matched/s3-chatbot-noadv/R44.md  [no fences]
  matched/s3-chatbot-noadv/R45.md  [no fences]
  matched/s3-chatbot-noadv/R46.md  [no fences]
  matched/s3-chatbot-noadv/R47.md  [no fences]
  matched/s3-chatbot-noadv/R48.md  [no fences]
  matched/s4-chatbot-adv/AV03.md  [no fences]
  matched/s4-chatbot-adv/P13.md  [no fences]
  matched/s4-chatbot-adv/P24.md  [no fences]
  matched/s4-chatbot-adv/P25.md  [no fences]
  matched/s4-chatbot-adv/R01.md  [no fences]
  matched/s4-chatbot-adv/R02.md  [no fences]
  matched/s4-chatbot-adv/R03.md  [no fences]
  matched/s4-chatbot-adv/R04.md  [no fences]
  matched/s4-chatbot-adv/R05.md  [no fences]
  matched/s4-chatbot-adv/R06.md  [no fences]
  matched/s4-chatbot-adv/R19.md  [no fences]
  matched/s4-chatbot-adv/R20.md  [no fences]
  matched/s4-chatbot-adv/R21.md  [no fences]
  matched/s4-chatbot-adv/R22.md  [no fences]
  matched/s4-chatbot-adv/R23.md  [no fences]
  matched/s4-chatbot-adv/R24.md  [no fences]
  matched/s4-chatbot-adv/R25.md  [no fences]
  matched/s4-chatbot-adv/R26.md  [no fences]
  matched/s4-chatbot-adv/R27.md  [no fences]
  matched/s4-chatbot-adv/R28.md  [no fences]
  matched/s4-chatbot-adv/R29.md  [no fences]
  matched/s4-chatbot-adv/R30.md  [no fences]
  matched/s4-chatbot-adv/R31.md  [no fences]
  matched/s4-chatbot-adv/R32.md  [no fences]
  matched/s4-chatbot-adv/R33.md  [no fences]
  matched/s4-chatbot-adv/R34.md  [no fences]
  matched/s4-chatbot-adv/R35.md  [no fences]
  matched/s4-chatbot-adv/R36.md  [no fences]
  matched/s4-chatbot-adv/R37.md  [no fences]
  matched/s4-chatbot-adv/R38.md  [no fences]
  matched/s4-chatbot-adv/R39.md  [no fences]
  matched/s4-chatbot-adv/R40.md  [no fences]
  matched/s4-chatbot-adv/R41.md  [no fences]
  matched/s4-chatbot-adv/R42.md  [no fences]
  matched/s4-chatbot-adv/R43.md  [no fences]
  matched/s4-chatbot-adv/R44.md  [no fences]
  matched/s4-chatbot-adv/R45.md  [no fences]
  matched/s4-chatbot-adv/R46.md  [no fences]
  matched/s4-chatbot-adv/R47.md  [no fences]
  matched/s4-chatbot-adv/R48.md  [no fences]
  uncovered/s3-chatbot-noadv/N17.md  [no fences]
  uncovered/s3-chatbot-noadv/R49.md  [no fences]
  uncovered/s3-chatbot-noadv/R50.md  [no fences]
  uncovered/s3-chatbot-noadv/R51.md  [no fences]
  uncovered/s3-chatbot-noadv/R52.md  [no fences]
  uncovered/s3-chatbot-noadv/R53.md  [no fences]
  uncovered/s3-chatbot-noadv/R54.md  [no fences]
  uncovered/s3-chatbot-noadv/R55.md  [no fences]
  uncovered/s3-chatbot-noadv/R56.md  [no fences]
  uncovered/s3-chatbot-noadv/R57.md  [no fences]
  uncovered/s3-chatbot-noadv/R58.md  [no fences]
  uncovered/s3-chatbot-noadv/R59.md  [no fences]
  uncovered/s3-chatbot-noadv/R60.md  [no fences]
  uncovered/s3-chatbot-noadv/R61.md  [no fences]
  uncovered/s3-chatbot-noadv/R62.md  [no fences]
  uncovered/s3-chatbot-noadv/R63.md  [no fences]
  uncovered/s3-chatbot-noadv/R64.md  [no fences]
  uncovered/s3-chatbot-noadv/R65.md  [no fences]
  uncovered/s3-chatbot-noadv/R66.md  [no fences]
  uncovered/s3-chatbot-noadv/R67.md  [no fences]
  uncovered/s3-chatbot-noadv/R68.md  [no fences]
  uncovered/s3-chatbot-noadv/R69.md  [no fences]
  uncovered/s3-chatbot-noadv/R70.md  [no fences]
  uncovered/s3-chatbot-noadv/R71.md  [no fences]
  uncovered/s3-chatbot-noadv/R72.md  [no fences]
  uncovered/s3-chatbot-noadv/R73.md  [no fences]
  uncovered/s3-chatbot-noadv/R74.md  [no fences]
  uncovered/s3-chatbot-noadv/R75.md  [no fences]
  uncovered/s3-chatbot-noadv/R76.md  [no fences]
  uncovered/s3-chatbot-noadv/R77.md  [no fences]
  uncovered/s3-chatbot-noadv/R78.md  [no fences]
  uncovered/s3-chatbot-noadv/R79.md  [no fences]
  uncovered/s3-chatbot-noadv/R80.md  [no fences]
  uncovered/s3-chatbot-noadv/R81.md  [no fences]
  uncovered/s3-chatbot-noadv/R82.md  [no fences]
  uncovered/s3-chatbot-noadv/R83.md  [no fences]
  uncovered/s3-chatbot-noadv/R84.md  [no fences]
  uncovered/s4-chatbot-adv/R49.md  [no fences]
  uncovered/s4-chatbot-adv/R50.md  [no fences]
  uncovered/s4-chatbot-adv/R51.md  [no fences]
  uncovered/s4-chatbot-adv/R52.md  [no fences]
  uncovered/s4-chatbot-adv/R53.md  [no fences]
  uncovered/s4-chatbot-adv/R54.md  [no fences]
  uncovered/s4-chatbot-adv/R55.md  [no fences]
  uncovered/s4-chatbot-adv/R56.md  [no fences]
  uncovered/s4-chatbot-adv/R57.md  [no fences]
  uncovered/s4-chatbot-adv/R58.md  [no fences]
  uncovered/s4-chatbot-adv/R59.md  [no fences]
  uncovered/s4-chatbot-adv/R60.md  [no fences]
  uncovered/s4-chatbot-adv/R61.md  [no fences]
  uncovered/s4-chatbot-adv/R62.md  [no fences]
  uncovered/s4-chatbot-adv/R63.md  [no fences]
  uncovered/s4-chatbot-adv/R64.md  [no fences]
  uncovered/s4-chatbot-adv/R65.md  [no fences]
  uncovered/s4-chatbot-adv/R66.md  [no fences]
  uncovered/s4-chatbot-adv/R67.md  [no fences]
  uncovered/s4-chatbot-adv/R68.md  [no fences]
  uncovered/s4-chatbot-adv/R69.md  [no fences]
  uncovered/s4-chatbot-adv/R70.md  [no fences]
  uncovered/s4-chatbot-adv/R71.md  [no fences]
  uncovered/s4-chatbot-adv/R72.md  [no fences]
  uncovered/s4-chatbot-adv/R73.md  [no fences]
  uncovered/s4-chatbot-adv/R74.md  [no fences]
  uncovered/s4-chatbot-adv/R75.md  [no fences]
  uncovered/s4-chatbot-adv/R76.md  [no fences]
  uncovered/s4-chatbot-adv/R77.md  [no fences]
  uncovered/s4-chatbot-adv/R78.md  [no fences]

## Item x system verdicts (P pass, f fail, . empty, blank no file)

### blind

item     s3   s4
----------------
AV01      f    f
AV02      f    f
AV03      f    f
AV04      f    f
N01       f    f
N02       f    f
N03       f    f
N04       f    f
N05       f    f
N06       f    f
N07       f    f
N08       f    f
N09       f    f
N10       f    f
N11       f    f
N12       f    f
N13       f    f
N14       P    f
N15       f    f
N16       f    f
N17       f    f
N18       P    f
P01       f    f
P02       f    f
P03       f    f
P04       f    f
P05       f    f
P06       f    f
P07       f    f
P08       f    f
P09       f    f
P10       f    f
P11       f    f
P12       f    f
P13       f    P
P14       f    f
P15       f    f
P16       f    f
P17       f    f
P18       f    f
P19       f    f
P20       f    f
P21       f    f
P22       f    f
P23       f    f
P24       f    P
P25       f    f
P26       f    f
P27       P    P
P28       f    f
R01       f    f
R02       f    P
R03       f    f
R04       f    f
R05       f    P
R06       f    f
R07       f    f
R08       f    f
R09       f    f
R10       f    f
R11       f    f
R12       f    f
R13       f    f
R14       f    f
R15       P    f
R16       f    f
R17       f    f
R18       f    f
R19       f    f
R20       f    f
R21       f    f
R22       f    f
R23       f    f
R24       f    f
R25       f    f
R26       f    f
R27       f    f
R28       f    f
R29       f    f
R30       f    f
R31       f    P
R32       f    P
R33       f    f
R34       f    P
R35       f    P
R36       f    P
R37       f    f
R38       f    f
R39       f    f
R40       f    f
R41       f    f
R42       f    f
R43       f    f
R44       f    f
R45       f    f
R46       f    f
R47       f    f
R48       f    f
R49       f    f
R50       f    f
R51       f    f
R52       f    P
R53       f    f
R54       f    f
R55       f    P
R56       f    f
R57       f    f
R58       f    f
R59       f    f
R60       f    f
R61       f    f
R62       f    f
R63       f    f
R64       f    f
R65       f    f
R66       f    f
R67       f    f
R68       f    f
R69       f    f
R70       P    P
R71       f    f
R72       f    f
R73       f    f
R74       f    f
R75       f    f
R76       P    f
R77       f    f
R78       f    f
R79       f    f
R80       f    f
R81       f    f
R82       P    f
R83       f    f
R84       f    f

### matched

item     s3   s4
----------------
AV01      P    P
AV02      P    f
AV03      f    f
AV04      f    f
N01       f    f
N02       P    P
N03       P    P
N04       f    f
N05       f    P
N06       f    f
N07       f    f
N08       f    f
N09       f    f
N10       f    f
N11       f    f
N12       f    P
N13       f    f
N15       f    f
N16       f    P
P01       P    f
P02       P    P
P03       f    f
P04       P    f
P05       P    f
P06       P    f
P07       f    P
P08       P    P
P09       f    f
P10       f    f
P11       f    f
P12       P    P
P13       P    P
P14       f    f
P15       f    f
P16       f    f
P17       P    P
P18       f    P
P19       f    f
P20       f    f
P21       f    f
P22       P    P
P23       P    f
P24       P    P
P25       f    f
P26       f    f
P27       f    f
P28       P    P
R01       P    P
R02       P    P
R03       f    f
R04       P    f
R05       P    P
R06       P    P
R07       f    P
R08       f    P
R09       f    f
R10       f    P
R11       f    P
R12       f    P
R13       f    P
R14       f    P
R15       f    f
R16       f    P
R17       f    P
R18       f    P
R19       f    f
R20       f    P
R21       f    f
R22       f    f
R23       f    P
R24       f    f
R25       f    P
R26       f    P
R27       f    f
R28       f    P
R29       f    P
R30       f    P
R31       f    f
R32       f    P
R33       f    f
R34       f    f
R35       f    P
R36       f    f
R37       f    P
R38       f    P
R39       f    f
R40       f    P
R41       f    P
R42       f    P
R43       f    P
R44       f    f
R45       f    f
R46       f    f
R47       f    f
R48       f    P

### heldout

item     s3   s4
----------------
N02       f    f
N04       f    f
N05       f    f
N08       f    f
N13       f    f
N15       P    f
N16       f    f
P11       f    f
P13       f    f
P16       f    f
P17       f    f
P21       f    f
P22       f    f
P24       f    f
R01       f    f
R02       P    P
R03       f    f
R04       f    f
R05       P    P
R06       f    f
R07       f    f
R08       f    f
R09       f    f
R10       f    f
R11       f    f
R12       f    f
R13       f    f
R14       f    f
R15       f    f
R16       f    f
R17       f    f
R18       f    f
R19       f    f
R20       P    f
R21       f    f
R22       f    f
R23       P    f
R24       f    f
R25       f    f
R26       f    f
R27       f    f
R28       f    f
R29       f    f
R30       f    f
R31       f    f
R32       f    P
R33       f    f
R34       f    f
R35       f    P
R36       f    f
R37       P    P
R38       P    P
R39       f    f
R40       P    P
R41       P    P
R42       P    P
R43       f    f
R44       f    f
R45       f    f
R46       f    f
R47       f    f
R48       f    f

### uncovered

item     s3   s4
----------------
N14       P    f
N17       P    f
N18       f    f
R49       f    f
R50       f    f
R51       f    f
R52       f    f
R53       f    f
R54       f    f
R55       f    f
R56       f    f
R57       f    f
R58       f    f
R59       f    f
R60       f    f
R61       f    f
R62       f    f
R63       f    f
R64       f    f
R65       f    f
R66       f    f
R67       f    f
R68       f    f
R69       f    f
R70       P    f
R71       f    f
R72       f    f
R73       f    f
R74       f    f
R75       f    f
R76       f    f
R77       f    f
R78       f    f
R79       f    f
R80       f    f
R81       f    f
R82       f    f
R83       f    f
R84       f    f

