"""Reasoner tests with a mocked LLM client (no network)."""
import unittest

from advisor.artifacts.embeddings import HashingEmbedder
from advisor.artifacts.router import RetrievalRouter
from advisor.artifacts.store import ArtifactStore
from advisor.inventory.catalog import CURATED_CATALOG
from advisor.reason.reasoner import Reasoner


class FakeLLM:
    name = "fake"

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return self.response


class TestReasoner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = ArtifactStore(embedder=HashingEmbedder()).build()
        cls.router = RetrievalRouter(cls.store)
        cls.inv = CURATED_CATALOG

    def _retrieval(self, workload):
        return self.router.route(workload)

    def test_llm_json_is_parsed(self):
        payload = (
            'Here you go: {"machine_type": "raspberrypi4-64", "count": 1, '
            '"duration_hours": 4, "architecture": "arm64", '
            '"image": "ghcr.io/x", "device_profiles": ["pi_libcamera"], '
            '"platform_version": 2, "reasoning": "camera"}'
        )
        llm = FakeLLM(payload)
        r = Reasoner(llm_client=llm)
        rec = r.recommend("pi camera photo", [], self.inv, self._retrieval("camera"))
        self.assertEqual(llm.calls, 1)
        self.assertEqual(rec.produced_by, "fake")
        self.assertEqual(rec.machine_type, "raspberrypi4-64")
        self.assertEqual(rec.device_profiles, ["pi_libcamera"])
        # provenance is backfilled from retrieval when the LLM omits it
        self.assertTrue(rec.grounded_by)

    def test_bad_llm_output_falls_back_to_heuristic(self):
        llm = FakeLLM("not json at all")
        r = Reasoner(llm_client=llm, allow_heuristic_fallback=True)
        ret = self._retrieval("pi camera photo")
        rec = r.recommend("pi camera photo", [], self.inv, ret)
        self.assertEqual(rec.produced_by, "heuristic")
        self.assertEqual(rec.machine_type, "raspberrypi4-64")

    def test_no_client_uses_heuristic(self):
        r = Reasoner(llm_client=None)
        ret = self._retrieval("ssh into a device")
        rec = r.recommend("ssh into a device", [], self.inv, ret)
        self.assertEqual(rec.produced_by, "heuristic")
        self.assertEqual(rec.grounded_by, ret.provenance)


if __name__ == "__main__":
    unittest.main()
