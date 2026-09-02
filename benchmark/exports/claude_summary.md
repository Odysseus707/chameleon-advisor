# Run scores summary

## Fill status (non-empty / total answer files)

condition   s5-claude-sonnet
----------------------------
blind                134/134

## Overall PASS rate (all checkers green; scored answers only)

condition   s5-claude-sonnet
----------------------------
blind           18/134 (13%)

## Rates on COMMON items only (selection-bias guard)

  (fewer than two systems share scored items anywhere)

## Checker-group pass rates (checks passed / checks run)

### mechanism

condition   s5-claude-sonnet
----------------------------
blind           47/115 (41%)

### specifics

condition   s5-claude-sonnet
----------------------------
blind           45/119 (38%)

### safety

condition   s5-claude-sonnet
----------------------------
blind          188/199 (94%)

### feasibility

condition   s5-claude-sonnet
----------------------------
blind          171/228 (75%)

### capability

condition   s5-claude-sonnet
----------------------------
blind          175/358 (49%)

## State-sensitivity (does the pick track the environment?)

system           tracked/moved
------------------------------
s5-claude-sonnet     14/118 (12%)

## Fence lint (scored answers where the extractor sees NO code)

  These score near-zero mechanically. If the answer visibly contains
  code, the fences were stripped on paste — re-paste or --wrap-code.
  (Prose-only answers to abstention items are fine here.)

  blind/s5-claude-sonnet/R01.md  [no fences]
  blind/s5-claude-sonnet/R02.md  [no fences]
  blind/s5-claude-sonnet/R03.md  [no fences]
  blind/s5-claude-sonnet/R04.md  [no fences]
  blind/s5-claude-sonnet/R05.md  [no fences]
  blind/s5-claude-sonnet/R06.md  [no fences]
  blind/s5-claude-sonnet/R07.md  [no fences]
  blind/s5-claude-sonnet/R08.md  [no fences]
  blind/s5-claude-sonnet/R09.md  [no fences]
  blind/s5-claude-sonnet/R10.md  [no fences]
  blind/s5-claude-sonnet/R21.md  [no fences]
  blind/s5-claude-sonnet/R22.md  [no fences]
  blind/s5-claude-sonnet/R23.md  [no fences]
  blind/s5-claude-sonnet/R24.md  [no fences]
  blind/s5-claude-sonnet/R25.md  [no fences]
  blind/s5-claude-sonnet/R26.md  [no fences]
  blind/s5-claude-sonnet/R27.md  [no fences]
  blind/s5-claude-sonnet/R28.md  [no fences]
  blind/s5-claude-sonnet/R29.md  [no fences]
  blind/s5-claude-sonnet/R30.md  [no fences]
  blind/s5-claude-sonnet/R31.md  [no fences]
  blind/s5-claude-sonnet/R32.md  [no fences]
  blind/s5-claude-sonnet/R33.md  [no fences]
  blind/s5-claude-sonnet/R34.md  [no fences]
  blind/s5-claude-sonnet/R35.md  [no fences]
  blind/s5-claude-sonnet/R36.md  [no fences]
  blind/s5-claude-sonnet/R37.md  [no fences]
  blind/s5-claude-sonnet/R38.md  [no fences]
  blind/s5-claude-sonnet/R39.md  [no fences]
  blind/s5-claude-sonnet/R40.md  [no fences]
  blind/s5-claude-sonnet/R41.md  [no fences]
  blind/s5-claude-sonnet/R42.md  [no fences]
  blind/s5-claude-sonnet/R43.md  [no fences]
  blind/s5-claude-sonnet/R44.md  [no fences]
  blind/s5-claude-sonnet/R45.md  [no fences]
  blind/s5-claude-sonnet/R46.md  [no fences]
  blind/s5-claude-sonnet/R47.md  [no fences]
  blind/s5-claude-sonnet/R48.md  [no fences]
  blind/s5-claude-sonnet/R49.md  [no fences]
  blind/s5-claude-sonnet/R50.md  [no fences]
  blind/s5-claude-sonnet/R61.md  [no fences]
  blind/s5-claude-sonnet/R62.md  [no fences]
  blind/s5-claude-sonnet/R63.md  [no fences]
  blind/s5-claude-sonnet/R64.md  [no fences]
  blind/s5-claude-sonnet/R65.md  [no fences]
  blind/s5-claude-sonnet/R66.md  [no fences]
  blind/s5-claude-sonnet/R67.md  [no fences]
  blind/s5-claude-sonnet/R68.md  [no fences]
  blind/s5-claude-sonnet/R69.md  [no fences]
  blind/s5-claude-sonnet/R70.md  [no fences]
  blind/s5-claude-sonnet/R71.md  [no fences]
  blind/s5-claude-sonnet/R72.md  [no fences]
  blind/s5-claude-sonnet/R73.md  [no fences]
  blind/s5-claude-sonnet/R74.md  [no fences]
  blind/s5-claude-sonnet/R75.md  [no fences]
  blind/s5-claude-sonnet/R76.md  [no fences]
  blind/s5-claude-sonnet/R77.md  [no fences]
  blind/s5-claude-sonnet/R78.md  [no fences]
  blind/s5-claude-sonnet/R79.md  [no fences]
  blind/s5-claude-sonnet/R80.md  [no fences]
  blind/s5-claude-sonnet/R81.md  [no fences]
  blind/s5-claude-sonnet/R82.md  [no fences]
  blind/s5-claude-sonnet/R83.md  [no fences]
  blind/s5-claude-sonnet/R84.md  [no fences]

## Item x system verdicts (P pass, f fail, . empty, blank no file)

### blind

item     s5
-----------
AV01      f
AV02      f
AV03      f
AV04      f
N01       f
N02       f
N03       f
N04       f
N05       f
N06       P
N07       f
N08       f
N09       f
N10       f
N11       f
N12       f
N13       f
N14       P
N15       f
N16       f
N17       f
N18       f
P01       P
P02       P
P03       f
P04       P
P05       f
P06       f
P07       P
P08       P
P09       f
P10       P
P11       f
P12       f
P13       f
P14       f
P15       f
P16       f
P17       f
P18       f
P19       f
P20       f
P21       f
P22       f
P23       f
P24       f
P25       f
P26       f
P27       f
P28       f
R01       f
R02       P
R03       f
R04       f
R05       P
R06       f
R07       f
R08       f
R09       f
R10       f
R11       f
R12       f
R13       f
R14       f
R15       f
R16       f
R17       f
R18       f
R19       f
R20       f
R21       f
R22       f
R23       f
R24       f
R25       f
R26       f
R27       f
R28       f
R29       f
R30       f
R31       f
R32       f
R33       f
R34       f
R35       P
R36       f
R37       P
R38       P
R39       f
R40       f
R41       f
R42       f
R43       f
R44       f
R45       f
R46       f
R47       f
R48       f
R49       f
R50       f
R51       f
R52       f
R53       f
R54       f
R55       f
R56       f
R57       f
R58       f
R59       f
R60       f
R61       f
R62       f
R63       f
R64       f
R65       P
R66       P
R67       P
R68       P
R69       P
R70       f
R71       f
R72       f
R73       f
R74       f
R75       f
R76       f
R77       f
R78       f
R79       f
R80       f
R81       f
R82       f
R83       f
R84       f

