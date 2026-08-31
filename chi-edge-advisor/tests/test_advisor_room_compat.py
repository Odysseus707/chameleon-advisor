"""The disconnected advisor path must not move.

The benchmark drives advisor_room.advise() in-process (ForkAdapter.answer in
benchmark/chi_edge_bench/tools/run_bench.py) and never touches web_rag.py. So
every cited result in the reservation suite depends on the *disconnected*
rendering staying exactly as it was. Reservation support adds an identity=
parameter, a cost line and a real project name to that same code path; this
test is what proves none of it leaks into the no-identity case.

The golden was captured at commit 231e7ba, the advisor-integration checkpoint,
before any reservation code existed. Regenerate it only by deliberate
re-baselining - see tests/data/_capture_golden_reference.py - never to make a
failure go away. A diff here means benchmark provenance is at risk.
"""
import json
import sys
import unittest
from pathlib import Path

# advisor_room lives in the sibling fork repo, which is a separate git repo and
# may simply be absent on a fresh clone of this one. Skip rather than fail.
_WS = Path(__file__).resolve().parents[2]
_FORK = _WS / "RAG-docs-chameleon"
_HAVE_FORK = (_FORK / "advisor_room.py").is_file()
if _HAVE_FORK and str(_FORK) not in sys.path:
    sys.path.insert(0, str(_FORK))

# tests/data is imported as a package-relative module, so tests/ must be importable.
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

_GOLDEN_PATH = _TESTS / "data" / "advisor_room_render_golden.json"


def _golden():
    return json.loads(_GOLDEN_PATH.read_text())


@unittest.skipUnless(_HAVE_FORK, "RAG-docs-chameleon not present next to this repo")
class TestRenderGolden(unittest.TestCase):
    """_render output is frozen for the no-identity path."""

    @classmethod
    def setUpClass(cls):
        cls.golden = _golden()
        from data import _capture_golden_reference as ref  # noqa: PLC0415
        cls.ref = ref

    def test_golden_covers_every_case(self):
        """Guard against a case being dropped from the fixture and going unnoticed."""
        self.assertEqual(set(self.golden), set(self.ref.cases()))
        self.assertGreaterEqual(len(self.golden), 8)

    def test_render_matches_golden(self):
        actual = self.ref.render_all()
        for name in sorted(self.golden):
            with self.subTest(case=name):
                self.assertEqual(
                    actual[name], self.golden[name],
                    f"advisor_room._render changed for case {name!r}. If this is "
                    "intentional, re-baseline with tests/data/"
                    "_capture_golden_reference.py and say so in the commit.",
                )

    def test_project_name_is_still_a_placeholder_when_disconnected(self):
        """Without an identity the emitted code must not name a real project.

        This is the specific regression reservation support could introduce:
        filling the connected user's project into every rendering, including the
        benchmark's.
        """
        for name, text in self.golden.items():
            with self.subTest(case=name):
                self.assertIn('chi.set("project_name", "<your project name>")', text)

    def test_no_connected_vocabulary_leaks_into_disconnected_output(self):
        """Connected-only wording must be absent from the disconnected render."""
        forbidden = ("device-hours", "Service Unit", "lease_id=", "Created lease")
        for name, text in self.golden.items():
            for token in forbidden:
                with self.subTest(case=name, token=token):
                    self.assertNotIn(token, text)


@unittest.skipUnless(_HAVE_FORK, "RAG-docs-chameleon not present next to this repo")
class TestRenderSignature(unittest.TestCase):
    """The call shapes ForkAdapter and web_rag already use must keep working."""

    def test_render_accepts_two_positional_args(self):
        import advisor_room  # noqa: PLC0415
        from data import _capture_golden_reference as ref  # noqa: PLC0415

        rec, avail = ref.cases()["minimal"]
        self.assertEqual(advisor_room._render(rec, avail), _golden()["minimal"])

    def test_advise_takes_question_only(self):
        """advise(question) must remain callable with a single argument.

        ForkAdapter.answer calls self._ar.advise(q) positionally; an identity
        parameter added without a default would break every benchmark run.
        """
        import inspect  # noqa: PLC0415

        import advisor_room  # noqa: PLC0415

        params = inspect.signature(advisor_room.advise).parameters
        required = [n for n, p in params.items()
                    if p.default is inspect.Parameter.empty
                    and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
        self.assertEqual(required, ["question"])


if __name__ == "__main__":
    unittest.main()
