"""Run the read-only subcommands.

Importing a module proves very little: the NameError in tier_assign.main() sat
on the last line of a function that imported cleanly and printed 130 rows
before dying. These tests execute the commands.
"""
import pytest

from chi_edge_bench import paths
from chi_edge_bench.cli import main


@pytest.fixture(autouse=True)
def _isolated_workspace(tmp_path):
    """Never let a test write into the real measurement record."""
    paths.set_workspace(tmp_path)
    yield tmp_path
    paths.set_workspace(None)


def test_where(capsys):
    assert main(["where"]) == 0
    out = capsys.readouterr().out
    assert "items         134" in out
    assert "workspace" in out


@pytest.mark.parametrize("suite,n", [("all", 134), ("core", 50),
                                     ("reservation", 84)])
def test_items(capsys, suite, n):
    assert main(["items", "--suite", suite]) == 0
    assert f"[{n} items, suite={suite}]" in capsys.readouterr().out


def test_selftest_gate_passes(capsys):
    assert main(["selftest"]) == 0
    out = capsys.readouterr().out
    assert "134/134 golds pass" in out
    assert "0 mismatches" in out


def test_score_a_gold(capsys):
    assert main(["score", "--item", "R01", "--gold"]) == 0


def test_score_rejects_an_unknown_item():
    with pytest.raises(SystemExit) as e:
        main(["score", "--item", "NOPE", "--gold"])
    assert "no such item" in str(e.value)


def test_prompts_writes_into_the_workspace(_isolated_workspace, capsys):
    assert main(["prompts"]) == 0
    written = list((_isolated_workspace / "prompts").rglob("*.txt"))
    assert len(written) == 414


def test_compare_against_the_shipped_baseline(capsys):
    ref = paths.baselines_dir() / "isolation_scores.csv"
    assert main(["compare", "--csv", str(ref)]) == 0
    out = capsys.readouterr().out
    assert "70B, advisor OFF" in out
    assert "capability" in out


def test_score_runs_on_an_empty_workspace_says_where_it_looked(capsys):
    """A user who scores nothing must be told which directory was searched.

    The CLI reports this as a message plus exit 1, not a propagated SystemExit:
    a delegated tool's exit is translated, never re-raised through main().
    """
    assert main(["score-runs"]) == 1
    err = capsys.readouterr().err
    assert "no answer files" in err
    assert "workspace chosen by" in err


def test_version():
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
