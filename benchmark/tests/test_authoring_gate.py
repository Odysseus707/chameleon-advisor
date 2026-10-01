"""The Stage 8 authored-tier gate: what it reads before it judges.

The gate's five rules are only as good as the text it checks against. This
file covers that text, which nothing did before: verify_authored had no unit
tests at all, and the defect below sat in it undetected across the twenty-two
artifacts authored in the first pass.

Every guard here has been mutation-tested: broken deliberately, confirmed to
turn a test red, restored.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "corpus_v2" / "tools"))
import verify_authored as V


def notebook(source_line: str, padding_bytes: int) -> str:
    """A notebook whose SIZE is output and whose SOURCE is one line.

    This is the shape of a real artifact notebook: a few lines of provisioning
    code under megabytes of base64 output images and training logs.
    """
    return json.dumps({
        "cells": [
            {"cell_type": "code", "source": [source_line],
             "outputs": [{"data": {"image/png": "A" * padding_bytes}}]},
        ],
        "metadata": {}, "nbformat": 4, "nbformat_minor": 5,
    })


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    def add(name, text):
        (tmp_path / name).write_text(text, encoding="utf-8")
        subprocess.run(["git", "-C", str(tmp_path), "add", name], check=True)
    return tmp_path, add


def test_a_big_notebooks_source_is_still_read(repo):
    """A notebook is sized by its output and read for its source. Judging it on
    file size excluded five artifacts' notebooks from the tree entirely, so
    every probe quoted from one was rejected as not-verbatim while being
    verbatim in it."""
    path, add = repo
    add("big.ipynb", notebook('chi.use_site("CHI@UC")\n', 5_000_000))
    tree = V.tree_text(path)
    assert 'chi.use_site("CHI@UC")' in tree


def test_a_big_plain_file_is_still_skipped(repo):
    """The cap exists for blobs and still applies to them. Only notebooks are
    exempt, and only because their bulk is not their content."""
    path, add = repo
    add("blob.txt", "NEEDLE\n" + "x" * 5_000_000)
    assert "NEEDLE" not in V.tree_text(path)


def test_a_small_notebooks_output_is_still_read(repo):
    """Strictly additive. Tags have legitimately traced to notebook OUTPUT,
    which is part of what the artifact committed; a fix that added large
    notebooks by dropping raw text would have broken those."""
    path, add = repo
    add("small.ipynb", notebook("print('hi')\n", 100).replace("A" * 100, "ZOOKEEPER"))
    tree = V.tree_text(path)
    assert "ZOOKEEPER" in tree
    assert "print('hi')" in tree


def test_a_malformed_notebook_does_not_abort_the_tree(repo):
    """One unparseable notebook must not cost the gate every other file."""
    path, add = repo
    add("bad.ipynb", "{not json at all")
    add("good.py", "MARKER = 1\n")
    assert "MARKER = 1" in V.tree_text(path)


# ------------------------------------------------ what a retrieval tag is FOR
# Measured, not assumed. Authoring all 90 artifacts with 11.8 tags each dropped
# tree L2 routing from 25.0% to 17.5%; removing the shared provisioning
# vocabulary, leaving 7.6 tags each, took it to 35.0%; topping those back up to
# eight with mined terms pushed it down again to 30.0%.

import author as A


def payload(**over):
    base = dict(summary="s", preconditions=["p"], traps_illustrated=["t"],
                not_covered=["n"], memorization_probes=["m"],
                uncertainties=["u"], workload_tags=[],
                retrieval_tags=["leaftl", "asplos", "ssd", "wheatman", "sysflow"])
    base.update(over)
    return base


class _Rec(dict):
    pass


def errors(**over):
    """apply()'s validation only. Returns before writing when anything fails."""
    return A.apply(_Rec(id="__nonexistent__"), payload(**over))


def test_provisioning_mechanics_are_refused_as_tags():
    """`jupyter` reached 58 of 90 artifacts, `floating ip` 32, a site name 60.
    A tag true of most artifacts identifies none of them."""
    errs = errors(retrieval_tags=["leaftl", "asplos", "ssd", "wheatman",
                                  "jupyter", "lease", "CHI@UC"])
    assert any("provisions" in e for e in errs), errs
    assert any("jupyter" in e for e in errs), errs


def test_five_sharp_tags_are_enough():
    """The minimum was 8 and forced filler at ninety artifacts. Five tags that
    name the artifact must pass.

    apply() returns its errors BEFORE writing and only reaches the filesystem
    once validation is clean, so reaching a missing extraction file is the
    signal that nothing was rejected."""
    with pytest.raises(FileNotFoundError):
        errors()


def test_four_tags_is_still_too_few():
    errs = errors(retrieval_tags=["leaftl", "asplos", "ssd", "wheatman"])
    assert any("at least 5" in e for e in errs), errs


def test_the_site_name_rule_matches_the_registrys_own():
    """registry.py already refused site names on the fallback path for exactly
    this reason. The authored path was missing the same rule."""
    for site in ("CHI@UC", "CHI@TACC", "KVM@TACC", "CHI@Edge"):
        assert site in A.MECHANICS_TAGS, site
