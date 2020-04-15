"""Tests for dsi/common/canaries.py"""


import unittest

from dsi.common import canaries


class CanariesTestCase(unittest.TestCase):
    def setUp(self):
        self.get_config = lambda should_run="": {
            "bootstrap": {"canaries": should_run},
            "test_control": {
                "numactl_prefix_for_workload_client": "dummy_numactl_prefix",
                "common_fio_config": "dummy_fio_config",
            },
            "mongodb_setup": {
                "meta": {
                    "hostname": "dummy_hostname",
                    "port": 27017,
                    "is_sharded": False,
                    "is_replset": False,
                    "shell_ssl_options": "dummy_shell_ssl_options",
                },
            },
        }

    def test_cpu_noise_as_dict(self):
        observed = canaries.get_canary("cpu_noise", self.get_config()).as_dict()
        expected = {
            "id": "cpu_noise",
            "type": "cpu_noise",
            "cmd": "cd workloads && dummy_numactl_prefix ./run_workloads.py -c ../workloads.yml",
            "config_filename": "workloads.yml",
            "output_files": ["workloads/workload_timestamps.csv"],
            "workload_config": {
                "tests": {"default": ["cpu_noise"]},
                "target": "dummy_hostname",
                "port": 27017,
                "sharded": False,
                "replica": False,
                "shell_ssl_options": "dummy_shell_ssl_options",
            },
            "skip_validate": True,
        }
        self.assertEqual(expected, observed)

    def test_fio_as_dict(self):
        observed = canaries.get_canary("fio", self.get_config()).as_dict()
        expected = {
            "id": "fio",
            "type": "fio",
            "cmd": "dummy_numactl_prefix ./fio-test.sh dummy_hostname",
            "config_filename": "fio.ini",
            "output_files": ["fio.json", "fio_results.tgz"],
            "workload_config": "dummy_fio_config",
            "skip_validate": True,
        }
        self.assertEqual(expected, observed)

    def test_iperf_as_dict(self):
        observed = canaries.get_canary("iperf", self.get_config()).as_dict()
        expected = {
            "id": "iperf",
            "type": "iperf",
            "cmd": "dummy_numactl_prefix ./iperf-test.sh dummy_hostname",
            "output_files": ["iperf.json"],
            "skip_validate": True,
        }
        self.assertEqual(expected, observed)

    def test_all_canaries_are_returned(self):
        canary_tests = canaries.get_canaries(self.get_config())
        observed = []
        for test in canary_tests:
            observed.append(test["type"])
        expected = canaries.CANARY_TYPES
        self.assertEqual(expected, observed)

    def test_no_canaries_are_returned(self):
        observed = canaries.get_canaries(self.get_config(should_run="none"))
        expected = []
        self.assertEqual(expected, observed)


if __name__ == "__main__":
    unittest.main()
