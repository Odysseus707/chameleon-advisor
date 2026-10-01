"""The learned intuition store.

It holds LLM conclusions about what workloads need. Everything here guards the
same boundary: a remembered guess must stay a guess, stay reproducible, and
stay out of the two places that record measured fact.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from advisor.select.intuition import (MIN_OVERLAP, Intuition, IntuitionStore,
                                      _tokens)
from advisor.select.specs import extract, infer_requirements


class FakeLLM:
    name = "fake"

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return self.payload


def tmp():
    return Path(tempfile.mkdtemp()) / "intuition.json"


T0 = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


class TestOnlyGuessesAreRemembered(unittest.TestCase):
    def test_inferred_values_are_stored(self):
        store = IntuitionStore()
        req = infer_requirements("fine-tune a 7B model",
                                 client=FakeLLM('{"min_vram_gb": 75}'),
                                 allow_llm=True, intuition=store)
        self.assertEqual(len(store), 1)
        self.assertEqual(store.records[0].infers, {"min_vram_gb": 80})
        self.assertTrue(store.records[0].rounded_up)

    def test_what_the_user_stated_is_never_stored(self):
        """Their "180 GB" is a fact about their job, not our conclusion.

        Storing it would let one stranger's stated requirement return as an
        assumption about somebody else's work.
        """
        store = IntuitionStore()
        store.remember("a job needing 180 GB or more of RAM",
                       extract("a job needing 180 GB or more of RAM"))
        self.assertEqual(len(store), 0)

    def test_nothing_inferred_stores_nothing(self):
        store = IntuitionStore()
        self.assertIsNone(store.remember("just give me a node",
                                         extract("just give me a node")))
        self.assertEqual(len(store), 0)

    def test_entries_carry_no_author(self):
        """Deliberate. Which model guessed is not evidence about the guess."""
        store = IntuitionStore()
        infer_requirements("train a model", client=FakeLLM('{"min_vram_gb": 24}'),
                           allow_llm=True, intuition=store)
        fields = set(Intuition.__dataclass_fields__)
        self.assertNotIn("author", fields)
        self.assertNotIn("model", fields)


class TestRecallStaysAGuess(unittest.TestCase):
    def setUp(self):
        self.store = IntuitionStore([Intuition(
            id="li_0001", use_case="fine-tune a vision transformer",
            infers={"min_vram_gb": 48}, taught_by="fine-tune a vision transformer",
            recorded_utc=T0.isoformat(), confirmed=False)])

    def test_a_recalled_magnitude_only_ranks(self):
        req = infer_requirements("fine-tune a vision transformer on CHI@TACC",
                                 allow_llm=False, intuition=self.store)
        self.assertEqual(req.origin["min_vram_gb"], "recalled")
        self.assertEqual(req.soft(), {"min_vram_gb": 48})
        self.assertEqual(req.hard(), {})

    def test_recall_says_where_it_came_from(self):
        req = infer_requirements("fine-tune a vision transformer",
                                 allow_llm=False, intuition=self.store)
        joined = " ".join(req.assumptions)
        self.assertIn("earlier conclusion", joined)
        self.assertIn("not since confirmed", joined)

    def test_a_confirmed_entry_says_so_instead(self):
        self.store.confirm("li_0001")
        req = infer_requirements("fine-tune a vision transformer",
                                 allow_llm=False, intuition=self.store)
        self.assertIn("confirmed", " ".join(req.assumptions))

    def test_recall_never_overrides_the_user(self):
        req = infer_requirements(
            "fine-tune a vision transformer with 80 GB VRAM",
            allow_llm=False, intuition=self.store)
        self.assertEqual(req.requires["min_vram_gb"], 80)
        self.assertEqual(req.origin["min_vram_gb"], "explicit")

    def test_recall_is_not_re_remembered(self):
        """A guess must not gain weight by being repeated rather than right."""
        infer_requirements("fine-tune a vision transformer",
                           allow_llm=False, intuition=self.store)
        self.assertEqual(len(self.store), 1)


class TestRecallIsReproducible(unittest.TestCase):
    def _store(self):
        return IntuitionStore([
            Intuition(id="li_0001", use_case="train a segmentation model",
                      infers={"min_vram_gb": 24}, taught_by="",
                      recorded_utc=T0.isoformat()),
            # Same tokens as li_0001 on purpose, so overlap ties and the
            # tie-break is the only thing that can order them. With unequal
            # overlap the confirmed-first rule is never exercised and a sort
            # that drops it still passes.
            Intuition(id="li_0002", use_case="model segmentation train",
                      infers={"min_vram_gb": 48}, taught_by="",
                      recorded_utc=(T0 + timedelta(days=1)).isoformat(),
                      confirmed=True),
        ])

    def test_same_store_same_order_every_time(self):
        s = self._store()
        first = [r.id for r in s.recall("train a segmentation model")]
        for _ in range(5):
            self.assertEqual([r.id for r in s.recall("train a segmentation model")],
                             first)

    def test_confirmed_outranks_unconfirmed_at_equal_overlap(self):
        s = self._store()
        hits = s.recall("train a segmentation model")
        self.assertEqual([h.id for h in hits][:2], ["li_0002", "li_0001"])
        # And it is the tie-break doing it, not the overlap.
        from advisor.select.intuition import _tokens as tk
        want = tk("train a segmentation model")
        self.assertEqual(len(want & tk(s.records[0].use_case)),
                         len(want & tk(s.records[1].use_case)))

    def test_a_bad_timestamp_does_not_raise(self):
        s = self._store()
        s.records[0].recorded_utc = "not-a-date"
        self.assertTrue(s.recall("train a segmentation model"))


class TestMatchingIsNotTooCheap(unittest.TestCase):
    def test_stopwords_cannot_make_a_match(self):
        """"I need to run a job on a node" shares only noise with everything."""
        s = IntuitionStore([Intuition(
            id="li_0001", use_case="I need to run a job on a node for 2 hours",
            infers={"min_vram_gb": 80}, taught_by="", recorded_utc=T0.isoformat())])
        self.assertEqual(s.recall("I need to run a job on a node for 4 hours"), [])

    def test_one_shared_word_is_not_a_match(self):
        s = IntuitionStore([Intuition(
            id="li_0001", use_case="segmentation training",
            infers={"min_vram_gb": 80}, taught_by="", recorded_utc=T0.isoformat())])
        self.assertEqual(s.recall("segmentation of customer records"), [])
        self.assertGreaterEqual(MIN_OVERLAP, 2)

    def test_real_overlap_matches(self):
        s = IntuitionStore([Intuition(
            id="li_0001", use_case="segmentation model training",
            infers={"min_vram_gb": 80}, taught_by="", recorded_utc=T0.isoformat())])
        self.assertTrue(s.recall("training a segmentation model"))


class TestPersistence(unittest.TestCase):
    def test_round_trip(self):
        path = tmp()
        s = IntuitionStore()
        infer_requirements("train a diffusion model",
                           client=FakeLLM('{"min_vram_gb": 40}'),
                           allow_llm=True, intuition=s)
        s.save(path)
        again = IntuitionStore.load(path)
        self.assertEqual(len(again), 1)
        self.assertEqual(again.records[0].infers, {"min_vram_gb": 40})

    def test_missing_file_is_an_empty_store_not_an_error(self):
        self.assertEqual(len(IntuitionStore.load(tmp())), 0)

    def test_corrupt_file_degrades_loudly_and_empty(self):
        path = tmp()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not json")
        with self.assertLogs("advisor.select.intuition", level="WARNING"):
            self.assertEqual(len(IntuitionStore.load(path)), 0)

    def test_unknown_fields_are_dropped_not_fatal(self):
        path = tmp()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": "1.0", "intuitions": [
            {"id": "li_0001", "use_case": "x", "infers": {}, "taught_by": "",
             "recorded_utc": T0.isoformat(), "author": "somebody"}]}))
        self.assertEqual(len(IntuitionStore.load(path)), 1)

    def test_asking_twice_recalls_instead_of_re_asking(self):
        """The point of the memory: the second caller reuses the reasoning.

        The model is not consulted again, so the stored value stands until
        somebody confirms or forgets it. That is the intended lifecycle - a
        stored guess is revised deliberately, not by whichever answer the
        model happened to give last.
        """
        s = IntuitionStore()
        first = FakeLLM('{"min_vram_gb": 24}')
        infer_requirements("train a diffusion model", client=first,
                           allow_llm=True, intuition=s)
        second = FakeLLM('{"min_vram_gb": 80}')
        req = infer_requirements("train a diffusion model", client=second,
                                 allow_llm=True, intuition=s)
        self.assertEqual(first.calls, 1)
        self.assertEqual(second.calls, 0, "the model was asked again")
        self.assertEqual(req.origin["min_vram_gb"], "recalled")
        self.assertEqual(len(s), 1)
        self.assertEqual(s.records[0].infers, {"min_vram_gb": 24})

    def test_remembering_the_same_use_case_updates_in_place(self):
        s = IntuitionStore()
        for payload in ('{"min_vram_gb": 24}', '{"min_vram_gb": 80}'):
            req = infer_requirements("train a diffusion model",
                                     client=FakeLLM(payload), allow_llm=True)
            s.remember("train a diffusion model", req)
        self.assertEqual(len(s), 1)
        self.assertEqual(s.records[0].infers, {"min_vram_gb": 80})


class TestCorrectability(unittest.TestCase):
    def test_an_entry_can_be_confirmed_and_forgotten(self):
        """A memory with no way to be wrong is a liability."""
        s = IntuitionStore()
        infer_requirements("train a model", client=FakeLLM('{"min_vram_gb": 24}'),
                           allow_llm=True, intuition=s)
        rid = s.records[0].id
        self.assertFalse(s.records[0].confirmed)
        self.assertTrue(s.confirm(rid))
        self.assertTrue(s.records[0].confirmed)
        self.assertTrue(s.forget(rid))
        self.assertEqual(len(s), 0)

    def test_confirmed_is_never_set_on_the_way_in(self):
        s = IntuitionStore()
        infer_requirements("train a model", client=FakeLLM('{"min_vram_gb": 24}'),
                           allow_llm=True, intuition=s)
        self.assertFalse(s.records[0].confirmed)


class TestNoStoreMeansStateless(unittest.TestCase):
    def test_inference_without_a_store_is_unchanged(self):
        """Injected, never discovered - so a benchmark run stays comparable."""
        a = infer_requirements("fine-tune a 7B model",
                               client=FakeLLM('{"min_vram_gb": 75}'), allow_llm=True)
        b = infer_requirements("fine-tune a 7B model",
                               client=FakeLLM('{"min_vram_gb": 75}'), allow_llm=True)
        self.assertEqual(a.requires, b.requires)
        self.assertEqual(a.origin, b.origin)


if __name__ == "__main__":
    unittest.main()
