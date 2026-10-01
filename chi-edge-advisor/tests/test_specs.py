"""Spec inference: working out what a job needs, and what that entitles us to.

The central rule under test is that a requirement we GUESSED may order the
candidates but may never remove one. A guess that eliminates hardware can turn
a perfectly answerable request into a refusal the user never sees the inside of.
"""
import unittest

from advisor.availability.base import DeviceAvailability
from advisor.inventory.catalog import DeviceType
from advisor.select.ladder import Request, meets, select
from advisor.select.specs import (FLEET_TIERS, InferredRequirement, extract,
                                  infer_requirements, round_up_to_fleet)


class FakeLLM:
    """Returns a canned JSON body; records what it was asked."""

    name = "fake"

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        return self.payload


def dev(name, *, accel="none", cc=None, ram=None, vcpus=None, vram=None):
    return DeviceType(machine_type=name, architecture="x86_64",
                      gpu=accel != "none", accelerator=accel, cuda_compute=cc,
                      ram_gb=ram, vcpus=vcpus, vram_gb_per_gpu=vram,
                      sites=["CHI@TACC"], api_family="baremetal", node_count=4)


def hosts(mtype, free=2):
    return [DeviceAvailability(device_uid=f"{mtype}-{i}", device_name=f"{mtype}-{i}",
                               machine_type=mtype, site="CHI@TACC",
                               free_now=True, reservable=True)
            for i in range(free)]


class TestExplicitExtraction(unittest.TestCase):
    def test_stated_memory_becomes_a_floor(self):
        r = extract("an in-memory dataset job needing 180 GB or more")
        self.assertEqual(r.requires["min_ram_gb"], 180)
        self.assertEqual(r.origin["min_ram_gb"], "explicit")

    def test_gpu_memory_does_not_become_a_system_memory_floor(self):
        """"24 GB of GPU memory" contains the word "memory".

        A RAM pattern reading the same span invents a 24 GB system-memory
        requirement out of punctuation.
        """
        r = extract("serve inference, 24 GB of GPU memory should do")
        self.assertEqual(r.requires.get("min_vram_gb"), 24)
        self.assertNotIn("min_ram_gb", r.requires)

    def test_both_when_both_are_stated(self):
        r = extract("a job with 80 GB VRAM and 256 GB of system RAM")
        self.assertEqual(r.requires["min_vram_gb"], 80)
        self.assertEqual(r.requires["min_ram_gb"], 256)

    def test_tensor_cores_imply_cuda(self):
        r = extract("fine-tune a vision model with tensor cores")
        self.assertEqual(r.requires["min_tensor_cores"], 1)
        self.assertEqual(r.requires["accelerator"], "cuda")

    def test_port_target_wins_over_the_thing_being_ported_from(self):
        """"a ROCm/HIP port of an existing CUDA kernel" needs ROCm."""
        self.assertEqual(extract("run a ROCm/HIP port of an existing CUDA "
                                 "kernel").requires["accelerator"], "rocm")

    def test_fpga_and_oneapi_are_recognised(self):
        self.assertEqual(
            extract("synthesise an FPGA bitstream").requires["accelerator"], "fpga")
        self.assertEqual(
            extract("a SYCL kernel via oneAPI").requires["accelerator"], "oneapi")

    def test_node_count_is_read_but_is_not_a_requirement(self):
        r = extract("a 3-node MPI job across identical hardware")
        self.assertEqual(r.count, 3)
        self.assertEqual(r.requires, {})

    def test_nothing_stated_yields_nothing(self):
        r = extract("just give me a node")
        self.assertEqual(r.requires, {})
        self.assertIn("no hardware requirement", r.describe())

    def test_extraction_needs_no_network(self):
        # No client, no env var, no import of the llm module.
        self.assertEqual(infer_requirements("180 GB of RAM please",
                                            allow_llm=False).requires,
                         {"min_ram_gb": 180})


class TestErringUpward(unittest.TestCase):
    def test_rounds_to_a_size_the_fleet_actually_has(self):
        self.assertEqual(round_up_to_fleet("min_vram_gb", 45), 48)
        self.assertEqual(round_up_to_fleet("min_cuda_compute", 6.5), 7.0)

    def test_an_exact_rung_is_left_alone(self):
        self.assertEqual(round_up_to_fleet("min_vram_gb", 40), 40)

    def test_a_requirement_bigger_than_the_fleet_is_not_capped(self):
        """Capping it would turn "nothing here is big enough" into a
        recommendation for the biggest node, which is a different answer."""
        self.assertEqual(round_up_to_fleet("min_ram_gb", 999), 999)
        self.assertGreater(999, max(FLEET_TIERS["min_ram_gb"]))

    def test_llm_magnitude_is_rounded_up_and_labelled(self):
        llm = FakeLLM('{"min_vram_gb": 41, "why": "7B in fp16"}')
        r = infer_requirements("fine-tune a 7B model", client=llm, allow_llm=True)
        self.assertEqual(r.requires["min_vram_gb"], 48)
        self.assertEqual(r.origin["min_vram_gb"], "rounded_up")
        self.assertTrue(r.rounded_up)
        self.assertTrue(any("raised from" in a for a in r.assumptions))


class TestInferenceMayNotOverrideTheUser(unittest.TestCase):
    def test_stated_value_survives(self):
        llm = FakeLLM('{"min_ram_gb": 512}')
        r = infer_requirements("a job needing 180 GB or more of RAM",
                               client=llm, allow_llm=True)
        self.assertEqual(r.requires["min_ram_gb"], 180)
        self.assertEqual(r.origin["min_ram_gb"], "explicit")

    def test_llm_off_by_default(self):
        llm = FakeLLM('{"min_ram_gb": 512}')
        r = infer_requirements("some workload", client=llm)   # env unset
        self.assertEqual(llm.calls, [])
        self.assertEqual(r.requires, {})

    def test_unreachable_model_is_not_fatal(self):
        class Broken:
            name = "broken"

            def complete(self, s, u):
                raise RuntimeError("no route to host")

        r = infer_requirements("fine-tune a model", client=Broken(), allow_llm=True)
        self.assertEqual(r.requires, {})

    def test_malformed_json_is_not_fatal(self):
        r = infer_requirements("x", client=FakeLLM("I think you want an H100"),
                               allow_llm=True)
        self.assertEqual(r.requires, {})

    def test_accelerator_none_is_not_a_filter(self):
        """"no accelerator needed" must not become accelerator=='none'.

        That would exclude every GPU node from a CPU job which would run
        perfectly well on one.
        """
        r = infer_requirements("count some words",
                               client=FakeLLM('{"accelerator": "none"}'),
                               allow_llm=True)
        self.assertNotIn("accelerator", r.requires)


class TestHardVersusSoft(unittest.TestCase):
    def test_explicit_magnitudes_are_hard(self):
        r = extract("180 GB of RAM")
        self.assertIn("min_ram_gb", r.hard())
        self.assertEqual(r.soft(), {})

    def test_inferred_magnitudes_are_soft(self):
        r = infer_requirements("fine-tune a model",
                               client=FakeLLM('{"min_vram_gb": 80}'),
                               allow_llm=True)
        self.assertEqual(r.soft(), {"min_vram_gb": 80})
        self.assertEqual(r.hard(), {})

    def test_inferred_accelerator_is_still_hard(self):
        """A wrong class does not make the job slow, it makes it not run."""
        r = infer_requirements(
            "train a model",
            client=FakeLLM('{"accelerator": "cuda", "min_vram_gb": 80}'),
            allow_llm=True)
        self.assertEqual(r.hard(), {"accelerator": "cuda"})
        self.assertEqual(r.soft(), {"min_vram_gb": 80})


class TestSoftRequirementsRankButNeverRefuse(unittest.TestCase):
    CAT = [dev("gpu_small", accel="cuda", cc=6.0, vram=16),
           dev("gpu_big", accel="cuda", cc=8.0, vram=80)]

    def test_unmet_guess_still_returns_hardware(self):
        """The defining test. Nothing has 80 GB; the answer is not a refusal."""
        cat = [dev("gpu_small", accel="cuda", cc=6.0, vram=16)]
        r = select(cat, hosts("gpu_small"),
                   Request(site="CHI@TACC", requires={"accelerator": "cuda"},
                           soft_requires={"min_vram_gb": 80},
                           assumptions=["assumed 80 GB VRAM"]))
        self.assertEqual(r.rung.name, "free_now")
        self.assertEqual(r.chosen.machine_type, "gpu_small")
        self.assertFalse(r.chosen.meets_soft)
        self.assertIn("VRAM", r.chosen.soft_gap)

    def test_the_same_guess_as_a_hard_filter_would_have_refused(self):
        # Shows the two paths genuinely differ, so the distinction is load-bearing.
        cat = [dev("gpu_small", accel="cuda", cc=6.0, vram=16)]
        hard = select(cat, hosts("gpu_small"),
                      Request(site="CHI@TACC",
                              requires={"accelerator": "cuda", "min_vram_gb": 80}))
        self.assertEqual(hard.rung.name, "infeasible_capability")

    def test_meeting_the_guess_ranks_higher(self):
        av = hosts("gpu_small") + hosts("gpu_big")
        r = select(self.CAT, av,
                   Request(site="CHI@TACC", requires={"accelerator": "cuda"},
                           soft_requires={"min_vram_gb": 80}))
        self.assertEqual(r.chosen.machine_type, "gpu_big")
        self.assertTrue(r.chosen.meets_soft)

    def test_no_soft_requirements_leaves_ordering_untouched(self):
        """With nothing inferred the sort key is constant and the order is the
        rule the benchmark golds were solved with."""
        av = hosts("gpu_small", free=5) + hosts("gpu_big", free=1)
        r = select(self.CAT, av, Request(site="CHI@TACC"))
        self.assertIsNone(r.ranked[0].meets_soft)
        self.assertEqual(r.chosen.machine_type, "gpu_small")   # free count wins


class TestVramFilter(unittest.TestCase):
    def test_vram_is_per_gpu_not_summed(self):
        spec = dev("g", accel="cuda", cc=7.0, vram=16)
        self.assertIsNotNone(meets(spec, {"min_vram_gb": 80}))
        self.assertIsNone(meets(spec, {"min_vram_gb": 16}))

    def test_null_vram_fails_a_minimum(self):
        """R4 again: unmeasured VRAM is not enough VRAM."""
        spec = dev("g", accel="cuda", cc=7.0, vram=None)
        self.assertIsNotNone(meets(spec, {"min_vram_gb": 8}))


if __name__ == "__main__":
    unittest.main()
