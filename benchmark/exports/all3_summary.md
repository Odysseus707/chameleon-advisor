# Run scores summary

## Fill status (non-empty / total answer files)

condition s3-chatbot-noadvs4-chatbot-advs5-claude-sonnet
--------------------------------------------------------
blind            134/134       134/134       134/134

## Overall PASS rate (all checkers green; scored answers only)

condition s3-chatbot-noadvs4-chatbot-advs5-claude-sonnet
--------------------------------------------------------
blind         7/134 (5%)  13/134 (10%)  18/134 (13%)

## Rates on COMMON items only (selection-bias guard)

### blind — 134 items answered by all of: s3-chatbot-noadv, s4-chatbot-adv, s5-claude-sonnet

metric    s3-chatbot-noadvs4-chatbot-advs5-claude-sonnet
--------------------------------------------------------
PASS          7/134 (5%)  13/134 (10%)  18/134 (13%)
mechanism     9/115 (8%)    8/115 (7%)  47/115 (41%)
specifics   16/119 (13%)  27/119 (23%)  45/119 (38%)
safety     182/199 (91%) 181/199 (91%) 188/199 (94%)
feasibility  84/228 (37%) 151/228 (66%) 171/228 (75%)
capability 173/358 (48%) 175/358 (49%) 175/358 (49%)

## Checker-group pass rates (checks passed / checks run)

### mechanism

condition s3-chatbot-noadvs4-chatbot-advs5-claude-sonnet
--------------------------------------------------------
blind         9/115 (8%)    8/115 (7%)  47/115 (41%)

### specifics

condition s3-chatbot-noadvs4-chatbot-advs5-claude-sonnet
--------------------------------------------------------
blind       16/119 (13%)  27/119 (23%)  45/119 (38%)

### safety

condition s3-chatbot-noadvs4-chatbot-advs5-claude-sonnet
--------------------------------------------------------
blind      182/199 (91%) 181/199 (91%) 188/199 (94%)

### feasibility

condition s3-chatbot-noadvs4-chatbot-advs5-claude-sonnet
--------------------------------------------------------
blind       84/228 (37%) 151/228 (66%) 171/228 (75%)

### capability

condition s3-chatbot-noadvs4-chatbot-advs5-claude-sonnet
--------------------------------------------------------
blind      173/358 (48%) 175/358 (49%) 175/358 (49%)

## State-sensitivity (does the pick track the environment?)

system           tracked/moved
------------------------------
s4-chatbot-adv        0/90 (0%)
s5-claude-sonnet     14/118 (12%)

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

item     s3   s4   s5
---------------------
AV01      f    f    f
AV02      f    f    f
AV03      f    f    f
AV04      f    f    f
N01       f    f    f
N02       f    f    f
N03       f    f    f
N04       f    f    f
N05       f    f    f
N06       f    f    P
N07       f    f    f
N08       f    f    f
N09       f    f    f
N10       f    f    f
N11       f    f    f
N12       f    f    f
N13       f    f    f
N14       P    f    P
N15       f    f    f
N16       f    f    f
N17       f    f    f
N18       P    f    f
P01       f    f    P
P02       f    f    P
P03       f    f    f
P04       f    f    P
P05       f    f    f
P06       f    f    f
P07       f    f    P
P08       f    f    P
P09       f    f    f
P10       f    f    P
P11       f    f    f
P12       f    f    f
P13       f    P    f
P14       f    f    f
P15       f    f    f
P16       f    f    f
P17       f    f    f
P18       f    f    f
P19       f    f    f
P20       f    f    f
P21       f    f    f
P22       f    f    f
P23       f    f    f
P24       f    P    f
P25       f    f    f
P26       f    f    f
P27       P    P    f
P28       f    f    f
R01       f    f    f
R02       f    P    P
R03       f    f    f
R04       f    f    f
R05       f    P    P
R06       f    f    f
R07       f    f    f
R08       f    f    f
R09       f    f    f
R10       f    f    f
R11       f    f    f
R12       f    f    f
R13       f    f    f
R14       f    f    f
R15       P    f    f
R16       f    f    f
R17       f    f    f
R18       f    f    f
R19       f    f    f
R20       f    f    f
R21       f    f    f
R22       f    f    f
R23       f    f    f
R24       f    f    f
R25       f    f    f
R26       f    f    f
R27       f    f    f
R28       f    f    f
R29       f    f    f
R30       f    f    f
R31       f    P    f
R32       f    P    f
R33       f    f    f
R34       f    P    f
R35       f    P    P
R36       f    P    f
R37       f    f    P
R38       f    f    P
R39       f    f    f
R40       f    f    f
R41       f    f    f
R42       f    f    f
R43       f    f    f
R44       f    f    f
R45       f    f    f
R46       f    f    f
R47       f    f    f
R48       f    f    f
R49       f    f    f
R50       f    f    f
R51       f    f    f
R52       f    P    f
R53       f    f    f
R54       f    f    f
R55       f    P    f
R56       f    f    f
R57       f    f    f
R58       f    f    f
R59       f    f    f
R60       f    f    f
R61       f    f    f
R62       f    f    f
R63       f    f    f
R64       f    f    f
R65       f    f    P
R66       f    f    P
R67       f    f    P
R68       f    f    P
R69       f    f    P
R70       P    P    f
R71       f    f    f
R72       f    f    f
R73       f    f    f
R74       f    f    f
R75       f    f    f
R76       P    f    f
R77       f    f    f
R78       f    f    f
R79       f    f    f
R80       f    f    f
R81       f    f    f
R82       P    f    f
R83       f    f    f
R84       f    f    f

