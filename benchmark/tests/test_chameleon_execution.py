"""Executable verification of the bare-metal golds.

The checkers prove an answer has the right shape. These prove the golds would
DO the right thing: each is run against a stub backed by the real Blazar capture
of 2026-09-04, and its recorded effect - site, node type, count, lease hours,
image, reservation binding, teardown - is compared to an expectation the item
declares separately from its checkers.

This is what makes "the golds are verified" a claim with evidence behind it
rather than a restatement of the admission gate.
"""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

BENCH = Path(__file__).resolve().parent.parent
TOOL = BENCH / "corpus_v2" / "tools" / "verify_golds_exec.py"
ITEMS = BENCH / "chameleon_bench" / "data" / "items"

sys.path.insert(0, str(TOOL.parent))
import verify_golds_exec as V  # noqa: E402


def items():
    return [yaml.safe_load(p.read_text()) for p in sorted(ITEMS.glob("*.yaml"))]


def executable():
    return [i for i in items() if i.get("exec_expect")]


def test_there_are_executable_golds():
    """Guards the parametrised tests below: with no executable items they all
    silently pass, and a suite that verifies nothing reads as a verified one."""
    assert len(executable()) >= 7


def test_every_code_item_declares_an_execution_expectation():
    """A code gold with no exec_expect is unverified beyond its own checkers.
    Prose answers (abstention items) are legitimately exempt."""
    for i in items():
        if i.get("expected_answer_type") == "code":
            assert i.get("exec_expect"), (
                f"{i['id']} is a code item with no exec_expect; it would be "
                "admitted on checker agreement alone")


@pytest.mark.parametrize("item", executable(), ids=lambda i: i["id"])
def test_gold_executes_and_does_what_the_item_claims(item):
    rc, trace, err = V.run_gold(item["gold_spec"])
    assert rc == 0, f"{item['id']} gold raised:\n{err[-800:]}"
    bad = V.compare(item["exec_expect"], trace)
    assert not bad, f"{item['id']}: " + "; ".join(bad)


# -- the verifier must be able to fail ------------------------------------
# A check that has only ever passed is not known to be a check. These break a
# gold in ways the AST checkers would not notice and require execution to catch.

@pytest.mark.parametrize("old,new,expect_in", [
    ('node_type="gpu_mi100"', 'node_type="gpu_p100"', "node reservations"),
    ('timedelta(hours=3)', 'timedelta(hours=9)', "lease hours"),
    ('image_name="CC-Ubuntu22.04"', 'image_name="CC-Ubuntu20.04"', "server image"),
])
def test_execution_catches_a_wrong_but_well_formed_gold(old, new, expect_in):
    item = next(i for i in executable() if i["id"] == "CB09")
    assert old in item["gold_spec"]
    rc, trace, err = V.run_gold(item["gold_spec"].replace(old, new, 1))
    assert rc == 0, err[-400:]
    bad = V.compare(item["exec_expect"], trace)
    assert any(expect_in in b for b in bad), \
        f"execution did not notice {old!r} -> {new!r}; got {bad}"


def test_execution_catches_dropped_teardown():
    item = next(i for i in executable() if i["id"] == "CB09")
    stripped = "\n".join(l for l in item["gold_spec"].splitlines()
                         if "delete" not in l)
    rc, trace, _ = V.run_gold(stripped)
    assert rc == 0
    bad = V.compare(item["exec_expect"], trace)
    assert any("teardown" in b for b in bad), bad


def test_stub_rejects_hardware_absent_from_the_selected_site():
    """Real capture data: gpu_mi100 exists at CHI@TACC and not at CHI@UC."""
    rc, _, err = V.run_gold(
        'import chi\nfrom chi import lease\n'
        'chi.use_site("CHI@UC")\n'
        'l = lease.Lease("x")\n'
        'l.add_node_reservation(amount=1, node_type="gpu_mi100")\n')
    assert rc != 0 and "does not exist at CHI@UC" in err


def test_stub_models_the_lease_id_trap_as_quiet_then_failing():
    """The documented trap, executable.

    VERIFIED LIVE 2026-09-05 (CHI@TACC, project CHI-231225): Nova ACCEPTS a
    lease id as reservation_id. The instance is created, and only then reaches
    ERROR. The stub must therefore be QUIET at construction and fail at submit.
    An earlier version raised immediately, which made a silent trap look loud -
    the opposite of what A55's traps_illustrated describes and of what the
    testbed actually does.
    """
    prelude = ('import chi\nfrom chi import lease, server\n'
               'chi.use_site("CHI@TACC")\n'
               'l = lease.Lease("x")\n'
               'l.add_node_reservation(amount=1, node_type="gpu_mi100")\n'
               'l.submit()\n'
               's = server.Server("n", image_name="CC-Ubuntu22.04", '
               'reservation_id=l.id)\n')

    # construction alone must NOT fail - that is the "quiet" half
    rc, _, err = V.run_gold(prelude)
    assert rc == 0, f"construction should be quiet, but raised:\n{err[-400:]}"

    # submit is where the real testbed surfaces it
    rc, _, err = V.run_gold(prelude + "s.submit()\n")
    assert rc != 0, "submit should fail: the instance is bound to no reservation"
    assert "is a LEASE id" in err and "ERROR" in err, err[-400:]


def test_stub_models_get_node_reservation_as_broken():
    """The other half of the live findings, and it had no test at all.

    VERIFIED LIVE 2026-09-05 and again 2026-09-07 (CHI@TACC, project
    CHI-231225, python-chi 1.2.10 both times): `lease.get_node_reservation`
    raises `AttributeError: 'Lease' object has no attribute 'get'`.
    `_reservation_matching` expects a lease dict while `get_lease` now returns
    a Lease object.

    The stub returned the reservation id until 2026-09-07, i.e. it modelled a
    broken idiom as working. NO GOLD uses the spelling, which is exactly why
    this went unnoticed and why it still mattered: 20 corpus artifacts teach
    it, so a model that copies one would have been graded against a stub that
    disagreed with the testbed, and would have passed while shipping code that
    cannot run. CB38 exists to catch that answer.

    Asserted on the ERROR TYPE and message, not merely on "it raised": the
    previous behaviour also raised for an unrelated reason (RuntimeError, on a
    lease with no node reservation), so a weaker assertion would pass against
    the defect this replaces.
    """
    prelude = ('import chi\nfrom chi import lease\n'
               'chi.use_site("CHI@TACC")\n'
               'l = lease.Lease("x")\n'
               'l.add_node_reservation(amount=1, node_type="gpu_mi100")\n'
               'l.submit()\n')

    # The working spelling every gold actually uses is untouched.
    rc, _, err = V.run_gold(prelude + 'assert l.node_reservations[0]["id"]\n')
    assert rc == 0, f"the indexed form must still work:\n{err[-400:]}"

    rc, _, err = V.run_gold(prelude + "lease.get_node_reservation(l.id)\n")
    assert rc != 0, "get_node_reservation must fail as it does on the testbed"
    assert "AttributeError" in err, err[-400:]
    assert "'Lease' object has no attribute 'get'" in err, err[-400:]


def test_scarcity_is_recorded_not_failed():
    """0 free is a fact about the calendar, not a mistake in the answer.
    Grading it would make the suite measure when it was run."""
    rc, trace, err = V.run_gold(
        'import chi\nfrom chi import lease\n'
        'chi.use_site("CHI@UC")\n'
        'l = lease.Lease("x")\n'
        'l.add_node_reservation(amount=1, node_type="gpu_rtx_6000")\n'
        'l.submit()\n')
    assert rc == 0, err[-400:]
    assert any("free at capture time" in n for n in trace["notes"])
