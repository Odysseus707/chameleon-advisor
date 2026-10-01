"""The artifact cross-check.

The check must fire on evidence and stay silent without it. The failure mode
it was built to avoid is loud and systematic: the five most capable types on
the testbed are named by no artifact at all, so a naive "the corpus does not
mention this" check condemns every high-end GPU recommendation.
"""
import unittest

from advisor.artifacts.registry import ArtifactMeta
from advisor.inventory.catalog import DeviceType, capability_table_types
from advisor.select.crosscheck import crosscheck


def dev(name, *, accel="none", cc=None, micro="", ram=None):
    return DeviceType(machine_type=name, architecture="x86_64",
                      gpu=accel != "none", accelerator=accel, cuda_compute=cc,
                      microarchitecture=micro, ram_gb=ram,
                      sites=["CHI@TACC"], api_family="baremetal")


def art(aid, tags, node_types):
    return ArtifactMeta(artifact_id=aid, repo="", title="", machine_types=[],
                        device_profiles=[], image="", architecture="",
                        gpu=False, tags=list(tags), node_types=list(node_types),
                        wing="chameleon", api_family="baremetal")


CAT = [dev("gpu_h100", accel="cuda", cc=9.0),
       dev("gpu_rtx_6000", accel="cuda", cc=7.5, ram=128),
       dev("compute_skylake", micro="Intel Skylake", ram=188)]


class TestSilenceIsNotEvidence(unittest.TestCase):
    def test_no_comparable_artifact_means_no_note(self):
        r = crosscheck("train a diffusion model", "gpu_h100", CAT,
                       artifacts=[art("A1", ["web hosting"], ["compute_skylake"])])
        self.assertFalse(r.fired)
        self.assertFalse(r.had_evidence)
        self.assertEqual(r.note, "")

    def test_an_artifact_naming_no_placeable_hardware_is_not_comparable(self):
        r = crosscheck("train a model", "gpu_h100", CAT,
                       artifacts=[art("A1", ["train", "model"], ["not_a_real_type"])])
        self.assertFalse(r.had_evidence)

    def test_uncovered_hardware_on_the_real_corpus_stays_silent(self):
        """fpga has covered_by == [] and must not be condemned for it."""
        r = crosscheck("synthesise an fpga bitstream", "fpga",
                       capability_table_types())
        self.assertFalse(r.fired)

    def test_had_evidence_is_distinct_from_fired(self):
        """Silence is not agreement, and must not be reported as endorsement."""
        r = crosscheck("nothing in particular", "gpu_h100", CAT, artifacts=[])
        self.assertFalse(r.had_evidence)
        self.assertFalse(r.fired)


class TestFiresOnRealDisagreement(unittest.TestCase):
    def test_tier_disagreement_within_a_class(self):
        """The user's scenario: artifacts used less, we reached higher."""
        arts = [art("A1", ["train", "model"], ["gpu_rtx_6000"]),
                art("A2", ["train", "model"], ["gpu_rtx_6000"])]
        r = crosscheck("train model", "gpu_h100", CAT, artifacts=arts)
        self.assertTrue(r.fired)
        self.assertEqual(r.kind, "tier_disagreement")
        self.assertIn("gpu_rtx_6000", r.note)

    def test_class_disagreement_when_nobody_used_an_accelerator(self):
        arts = [art("A1", ["parse", "logs"], ["compute_skylake"])]
        r = crosscheck("parse logs", "gpu_h100", CAT, artifacts=arts)
        self.assertTrue(r.fired)
        self.assertEqual(r.kind, "class_disagreement")

    def test_the_note_carries_its_own_caveat(self):
        """It can be wrong even when it fires, and must say so."""
        arts = [art("A1", ["train", "model"], ["gpu_rtx_6000"])]
        note = crosscheck("train model", "gpu_h100", CAT, artifacts=arts).note
        self.assertTrue("predates" in note or "free at the time" in note)


class TestAgreementIsNotDisagreement(unittest.TestCase):
    def test_an_artifact_using_exactly_our_pick_is_agreement(self):
        """Was a real bug: our own type was excluded from the comparison, so
        the strongest possible agreement read as disagreement."""
        arts = [art("A1", ["train", "model"], ["gpu_h100", "compute_skylake"])]
        r = crosscheck("train model", "gpu_h100", CAT, artifacts=arts)
        self.assertTrue(r.had_evidence)
        self.assertFalse(r.fired)

    def test_one_artifact_in_our_class_suppresses_class_disagreement(self):
        # A notebook artifact naming both a GPU and a CPU node is not evidence
        # against choosing the GPU.
        arts = [art("A1", ["train", "model"], ["compute_skylake"]),
                art("A2", ["train", "model"], ["gpu_rtx_6000"])]
        r = crosscheck("train model", "gpu_rtx_6000", CAT, artifacts=arts)
        self.assertNotEqual(r.kind, "class_disagreement")

    def test_mixed_tiers_do_not_fire(self):
        # Only fires when EVERY comparable artifact reached lower.
        arts = [art("A1", ["train", "model"], ["gpu_rtx_6000"]),
                art("A2", ["train", "model"], ["gpu_h100"])]
        r = crosscheck("train model", "gpu_h100", CAT, artifacts=arts)
        self.assertFalse(r.fired)


class TestMatchingIsNotTooCheap(unittest.TestCase):
    def test_a_single_common_token_is_not_comparability(self):
        """"model" alone would make most of the corpus comparable to most of
        the corpus, and a check that always fires says nothing."""
        arts = [art("A1", ["model"], ["compute_skylake"])]
        r = crosscheck("model", "gpu_h100", CAT, artifacts=arts)
        self.assertFalse(r.had_evidence)

    def test_a_whole_multiword_tag_is_enough(self):
        arts = [art("A1", ["machine learning"], ["compute_skylake"])]
        r = crosscheck("a machine learning job", "gpu_h100", CAT, artifacts=arts)
        self.assertTrue(r.had_evidence)

    def test_edge_artifacts_are_excluded(self):
        edge = ArtifactMeta(artifact_id="edge_x", repo="", title="",
                            machine_types=[], device_profiles=[], image="",
                            architecture="", gpu=False,
                            tags=["train", "model"],
                            node_types=["compute_skylake"], wing="edge")
        r = crosscheck("train model", "gpu_h100", CAT, artifacts=[edge])
        self.assertFalse(r.had_evidence)


class TestNeverAVeto(unittest.TestCase):
    def test_result_carries_no_power_to_change_the_pick(self):
        arts = [art("A1", ["train", "model"], ["gpu_rtx_6000"])]
        r = crosscheck("train model", "gpu_h100", CAT, artifacts=arts)
        self.assertEqual(r.our_type, "gpu_h100")   # unchanged by firing
        self.assertTrue(hasattr(r, "note"))
        self.assertFalse(hasattr(r, "replacement"))


if __name__ == "__main__":
    unittest.main()
