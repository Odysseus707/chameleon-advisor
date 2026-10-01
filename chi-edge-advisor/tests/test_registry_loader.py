"""Registry loader + IDF tag weighting.

Guards the two things that widening the registry from 5 artifacts to 95 can
break silently: the frozen edge population, and the meaning of a tag score.
"""
import math
import unittest

from advisor.artifacts.embeddings import HashingEmbedder
from advisor.artifacts.registry import (ARTIFACTS, ARTIFACTS_BY_ID,
                                        CORPUS_ARTIFACTS, EDGE_ARTIFACTS,
                                        REAL_FLAVORS, ArtifactMeta)
from advisor.artifacts.router import RetrievalRouter
from advisor.artifacts.store import ArtifactStore
from advisor.artifacts.tree import RouterTree


class TestLoader(unittest.TestCase):
    def test_both_populations_present(self):
        self.assertEqual(len(EDGE_ARTIFACTS), 5)
        self.assertEqual(len(CORPUS_ARTIFACTS), 90)
        self.assertEqual(len(ARTIFACTS_BY_ID), 95)

    def test_edge_entries_are_untouched(self):
        # The five feed already-collected answers. Their ids and tags are the
        # routing signal those answers were produced against.
        self.assertEqual(
            [a.artifact_id for a in ARTIFACTS[:5]],
            ["edge_ssh_image", "edge-picamera-image", "edge_sensehat_image",
             "edge-cpu-inference", "serve-edge-chi"],
        )
        for a in EDGE_ARTIFACTS:
            self.assertEqual(a.wing, "edge")
            self.assertEqual(a.api_family, "edge")
            self.assertEqual(a.branch_sites(), ["CHI@Edge"])

    def test_corpus_artifacts_never_join_the_edge_branch(self):
        for a in CORPUS_ARTIFACTS:
            self.assertNotIn("CHI@Edge", a.branch_sites())
        # ...but they keep the other sites they observed.
        a52 = ARTIFACTS_BY_ID["A52"]
        self.assertIn("CHI@Edge", a52.sites)          # observed
        self.assertNotIn("CHI@Edge", a52.branch_sites())  # not routed there
        self.assertIn("KVM@TACC", a52.branch_sites())

    def test_siteless_artifacts_join_no_branch(self):
        # Rather than being defaulted into a site, which would be a guess.
        siteless = [a for a in CORPUS_ARTIFACTS if not a.sites]
        self.assertTrue(siteless)
        for a in siteless:
            self.assertEqual(a.branch_sites(), [])

    def test_flavor_pollution_is_filtered(self):
        # flavors_observed is produced by a regex that also catches filenames
        # and attribute lookups. None of that may reach routing as a flavor.
        for a in CORPUS_ARTIFACTS:
            for f in a.flavors:
                self.assertIn(f, REAL_FLAVORS)
        self.assertIn("g1.h100", ARTIFACTS_BY_ID["A30"].flavors)
        self.assertNotIn("gpu.ipynb", ARTIFACTS_BY_ID["A30"].flavors)

    def test_node_types_are_capability_table_members(self):
        from advisor.artifacts.registry import _known_node_types
        known = _known_node_types()
        self.assertTrue(known, "capability table must be readable for this test")
        for a in CORPUS_ARTIFACTS:
            for t in a.node_types:
                self.assertIn(t, known)

    def test_derived_api_family_is_labelled(self):
        # 25 records say "none" and 3 "mixed"; those become a derived value and
        # must never be readable as an observed one.
        for a in CORPUS_ARTIFACTS:
            self.assertIn(a.api_family, {"baremetal", "kvm"})
            if a.api_family_source == "derived_from_site":
                primary = a.site.upper()
                self.assertEqual(a.api_family,
                                 "kvm" if primary.startswith("KVM@") else "baremetal")

    def test_grounding_resolves_for_every_corpus_artifact(self):
        for a in CORPUS_ARTIFACTS:
            self.assertIsNotNone(a.grounding_file, a.artifact_id)
            self.assertTrue(a.grounding_file.is_file())


class TestIdfWeighting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = ArtifactStore(embedder=HashingEmbedder()).build()
        cls.router = RetrievalRouter(cls.store)

    def test_common_tag_is_discounted(self):
        """The property, not one tag's name.

        This asserted on "bare-metal", which reached the vocabulary only via
        the FALLBACK path on the 68 unauthored artifacts. Authoring all 90
        removed that path and the test raised KeyError instead of failing -
        a test of a tag rather than of the weighting it was written to check.
        """
        idf = self.router._idf(self.router.pool)
        self.assertTrue(idf, "no tags in the pool at all")
        # Whatever the most widely shared tag turns out to be, it must be
        # discounted below a tag that appears on a single artifact.
        df = {}
        for meta in self.router.pool.values():
            for tag in set(meta.tags):
                df[tag] = df.get(tag, 0) + 1
        commonest = max(df, key=lambda t: df[t])
        rarest = min(df, key=lambda t: df[t])
        self.assertGreater(df[commonest], df[rarest])
        self.assertLess(idf[commonest], idf[rarest])

    def test_idf_never_negative(self):
        # A tag on every artifact contributes nothing; it must not penalise.
        pool = {a.artifact_id: a for a in EDGE_ARTIFACTS}
        everywhere = ArtifactMeta(
            artifact_id="_t", repo="", title="", machine_types=[],
            device_profiles=[], image="", architecture="", gpu=False,
            tags=["ubiquitous"])
        pool = {**{k: v for k, v in pool.items()}, "_t": everywhere}
        for m in pool.values():
            m_tags = list(m.tags)
            if "ubiquitous" not in m_tags:
                m.tags = m_tags + ["ubiquitous"]
        try:
            idf = RetrievalRouter(self.store)._idf(pool)
            self.assertGreaterEqual(idf["ubiquitous"], 0.0)
        finally:
            for m in pool.values():
                m.tags = [t for t in m.tags if t != "ubiquitous"]

    def test_idf_is_scoped_to_the_pool_it_was_asked_about(self):
        # P3: a cache keyed by nothing grades the second caller against the
        # first caller's table. These two pools must not share an answer.
        r = RetrievalRouter(self.store)
        edge = {a.artifact_id: a for a in EDGE_ARTIFACTS}
        big = r._idf(r.pool)
        small = r._idf(edge)
        self.assertIsNot(big, small)
        self.assertNotEqual(set(big), set(small))
        # and asking again returns the right one, not the most recent one
        self.assertEqual(r._idf(r.pool), big)

    def test_classify_actually_applies_the_weighting(self):
        """A rare-tag match must outscore a common-tag match.

        Unweighted these tie at 1.0 apiece, which is the whole defect: an
        artifact matching only `bare-metal` scored the same as one matching
        its own name. Without this test, deleting the idf multiplier from
        classify() passes the entire suite.
        """
        def meta(aid, tags):
            return ArtifactMeta(artifact_id=aid, repo="", title="",
                                machine_types=[], device_profiles=[], image="",
                                architecture="", gpu=False, tags=tags)

        pool = {"rare_one": meta("rare_one", ["kryptonite"])}
        for i in range(5):                     # 5 of 10 share "widespread"
            pool[f"common{i}"] = meta(f"common{i}", ["widespread"])
        for i in range(4):                     # filler, so neither tag is
            pool[f"other{i}"] = meta(f"other{i}", [f"unrelated{i}"])

        scores = RetrievalRouter(self.store).classify("widespread kryptonite",
                                                      pool=pool)
        self.assertGreater(scores["rare_one"], scores["common0"])
        self.assertGreater(scores["common0"], 0.0)   # still a real match

    def test_scores_are_pool_relative(self):
        q = "reserve a bare metal node"
        wide = self.router.classify(q)
        edge_pool = {a.artifact_id: a for a in EDGE_ARTIFACTS}
        narrow = self.router.classify(q, pool=edge_pool)
        self.assertEqual(set(narrow), set(edge_pool))
        self.assertEqual(len(wide), 95)


class TestRouterNarrowsItselfToTheIndex(unittest.TestCase):
    """An unscoped router may not outrun the index it was handed.

    Selecting an artifact whose chunks are absent is never useful: search
    returns nothing under that id and the caller gets an answer with empty
    grounding that raises nothing and logs nothing. This has happened to three
    separate callers of RetrievalRouter - the benchmark driver, the CLI, and
    the docs chatbot - each time because the registry grew to 95 artifacts
    while a persisted index stayed at 5. Fixing it per caller is how it got to
    three; the guard belongs here.
    """

    @classmethod
    def setUpClass(cls):
        cls.narrow = ArtifactStore(embedder=HashingEmbedder()).build(
            artifacts=EDGE_ARTIFACTS)
        cls.full = ArtifactStore(embedder=HashingEmbedder()).build()

    def test_narrow_index_narrows_the_pool(self):
        r = RetrievalRouter(self.narrow)
        self.assertEqual(r.pool_source, "store")
        self.assertEqual(set(r.pool), set(self.narrow.artifact_ids()))

    def test_it_says_so(self):
        with self.assertLogs("advisor.artifacts.router", level="WARNING") as cm:
            RetrievalRouter(self.narrow)
        self.assertIn("5 of the registry's 95", "\n".join(cm.output))

    def test_full_index_keeps_the_whole_registry(self):
        r = RetrievalRouter(self.full)
        self.assertEqual(r.pool_source, "registry")
        self.assertEqual(len(r.pool), len(ARTIFACTS_BY_ID))

    def test_an_explicit_pool_is_never_second_guessed(self):
        wanted = ["edge_ssh_image"]
        r = RetrievalRouter(self.full, artifacts=wanted)
        self.assertEqual(r.pool_source, "explicit")
        self.assertEqual(set(r.pool), set(wanted))

    def test_nothing_outside_the_index_is_ever_selected(self):
        r = RetrievalRouter(self.narrow)
        servable = set(self.narrow.artifact_ids())
        for q in ("how do I run a container on a bare metal node",
                  "can I use a container with docker on CHI@TACC",
                  "how do I attach a camera to my instance"):
            with self.subTest(question=q):
                result = r.route(q)
                self.assertTrue(set(result.selected_artifact_ids) <= servable)
                self.assertTrue(result.chunks)

    def test_an_unbuilt_store_is_left_alone(self):
        """Nothing to compare against yet, so the registry is the only answer.

        Narrowing to an empty index here would leave the router unable to
        select anything at all, which is worse than the hazard.
        """
        r = RetrievalRouter(ArtifactStore(embedder=HashingEmbedder()))
        self.assertEqual(r.pool_source, "registry")
        self.assertEqual(len(r.pool), len(ARTIFACTS_BY_ID))

    def test_the_tree_narrows_its_branches_too(self):
        tree = RouterTree(self.narrow)
        servable = set(self.narrow.artifact_ids())
        for site, metas in tree.branches.items():
            for m in metas:
                self.assertIn(m.artifact_id, servable, site)


if __name__ == "__main__":
    unittest.main()
