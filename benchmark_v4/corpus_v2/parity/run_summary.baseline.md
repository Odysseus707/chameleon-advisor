# Run scores summary

## Fill status (non-empty / total answer files)

condition     s1-chatbot        s2-gpt     s3-sonnet    s4-fork-on   s5-fork-off       s6-opus
----------------------------------------------------------------------------------------------
blind              50/50          0/50         28/50         50/50         50/50          0/50
matched            47/47          0/47          0/47             —             —          0/47
heldout            14/14          0/14          0/14             —             —          0/14
uncovered            3/3           0/3           0/3             —             —           0/3

## Overall PASS rate (all checkers green; scored answers only)

condition     s1-chatbot        s2-gpt     s3-sonnet    s4-fork-on   s5-fork-off       s6-opus
----------------------------------------------------------------------------------------------
blind          2/50 (4%)             —     1/28 (4%)     2/50 (4%)     2/50 (4%)             —
matched        2/47 (4%)             —             —             —             —             —
heldout        0/14 (0%)             —             —             —             —             —
uncovered       0/3 (0%)             —             —             —             —             —

## Rates on COMMON items only (selection-bias guard)

### blind — 28 items answered by all of: s1-chatbot, s3-sonnet, s4-fork-on, s5-fork-off

metric        s1-chatbot     s3-sonnet    s4-fork-on   s5-fork-off
------------------------------------------------------------------
PASS           2/28 (7%)     1/28 (4%)     0/28 (0%)     2/28 (7%)
mechanism      2/75 (3%)     1/75 (1%)    9/75 (12%)    8/75 (11%)
specifics      2/78 (3%)     2/78 (3%)    9/78 (12%)    9/78 (12%)
safety       23/33 (70%)   23/33 (70%)   20/33 (61%)   21/33 (64%)

## Checker-group pass rates (checks passed / checks run)

### mechanism

condition     s1-chatbot        s2-gpt     s3-sonnet    s4-fork-on   s5-fork-off       s6-opus
----------------------------------------------------------------------------------------------
blind         2/115 (2%)             —     1/75 (1%)    9/115 (8%)    8/115 (7%)             —
matched       0/112 (0%)             —             —             —             —             —
heldout        0/35 (0%)             —             —             —             —             —
uncovered       0/3 (0%)             —             —             —             —             —

### specifics

condition     s1-chatbot        s2-gpt     s3-sonnet    s4-fork-on   s5-fork-off       s6-opus
----------------------------------------------------------------------------------------------
blind         3/119 (3%)             —     2/78 (3%)  22/119 (18%)  15/119 (13%)             —
matched       7/119 (6%)             —             —             —             —             —
heldout        2/41 (5%)             —             —             —             —             —
uncovered              —             —             —             —             —             —

### safety

condition     s1-chatbot        s2-gpt     s3-sonnet    s4-fork-on   s5-fork-off       s6-opus
----------------------------------------------------------------------------------------------
blind        29/43 (67%)             —   23/33 (70%)   25/43 (58%)   26/43 (60%)             —
matched      24/38 (63%)             —             —             —             —             —
heldout       7/15 (47%)             —             —             —             —             —
uncovered     5/5 (100%)             —             —             —             —             —

## Advisor ablation (blind): s4-fork-on vs s5-fork-off

items compared: 50 | s4 PASS 2 | s5 PASS 2 | delta +0

  mechanism  s4     9/115 (8%)   s5     8/115 (7%)
  specifics  s4   22/119 (18%)   s5   15/119 (13%)
  safety     s4    25/43 (58%)   s5    26/43 (60%)

  advisor fixes (s4 PASS, s5 FAIL): P13, P24
  advisor breaks (s5 PASS, s4 FAIL): N14, N18

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
  blind/s3-sonnet/AV01.md  [no fences]
  blind/s3-sonnet/AV02.md  [no fences]
  blind/s3-sonnet/AV03.md  [no fences]
  blind/s3-sonnet/AV04.md  [no fences]
  blind/s3-sonnet/N01.md  [no fences]
  blind/s3-sonnet/N02.md  [no fences]
  blind/s3-sonnet/N03.md  [no fences]
  blind/s3-sonnet/N04.md  [no fences]
  blind/s3-sonnet/N05.md  [no fences]
  blind/s3-sonnet/N06.md  [no fences]
  blind/s3-sonnet/N07.md  [no fences]
  blind/s3-sonnet/N08.md  [no fences]
  blind/s3-sonnet/N09.md  [no fences]
  blind/s3-sonnet/N10.md  [no fences]
  blind/s3-sonnet/N11.md  [no fences]
  blind/s3-sonnet/N12.md  [no fences]
  blind/s3-sonnet/N13.md  [no fences]
  blind/s3-sonnet/N14.md  [no fences]
  blind/s3-sonnet/N15.md  [no fences]
  blind/s3-sonnet/N16.md  [no fences]
  blind/s3-sonnet/N17.md  [no fences]
  blind/s3-sonnet/N18.md  [no fences]
  blind/s3-sonnet/P01.md  [no fences]
  blind/s3-sonnet/P02.md  [no fences]
  blind/s3-sonnet/P03.md  [no fences]
  blind/s3-sonnet/P04.md  [no fences]
  blind/s3-sonnet/P05.md  [no fences]
  blind/s3-sonnet/P06.md  [no fences]
  blind/s4-fork-on/AV01.md  [no fences]
  blind/s4-fork-on/AV02.md  [no fences]
  blind/s4-fork-on/AV03.md  [no fences]
  blind/s4-fork-on/AV04.md  [no fences]
  blind/s4-fork-on/N01.md  [no fences]
  blind/s4-fork-on/N09.md  [no fences]
  blind/s4-fork-on/N14.md  [no fences]
  blind/s4-fork-on/N15.md  [no fences]
  blind/s4-fork-on/N18.md  [no fences]
  blind/s4-fork-on/P05.md  [no fences]
  blind/s4-fork-on/P07.md  [no fences]
  blind/s4-fork-on/P10.md  [no fences]
  blind/s4-fork-on/P12.md  [no fences]
  blind/s4-fork-on/P13.md  [no fences]
  blind/s4-fork-on/P14.md  [no fences]
  blind/s4-fork-on/P24.md  [no fences]
  blind/s4-fork-on/P25.md  [no fences]
  blind/s4-fork-on/P26.md  [no fences]
  blind/s4-fork-on/P27.md  [no fences]
  blind/s5-fork-off/AV01.md  [no fences]
  blind/s5-fork-off/AV02.md  [no fences]
  blind/s5-fork-off/AV03.md  [no fences]
  blind/s5-fork-off/AV04.md  [no fences]
  blind/s5-fork-off/N01.md  [no fences]
  blind/s5-fork-off/N02.md  [no fences]
  blind/s5-fork-off/N03.md  [no fences]
  blind/s5-fork-off/N04.md  [no fences]
  blind/s5-fork-off/N10.md  [no fences]
  blind/s5-fork-off/N12.md  [no fences]
  blind/s5-fork-off/N13.md  [no fences]
  blind/s5-fork-off/N14.md  [no fences]
  blind/s5-fork-off/N15.md  [no fences]
  blind/s5-fork-off/N18.md  [no fences]
  blind/s5-fork-off/P04.md  [no fences]
  blind/s5-fork-off/P05.md  [no fences]
  blind/s5-fork-off/P06.md  [no fences]
  blind/s5-fork-off/P07.md  [no fences]
  blind/s5-fork-off/P10.md  [no fences]
  blind/s5-fork-off/P12.md  [no fences]
  blind/s5-fork-off/P13.md  [no fences]
  blind/s5-fork-off/P14.md  [no fences]
  blind/s5-fork-off/P15.md  [no fences]
  blind/s5-fork-off/P16.md  [no fences]
  blind/s5-fork-off/P17.md  [no fences]
  blind/s5-fork-off/P18.md  [no fences]
  blind/s5-fork-off/P19.md  [no fences]
  blind/s5-fork-off/P20.md  [no fences]
  blind/s5-fork-off/P21.md  [no fences]
  blind/s5-fork-off/P23.md  [no fences]
  blind/s5-fork-off/P24.md  [no fences]
  blind/s5-fork-off/P25.md  [no fences]
  blind/s5-fork-off/P26.md  [no fences]
  blind/s5-fork-off/P27.md  [no fences]
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

item     s1   s2   s3   s4   s5   s6
------------------------------------
AV01      f    .    f    f    f    .
AV02      f    .    f    f    f    .
AV03      f    .    f    f    f    .
AV04      f    .    f    f    f    .
N01       f    .    f    f    f    .
N02       f    .    f    f    f    .
N03       f    .    f    f    f    .
N04       f    .    f    f    f    .
N05       f    .    f    f    f    .
N06       f    .    f    f    f    .
N07       f    .    f    f    f    .
N08       f    .    f    f    f    .
N09       f    .    f    f    f    .
N10       f    .    f    f    f    .
N11       f    .    f    f    f    .
N12       f    .    f    f    f    .
N13       f    .    f    f    f    .
N14       P    .    f    f    P    .
N15       f    .    f    f    f    .
N16       f    .    f    f    f    .
N17       f    .    f    f    f    .
N18       P    .    P    f    P    .
P01       f    .    f    f    f    .
P02       f    .    f    f    f    .
P03       f    .    f    f    f    .
P04       f    .    f    f    f    .
P05       f    .    f    f    f    .
P06       f    .    f    f    f    .
P07       f    .    .    f    f    .
P08       f    .    .    f    f    .
P09       f    .    .    f    f    .
P10       f    .    .    f    f    .
P11       f    .    .    f    f    .
P12       f    .    .    f    f    .
P13       f    .    .    P    f    .
P14       f    .    .    f    f    .
P15       f    .    .    f    f    .
P16       f    .    .    f    f    .
P17       f    .    .    f    f    .
P18       f    .    .    f    f    .
P19       f    .    .    f    f    .
P20       f    .    .    f    f    .
P21       f    .    .    f    f    .
P22       f    .    .    f    f    .
P23       f    .    .    f    f    .
P24       f    .    .    P    f    .
P25       f    .    .    f    f    .
P26       f    .    .    f    f    .
P27       f    .    .    f    f    .
P28       f    .    .    f    f    .

### matched

item     s1   s2   s3   s4   s5   s6
------------------------------------
AV01      f    .    .              .
AV02      f    .    .              .
AV03      f    .    .              .
AV04      f    .    .              .
N01       f    .    .              .
N02       f    .    .              .
N03       f    .    .              .
N04       f    .    .              .
N05       f    .    .              .
N06       f    .    .              .
N07       f    .    .              .
N08       f    .    .              .
N09       f    .    .              .
N10       f    .    .              .
N11       f    .    .              .
N12       f    .    .              .
N13       f    .    .              .
N15       f    .    .              .
N16       f    .    .              .
P01       f    .    .              .
P02       f    .    .              .
P03       f    .    .              .
P04       f    .    .              .
P05       f    .    .              .
P06       f    .    .              .
P07       f    .    .              .
P08       f    .    .              .
P09       f    .    .              .
P10       f    .    .              .
P11       f    .    .              .
P12       f    .    .              .
P13       P    .    .              .
P14       f    .    .              .
P15       f    .    .              .
P16       f    .    .              .
P17       f    .    .              .
P18       f    .    .              .
P19       f    .    .              .
P20       f    .    .              .
P21       f    .    .              .
P22       f    .    .              .
P23       f    .    .              .
P24       P    .    .              .
P25       f    .    .              .
P26       f    .    .              .
P27       f    .    .              .
P28       f    .    .              .

### heldout

item     s1   s2   s3   s4   s5   s6
------------------------------------
N02       f    .    .              .
N04       f    .    .              .
N05       f    .    .              .
N08       f    .    .              .
N13       f    .    .              .
N15       f    .    .              .
N16       f    .    .              .
P11       f    .    .              .
P13       f    .    .              .
P16       f    .    .              .
P17       f    .    .              .
P21       f    .    .              .
P22       f    .    .              .
P24       f    .    .              .

### uncovered

item     s1   s2   s3   s4   s5   s6
------------------------------------
N14       f    .    .              .
N17       f    .    .              .
N18       f    .    .              .

