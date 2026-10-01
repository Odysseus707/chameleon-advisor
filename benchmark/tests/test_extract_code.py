"""Reading a hand-pasted chat answer.

An arm driven by hand - a model too expensive to call 96 times over an API -
arrives as raw chat text. It has prose around the code and almost never has
``` fences, because the person pasting it does not add them. The harness used
to extract nothing from that shape, so the answer scored as though no code was
written: a measurement of the paste rather than of the model.

These pin the three properties that make such an arm readable AND safe to
compare against the API arms:

  * unfenced code is recovered, including multi-line calls;
  * prose is never mistaken for code;
  * the HARNESS is unchanged, so no historical arm moves.

That last one is why recovery lives in `manual_arm.unfenced_blocks` and not in
`runner.extract_code`. Wiring it into the harness was tried: it moved 79 stored
verdicts, all in the two hand-pasted arms, and failed Level 2 verdict parity.
Extraction getting better must not restate a measurement already taken (R1).
"""
import ast

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "chi_edge_bench" / "tools"))

from chi_edge_bench.harness.runner import extract_code   # noqa: E402
from manual_arm import unfenced_blocks                   # noqa: E402

PASTED = """Sure! Here's how you'd reserve a Cascade Lake node and boot it.

First, point python-chi at the site and create the lease:

from datetime import timedelta
import chi
from chi import lease, server

chi.use_site("CHI@TACC")

my_lease = lease.Lease("cascadelake-lease", duration=timedelta(hours=3))
my_lease.add_node_reservation(amount=1, node_type="compute_cascadelake")
my_lease.submit(idempotent=True)

Note that you must bind the instance to the RESERVATION id, not the lease id:

my_server = server.Server(
    "cascadelake-node",
    image_name="CC-Ubuntu22.04",
    reservation_id=my_lease.node_reservations[0]["id"],
)
my_server.submit(idempotent=True, show="text")

That's it. The instance takes 10-20 minutes to deploy.
"""


def test_unfenced_paste_yields_parseable_code():
    code = unfenced_blocks(PASTED)
    assert code.strip(), "a pasted chat answer must not extract to nothing"
    ast.parse(code)


def test_multi_line_calls_survive():
    """The bug this test exists for.

    `Server(` opens a bracket and its closing `)` starts no statement, so a
    line-shape scanner flushes the block before the bracket closes and the
    whole call fails to parse and is dropped - taking the image name and the
    reservation wiring with it, which are exactly what the checkers look for.
    """
    code = unfenced_blocks(PASTED)
    assert "CC-Ubuntu22.04" in code
    assert 'node_reservations[0]["id"]' in code
    assert "server.Server(" in code


def test_prose_is_not_mistaken_for_code():
    code = unfenced_blocks(PASTED)
    for prose in ("Sure!", "That's it", "Note that you must", "First, point"):
        assert prose not in code, prose


def test_fenced_answers_are_untouched():
    """Strict additivity, the property that protects every existing arm."""
    fenced = "Here you go:\n\n```python\nimport chi\nchi.use_site('CHI@UC')\n```\n"
    assert extract_code(fenced) == "import chi\nchi.use_site('CHI@UC')\n"


def test_pure_code_answers_are_untouched():
    pure = "import chi\nchi.use_site('CHI@UC')\n"
    assert extract_code(pure) == pure


def test_the_harness_itself_still_ignores_unfenced_code():
    """R1, pinned. If this ever passes, a historical arm has silently moved."""
    assert extract_code(PASTED).strip() == ""


def test_an_answer_with_no_code_still_extracts_nothing():
    """A prose-only answer must not acquire code it never had.

    The recovery path keeps a block only if `ast.parse` accepts it, so a line
    that merely looks like a call - and this is ordinary English - is dropped
    rather than promoted into the answer.
    """
    prose = ("You should reserve a compute_cascadelake node. Use chi.use_site "
             "to select the site, then add_node_reservation(amount=1) and "
             "submit the lease. Finally boot the instance.\n")
    assert unfenced_blocks(prose).strip() == ""
