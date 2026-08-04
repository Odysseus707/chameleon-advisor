# Run scores summary

## Fill status (non-empty / total answer files)

condition     s1-chatbot        s2-gpt     s3-sonnet    s4-fork-on   s5-fork-off       s6-opus
----------------------------------------------------------------------------------------------
blind              22/50          0/50         28/50         50/50         50/50          0/50
matched             0/47          0/47          0/47             —             —          0/47
heldout             0/14          0/14          0/14             —             —          0/14
uncovered            0/3           0/3           0/3             —             —           0/3

## Overall PASS rate (all checkers green; scored answers only)

condition     s1-chatbot        s2-gpt     s3-sonnet    s4-fork-on   s5-fork-off       s6-opus
----------------------------------------------------------------------------------------------
blind          2/22 (9%)             —     1/28 (4%)     2/50 (4%)     2/50 (4%)             —
matched                —             —             —             —             —             —
heldout                —             —             —             —             —             —
uncovered              —             —             —             —             —             —

## Rates on COMMON items only (selection-bias guard)

### blind — 22 items answered by all of: s1-chatbot, s3-sonnet, s4-fork-on, s5-fork-off

metric        s1-chatbot     s3-sonnet    s4-fork-on   s5-fork-off
------------------------------------------------------------------
PASS           2/22 (9%)     0/22 (0%)     0/22 (0%)     2/22 (9%)
mechanism      5/60 (8%)   19/60 (32%)     4/60 (7%)     5/60 (8%)
specifics      6/69 (9%)   17/69 (25%)    7/69 (10%)    7/69 (10%)
safety       18/28 (64%)   23/28 (82%)   18/28 (64%)   19/28 (68%)

## Checker-group pass rates (checks passed / checks run)

### mechanism

condition     s1-chatbot        s2-gpt     s3-sonnet    s4-fork-on   s5-fork-off       s6-opus
----------------------------------------------------------------------------------------------
blind          5/60 (8%)             —   28/75 (37%)    9/115 (8%)    8/115 (7%)             —
matched                —             —             —             —             —             —
heldout                —             —             —             —             —             —
uncovered              —             —             —             —             —             —

### specifics

condition     s1-chatbot        s2-gpt     s3-sonnet    s4-fork-on   s5-fork-off       s6-opus
----------------------------------------------------------------------------------------------
blind          6/69 (9%)             —   21/78 (27%)  22/119 (18%)  15/119 (13%)             —
matched                —             —             —             —             —             —
heldout                —             —             —             —             —             —
uncovered              —             —             —             —             —             —

### safety

condition     s1-chatbot        s2-gpt     s3-sonnet    s4-fork-on   s5-fork-off       s6-opus
----------------------------------------------------------------------------------------------
blind        18/28 (64%)             —   28/33 (85%)   25/43 (58%)   26/43 (60%)             —
matched                —             —             —             —             —             —
heldout                —             —             —             —             —             —
uncovered              —             —             —             —             —             —

## Advisor ablation (blind): s4-fork-on vs s5-fork-off

items compared: 50 | s4 PASS 2 | s5 PASS 2 | delta +0

  mechanism  s4     9/115 (8%)   s5     8/115 (7%)
  specifics  s4   22/119 (18%)   s5   15/119 (13%)
  safety     s4    25/43 (58%)   s5    26/43 (60%)

  advisor fixes (s4 PASS, s5 FAIL): P13, P24
  advisor breaks (s5 PASS, s4 FAIL): N14, N18

## Fence lint (scored answers where the extractor sees NO code)

  These score near-zero mechanically. If the answer visibly contains
  code, the fences were stripped on paste — re-paste or --wrap-code.
  (Prose-only answers to abstention items are fine here.)

  blind/s1-chatbot/AV03.md  [no fences]
  blind/s1-chatbot/N01.md  [no fences]
  blind/s1-chatbot/N02.md  [no fences]
  blind/s1-chatbot/N03.md  [no fences]
  blind/s1-chatbot/N04.md  [no fences]
  blind/s1-chatbot/N05.md  [no fences]
  blind/s1-chatbot/N07.md  [no fences]
  blind/s1-chatbot/N08.md  [no fences]
  blind/s1-chatbot/N09.md  [no fences]
  blind/s1-chatbot/N10.md  [no fences]
  blind/s1-chatbot/N14.md  [no fences]
  blind/s1-chatbot/N16.md  [no fences]
  blind/s1-chatbot/N18.md  [no fences]
  blind/s3-sonnet/AV01.md  [no fences]
  blind/s3-sonnet/AV02.md  [no fences]
  blind/s3-sonnet/AV03.md  [no fences]
  blind/s3-sonnet/N02.md  [no fences]
  blind/s3-sonnet/N03.md  [no fences]
  blind/s3-sonnet/N04.md  [no fences]
  blind/s3-sonnet/N08.md  [no fences]
  blind/s3-sonnet/N09.md  [no fences]
  blind/s3-sonnet/N10.md  [no fences]
  blind/s3-sonnet/N14.md  [no fences]
  blind/s3-sonnet/P02.md  [no fences]
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
N18       P    .    f    f    P    .
P01       .    .    P    f    f    .
P02       .    .    f    f    f    .
P03       .    .    f    f    f    .
P04       .    .    f    f    f    .
P05       .    .    f    f    f    .
P06       .    .    f    f    f    .
P07       .    .    .    f    f    .
P08       .    .    .    f    f    .
P09       .    .    .    f    f    .
P10       .    .    .    f    f    .
P11       .    .    .    f    f    .
P12       .    .    .    f    f    .
P13       .    .    .    P    f    .
P14       .    .    .    f    f    .
P15       .    .    .    f    f    .
P16       .    .    .    f    f    .
P17       .    .    .    f    f    .
P18       .    .    .    f    f    .
P19       .    .    .    f    f    .
P20       .    .    .    f    f    .
P21       .    .    .    f    f    .
P22       .    .    .    f    f    .
P23       .    .    .    f    f    .
P24       .    .    .    P    f    .
P25       .    .    .    f    f    .
P26       .    .    .    f    f    .
P27       .    .    .    f    f    .
P28       .    .    .    f    f    .

### matched

item     s1   s2   s3   s4   s5   s6
------------------------------------
AV01      .    .    .              .
AV02      .    .    .              .
AV03      .    .    .              .
AV04      .    .    .              .
N01       .    .    .              .
N02       .    .    .              .
N03       .    .    .              .
N04       .    .    .              .
N05       .    .    .              .
N06       .    .    .              .
N07       .    .    .              .
N08       .    .    .              .
N09       .    .    .              .
N10       .    .    .              .
N11       .    .    .              .
N12       .    .    .              .
N13       .    .    .              .
N15       .    .    .              .
N16       .    .    .              .
P01       .    .    .              .
P02       .    .    .              .
P03       .    .    .              .
P04       .    .    .              .
P05       .    .    .              .
P06       .    .    .              .
P07       .    .    .              .
P08       .    .    .              .
P09       .    .    .              .
P10       .    .    .              .
P11       .    .    .              .
P12       .    .    .              .
P13       .    .    .              .
P14       .    .    .              .
P15       .    .    .              .
P16       .    .    .              .
P17       .    .    .              .
P18       .    .    .              .
P19       .    .    .              .
P20       .    .    .              .
P21       .    .    .              .
P22       .    .    .              .
P23       .    .    .              .
P24       .    .    .              .
P25       .    .    .              .
P26       .    .    .              .
P27       .    .    .              .
P28       .    .    .              .

### heldout

item     s1   s2   s3   s4   s5   s6
------------------------------------
N02       .    .    .              .
N04       .    .    .              .
N05       .    .    .              .
N08       .    .    .              .
N13       .    .    .              .
N15       .    .    .              .
N16       .    .    .              .
P11       .    .    .              .
P13       .    .    .              .
P16       .    .    .              .
P17       .    .    .              .
P21       .    .    .              .
P22       .    .    .              .
P24       .    .    .              .

### uncovered

item     s1   s2   s3   s4   s5   s6
------------------------------------
N14       .    .    .              .
N17       .    .    .              .
N18       .    .    .              .

