"""Validator trap-check tests."""
import unittest

from advisor.availability.base import DeviceAvailability
from advisor.inventory.catalog import CURATED_CATALOG
from advisor.reason.schema import Recommendation
from advisor.validate.checks import validate_recommendation


def _check(report, name):
    return next(c for c in report.checks if c.name == name)


class TestValidator(unittest.TestCase):
    def setUp(self):
        self.inv = CURATED_CATALOG

    def _rec(self, **kw):
        base = dict(
            machine_type="raspberrypi4-64", count=1, duration_hours=3,
            architecture="arm64", image="img", reasoning="r",
        )
        base.update(kw)
        return Recommendation(**base)

    def test_architecture_mismatch_fails(self):
        rec = self._rec(architecture="x86_64")
        report = validate_recommendation(rec, self.inv)
        self.assertFalse(_check(report, "architecture_match").passed)

    def test_architecture_match_passes(self):
        report = validate_recommendation(self._rec(), self.inv)
        self.assertTrue(_check(report, "architecture_match").passed)

    def test_unknown_machine_type_fails(self):
        rec = self._rec(machine_type="does-not-exist")
        report = validate_recommendation(rec, self.inv)
        self.assertFalse(_check(report, "machine_type_exists").passed)
        self.assertFalse(report.passed)

    def test_unknown_device_profile_fails(self):
        rec = self._rec(device_profiles=["not_a_profile"])
        report = validate_recommendation(rec, self.inv)
        self.assertFalse(_check(report, "device_profile_exists").passed)

    def test_jetson_gpu_without_nvidia_runtime_fails(self):
        rec = self._rec(
            machine_type="jetson-nano", architecture="arm64", gpu=True, runtime=None,
        )
        report = validate_recommendation(rec, self.inv)
        self.assertFalse(_check(report, "gpu_runtime_nvidia").passed)

    def test_jetson_gpu_with_nvidia_runtime_passes(self):
        rec = self._rec(
            machine_type="jetson-nano", architecture="arm64", gpu=True,
            runtime="nvidia",
        )
        report = validate_recommendation(rec, self.inv)
        self.assertTrue(_check(report, "gpu_runtime_nvidia").passed)

    def test_free_device_confirmed_passes(self):
        avail = [DeviceAvailability(
            device_uid="iot-rpi4-picam2", machine_type="raspberrypi4-64",
            free_now=True, live_state_known=True,
        )]
        report = validate_recommendation(self._rec(), self.inv, avail)
        self.assertTrue(_check(report, "device_free_in_window").passed)

    def test_reserved_named_device_fails(self):
        avail = [DeviceAvailability(
            device_uid="iot-rpi4-picam2", machine_type="raspberrypi4-64",
            free_now=False, live_state_known=True,
        )]
        rec = self._rec(device_name="iot-rpi4-picam2")
        report = validate_recommendation(rec, self.inv, avail)
        self.assertFalse(_check(report, "device_free_in_window").passed)

    def test_unknown_live_state_fails_conservatively(self):
        # no availability data => cannot confirm free => must fail
        report = validate_recommendation(self._rec(), self.inv, [])
        self.assertFalse(_check(report, "device_free_in_window").passed)

    def test_platform_version_present(self):
        report = validate_recommendation(self._rec(platform_version=2), self.inv)
        self.assertTrue(_check(report, "platform_version_present").passed)


if __name__ == "__main__":
    unittest.main()
