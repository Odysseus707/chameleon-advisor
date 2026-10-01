"""The wing-aware benchmark tools: score_wing and run_llm_wing.

Both are new surfaces that decide what a collected number MEANS, so the things
guarded here are the ones that would make a number wrong while looking right:
scoring the wrong wing, scoring nothing at all, and letting the two arms of an
A/B differ by anything other than the advisor.
"""
import ast
import re
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "chi_edge_bench/tools"
SCORE = TOOLS / "score_wing.py"
RUNLLM = TOOLS / "run_llm_wing.py"


def src(path):
    return path.read_text(encoding="utf-8")


def func(path, name):
    for node in ast.walk(ast.parse(src(path))):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src(path), node)
    raise AssertionError(f"{name}() not found in {path.name}")


class TestBothSetTheWing(unittest.TestCase):
    """P2: the wing is process state.

    A tool that forgets it resolves items, snapshots and the capability table
    to the edge wing and then grades bare-metal answers against CHI@Edge
    hardware. It failed loudly once only because the data does not overlap.
    """

    def test_score_wing_sets_it(self):
        self.assertIn("paths.set_wing(args.wing)", src(SCORE))

    def test_run_llm_wing_sets_it(self):
        self.assertIn("paths.set_wing(args.wing)", src(RUNLLM))


class TestNeitherPassesVacuously(unittest.TestCase):
    """P5: an empty result set reads as a pass.

    "0 items scored, exit 0" is indistinguishable from a clean run in a log,
    and it is exactly what a mis-set wing or a typo'd arm name produces.
    """

    def test_score_wing_refuses_no_items(self):
        self.assertIn("no {args.suite} items under", src(SCORE).replace('f"', '"'))
        self.assertIn("return 2", src(SCORE))

    def test_score_wing_refuses_an_arm_with_no_answers(self):
        body = func(SCORE, "main")
        self.assertIn('if not first["rows"]', body)
        self.assertIn("nothing was scored", body)

    def test_run_llm_wing_refuses_no_items(self):
        body = func(RUNLLM, "main")
        self.assertIn("return 2", body)
        self.assertIn("return 0 if ok else 1", body)


class TestTheAbIsFair(unittest.TestCase):
    """The only difference between the arms must be the advisor.

    If the system prompt, the model or the item text varied too, a score gap
    would be unattributable - which is worse than no comparison, because it
    still looks like one.
    """

    def test_one_system_prompt_shared_by_both_arms(self):
        tree = ast.parse(src(RUNLLM))
        assigns = [n for n in tree.body if isinstance(n, ast.Assign)
                   and any(getattr(t, "id", "") == "SYSTEM_PROMPT" for t in n.targets)]
        self.assertEqual(len(assigns), 1, "SYSTEM_PROMPT must be a single constant")
        body = func(RUNLLM, "main")
        self.assertNotIn("SYSTEM_PROMPT =", body)

    def test_the_advisor_arm_only_prepends(self):
        """The item prompt itself is never rewritten, only preceded.

        Asserted as a PROPERTY rather than as one literal line. The literal
        version broke when `advisor_finding` was allowed to return None and the
        call was lifted into its own statement - a refactor that left the
        invariant completely intact. A guard that fails on rearrangement while
        still passing on a real rewrite is guarding the wrong thing.
        """
        body = func(RUNLLM, "main")
        self.assertIn('user = item["prompt"]', body)
        # Every assignment to `user` after that is a prepend onto `user`.
        rewrites = [ln.strip() for ln in body.splitlines()
                    if re.match(r"\s*user\s*=", ln)
                    and 'item["prompt"]' not in ln]
        self.assertTrue(rewrites, "the advisor arm must assign `user` at all")
        for ln in rewrites:
            self.assertRegex(
                ln, r"user = (ADVISOR|ARTIFACT)_PREAMBLE\.format\(.*\) \+ user$",
                f"the prompt must only be preceded, never rewritten: {ln}")

    def test_both_halves_of_the_advisor_are_offered(self):
        """The bug this test exists for, and it cost a whole measurement.

        The advisor has two halves: the ladder answers "what is free at this
        site" and needs a site; the retrieval router answers "what does the
        corpus show" and needs only the question. Only the ladder was wired in,
        so all 40 CB items - which carry no site - received a prompt
        byte-identical to the bare arm's, and both arms scored 0.0% mechanism
        and 0.8% specifics. That measured a model with no reference material,
        not an advisor that failed to help.
        """
        body = func(RUNLLM, "main")
        self.assertIn("finding = advisor_finding(item)", body)
        self.assertIn("artifact_context(item)", body)
        # The ladder is tried first; retrieval is the fallback, not a duplicate.
        self.assertLess(body.index("advisor_finding(item)"),
                        body.index("artifact_context(item)"))

    def test_an_item_with_neither_gets_an_identical_prompt(self):
        """Fairness for anything neither half can speak to.

        Such an item must receive the SAME prompt in both arms - identical by
        construction - so a score gap is attributable to items that actually
        received context. Substituting a placebo, or dropping those items from
        one arm, would each make the A/B say more than the data supports.
        """
        body = func(RUNLLM, "main")
        i = body.index("no_context += 1")
        stmt = body[i:body.index("\n", i)]
        self.assertNotIn("user", stmt,
                         "the no-context branch must leave the prompt alone")

    def test_both_arms_pin_the_same_model(self):
        body = func(RUNLLM, "main")
        self.assertIn("pin_model_env(Path(args.config))", body)
        # ...and it is applied before either arm branches.
        self.assertLess(body.index("pin_model_env"), body.index("args.advisor == \"on\""))


class TestSecretsNeverLand(unittest.TestCase):
    def test_the_key_is_never_recorded(self):
        """It is read from the environment and must reach no file we write."""
        text = src(RUNLLM)
        for name in ("TEJAS_API_KEY", "LLM_API_KEY"):
            # Referenced only in the operator hint, never assigned or stored.
            for line in text.splitlines():
                if name in line:
                    self.assertIn("SECRET-KEY", line,
                                  f"{name} appears outside the operator hint")

    def test_the_manifest_records_the_model_not_the_key(self):
        body = func(RUNLLM, "pin_model_env")
        self.assertIn('"model"', body)
        self.assertNotIn("KEY", body)


class TestAnswersAreVerbatim(unittest.TestCase):
    def test_the_model_output_is_written_unmodified(self):
        """The scorer must read what the model said, not a cleaned-up version.

        Recovering fences or trimming prose here would change what is being
        measured, silently and in the direction that flatters the system.
        """
        body = func(RUNLLM, "main")
        self.assertIn("dest.write_text(text)", body)
        for verb in (".strip())", ".replace(", "textwrap"):
            self.assertNotIn(f"dest.write_text(text{verb}", body)

    def test_an_error_is_recorded_as_a_result(self):
        body = func(RUNLLM, "main")
        self.assertIn("LLM ERROR", body)
        self.assertIn("errored", body)


class TestScoreWingLeavesTheFrozenScorerAlone(unittest.TestCase):
    def test_it_reuses_evaluate_rather_than_reimplementing_it(self):
        """Two scoring implementations would drift, and the disagreement would
        show up as a mysterious score change nobody could attribute."""
        self.assertIn("from chi_edge_bench.harness.runner import evaluate",
                      src(SCORE))

    def test_it_neither_imports_nor_invokes_the_frozen_scorer(self):
        """Naming it in the docstring is correct - that is where the reason
        for the split belongs. Depending on it in code is not."""
        tree = ast.parse(src(SCORE))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertNotIn("score_runs", a.name)
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("score_runs", node.module or "")
        code = "\n".join(l for l in src(SCORE).splitlines()
                          if not l.strip().startswith("#"))
        self.assertNotIn("score_runs(", code)


if __name__ == "__main__":
    unittest.main()
