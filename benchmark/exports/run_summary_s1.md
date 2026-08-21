# Run scores summary

## Fill status (non-empty / total answer files)

condition     s1-chatbot
------------------------
blind              50/50
matched            47/47
heldout            14/14
uncovered            3/3

## Overall PASS rate (all checkers green; scored answers only)

condition     s1-chatbot
------------------------
blind          2/50 (4%)
matched        2/47 (4%)
heldout        0/14 (0%)
uncovered       0/3 (0%)

## Rates on COMMON items only (selection-bias guard)

  (fewer than two systems share scored items anywhere)

## Checker-group pass rates (checks passed / checks run)

### mechanism

condition     s1-chatbot
------------------------
blind         2/115 (2%)
matched       0/112 (0%)
heldout        0/35 (0%)
uncovered       0/3 (0%)

### specifics

condition     s1-chatbot
------------------------
blind         3/119 (3%)
matched       7/119 (6%)
heldout        2/41 (5%)
uncovered              —

### safety

condition     s1-chatbot
------------------------
blind        29/43 (67%)
matched      24/38 (63%)
heldout       7/15 (47%)
uncovered     5/5 (100%)

## Uncovered items (abstain-or-discover)

  N14   s1-chatbot     FAIL [abstain_or_discover]
  N17   s1-chatbot     FAIL [abstain_or_discover]
  N18   s1-chatbot     FAIL [abstain_or_discover]

## Fence lint (scored answers where the extractor sees NO code)

  These score near-zero mechanically. If the answer visibly contains
  code, the fences were stripped on paste — re-paste or --wrap-code.
  (Prose-only answers to abstention items are fine here.)

  blind/s1-chatbot/AV01.md  [no fences]
  blind/s1-chatbot/AV02.md  [no fences]
  blind/s1-chatbot/AV03.md  [no fences]
  blind/s1-chatbot/AV04.md  [no fences]
  blind/s1-chatbot/N01.md  [no fences]
  blind/s1-chatbot/N02.md  [no fences]
  blind/s1-chatbot/N03.md  [no fences]
  blind/s1-chatbot/N04.md  [no fences]
  blind/s1-chatbot/N05.md  [no fences]
  blind/s1-chatbot/N06.md  [no fences]
  blind/s1-chatbot/N07.md  [no fences]
  blind/s1-chatbot/N08.md  [no fences]
  blind/s1-chatbot/N09.md  [no fences]
  blind/s1-chatbot/N10.md  [no fences]
  blind/s1-chatbot/N11.md  [no fences]
  blind/s1-chatbot/N12.md  [no fences]
  blind/s1-chatbot/N13.md  [no fences]
  blind/s1-chatbot/N14.md  [no fences]
  blind/s1-chatbot/N15.md  [no fences]
  blind/s1-chatbot/N16.md  [no fences]
  blind/s1-chatbot/N17.md  [no fences]
  blind/s1-chatbot/N18.md  [no fences]
  blind/s1-chatbot/P01.md  [no fences]
  blind/s1-chatbot/P02.md  [no fences]
  blind/s1-chatbot/P03.md  [no fences]
  blind/s1-chatbot/P04.md  [no fences]
  blind/s1-chatbot/P05.md  [no fences]
  blind/s1-chatbot/P06.md  [no fences]
  blind/s1-chatbot/P07.md  [no fences]
  blind/s1-chatbot/P08.md  [no fences]
  blind/s1-chatbot/P09.md  [no fences]
  blind/s1-chatbot/P10.md  [no fences]
  blind/s1-chatbot/P11.md  [no fences]
  blind/s1-chatbot/P12.md  [no fences]
  blind/s1-chatbot/P13.md  [no fences]
  blind/s1-chatbot/P14.md  [no fences]
  blind/s1-chatbot/P15.md  [no fences]
  blind/s1-chatbot/P16.md  [no fences]
  blind/s1-chatbot/P17.md  [no fences]
  blind/s1-chatbot/P18.md  [no fences]
  blind/s1-chatbot/P19.md  [no fences]
  blind/s1-chatbot/P20.md  [no fences]
  blind/s1-chatbot/P21.md  [no fences]
  blind/s1-chatbot/P22.md  [no fences]
  blind/s1-chatbot/P23.md  [no fences]
  blind/s1-chatbot/P24.md  [no fences]
  blind/s1-chatbot/P25.md  [no fences]
  blind/s1-chatbot/P26.md  [no fences]
  blind/s1-chatbot/P27.md  [no fences]
  blind/s1-chatbot/P28.md  [no fences]
  heldout/s1-chatbot/N02.md  [no fences]
  heldout/s1-chatbot/N04.md  [no fences]
  heldout/s1-chatbot/N05.md  [no fences]
  heldout/s1-chatbot/N08.md  [no fences]
  heldout/s1-chatbot/N13.md  [no fences]
  heldout/s1-chatbot/N15.md  [no fences]
  heldout/s1-chatbot/N16.md  [no fences]
  heldout/s1-chatbot/P11.md  [no fences]
  heldout/s1-chatbot/P13.md  [no fences]
  heldout/s1-chatbot/P16.md  [no fences]
  heldout/s1-chatbot/P17.md  [no fences]
  heldout/s1-chatbot/P21.md  [no fences]
  heldout/s1-chatbot/P22.md  [no fences]
  heldout/s1-chatbot/P24.md  [no fences]
  matched/s1-chatbot/AV01.md  [no fences]
  matched/s1-chatbot/AV02.md  [no fences]
  matched/s1-chatbot/AV03.md  [no fences]
  matched/s1-chatbot/AV04.md  [no fences]
  matched/s1-chatbot/N02.md  [no fences]
  matched/s1-chatbot/N04.md  [no fences]
  matched/s1-chatbot/N05.md  [no fences]
  matched/s1-chatbot/N06.md  [no fences]
  matched/s1-chatbot/N09.md  [no fences]
  matched/s1-chatbot/N10.md  [no fences]
  matched/s1-chatbot/N11.md  [no fences]
  matched/s1-chatbot/N12.md  [no fences]
  matched/s1-chatbot/N13.md  [no fences]
  matched/s1-chatbot/N15.md  [no fences]
  matched/s1-chatbot/P01.md  [no fences]
  matched/s1-chatbot/P02.md  [no fences]
  matched/s1-chatbot/P03.md  [no fences]
  matched/s1-chatbot/P04.md  [no fences]
  matched/s1-chatbot/P05.md  [no fences]
  matched/s1-chatbot/P06.md  [no fences]
  matched/s1-chatbot/P07.md  [fenced but unparseable]
  matched/s1-chatbot/P08.md  [no fences]
  matched/s1-chatbot/P09.md  [no fences]
  matched/s1-chatbot/P10.md  [no fences]
  matched/s1-chatbot/P11.md  [no fences]
  matched/s1-chatbot/P12.md  [no fences]
  matched/s1-chatbot/P13.md  [no fences]
  matched/s1-chatbot/P14.md  [no fences]
  matched/s1-chatbot/P15.md  [no fences]
  matched/s1-chatbot/P16.md  [no fences]
  matched/s1-chatbot/P17.md  [no fences]
  matched/s1-chatbot/P18.md  [no fences]
  matched/s1-chatbot/P19.md  [no fences]
  matched/s1-chatbot/P20.md  [no fences]
  matched/s1-chatbot/P21.md  [no fences]
  matched/s1-chatbot/P22.md  [no fences]
  matched/s1-chatbot/P23.md  [no fences]
  matched/s1-chatbot/P24.md  [no fences]
  matched/s1-chatbot/P25.md  [no fences]
  matched/s1-chatbot/P26.md  [no fences]
  matched/s1-chatbot/P27.md  [no fences]
  matched/s1-chatbot/P28.md  [no fences]
  uncovered/s1-chatbot/N14.md  [no fences]
  uncovered/s1-chatbot/N17.md  [no fences]
  uncovered/s1-chatbot/N18.md  [no fences]

## Item x system verdicts (P pass, f fail, . empty, blank no file)

### blind

item     s1
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
N06       f
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
N18       P
P01       f
P02       f
P03       f
P04       f
P05       f
P06       f
P07       f
P08       f
P09       f
P10       f
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

### matched

item     s1
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
N06       f
N07       f
N08       f
N09       f
N10       f
N11       f
N12       f
N13       f
N15       f
N16       f
P01       f
P02       f
P03       f
P04       f
P05       f
P06       f
P07       f
P08       f
P09       f
P10       f
P11       f
P12       f
P13       P
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
P24       P
P25       f
P26       f
P27       f
P28       f

### heldout

item     s1
-----------
N02       f
N04       f
N05       f
N08       f
N13       f
N15       f
N16       f
P11       f
P13       f
P16       f
P17       f
P21       f
P22       f
P24       f

### uncovered

item     s1
-----------
N14       f
N17       f
N18       f

