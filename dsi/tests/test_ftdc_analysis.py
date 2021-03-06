"""
Unit tests for `ftdc_analysis.py`
"""

import os
import shutil
import unittest

import six.moves.queue

from dsi.libanalysis import ftdc_analysis
from test_lib.fixture_files import FixtureFiles

FIXTURE_FILES = FixtureFiles()


class TestFtdcAnalysis(unittest.TestCase):
    """
    Test suite
    """

    def test_resource_rules_pass(self):
        """
        FTDC resource sanity checks upon successful test run
        """
        dir_path = FIXTURE_FILES.fixture_file_path("analysis", "core_workloads_reports")
        variant = "linux-standalone"
        constant_values = {"max_thread_level": 64}
        config = {
            "analysis": {
                "rules": {
                    "resource_rules_ftdc_chunk": {
                        "default": [
                            "below_configured_cache_size",
                            "below_configured_oplog_size",
                            "max_connections",
                            "repl_member_state",
                        ]
                    },
                    "resource_rules_ftdc_file": {
                        # FIXME: This test takes 80 seconds. Maybe use smaller ftdc file?
                        "default": []  # ['ftdc_replica_lag_check']
                    },
                }
            }
        }
        observed_result = ftdc_analysis.resource_rules(config, dir_path, variant, constant_values)
        expected_result = {
            "status": "pass",
            "end": 1,
            "log_raw": "\nPassed resource sanity checks.",
            "exit_code": 0,
            "start": 0,
            "test_file": "resource_sanity_checks",
        }
        self.assertEqual(observed_result, expected_result)

    def test_failure_message(self):
        """
        Test formatting of the failure_message() in ftdc_analysis.

        Note: The input file_rule_failures is generated by following lines of code

        path_ftdc_repllag = FIXTURE_FILES.fixture_file_path('test_repllag')
        path_ftdc = os.path.join(path_ftdc_repllag, 'metrics.mongod.0')
        perf_json = os.path.join(path_ftdc_repllag, 'perf.json')
        test_times = util.get_test_times(perf_json)
        MS = 1000
        output = ftdc_analysis._ftdc_file_rule_evaluation(
            path_ftdc, "sys-perf", "linux-3-node-replSet", test_times)
        import pprint
        pprint.pprint(output)
        self.assertEqual(output, "")
        """
        rule_info = [
            {
                "additional": {
                    "lag end threshold (s)": 2.0,
                    "lag start threshold (s)": 15.0,
                    "primary member": "0",
                },
                "members": {
                    "1": {
                        "compared_values": [
                            (16.0, "2017-05-31 16:54:42Z", 129.0, "2017-05-31 16:54:42Z", 120.0),
                            (17.0, "2017-05-31 16:59:23Z", 104.0, "2017-05-31 16:59:26Z", 99.0),
                            (16.0, "2017-05-31 17:04:33Z", 117.0, "2017-05-31 17:04:34Z", 110.0),
                            (16.0, "2017-05-31 17:09:13Z", 93.0, "2017-05-31 17:09:32Z", 12.0),
                        ],
                        "labels": (
                            "start value (s)",
                            "max time",
                            "max value (s)",
                            "end time",
                            "end value (s)",
                        ),
                        "report_all_values": True,
                        "times": [1496248949000, 1496249726000, 1496250019000, 1496250331000],
                    },
                    "2": {
                        "compared_values": [
                            (16.0, "2017-05-31 16:54:03Z", 90.0, "2017-05-31 16:54:04Z", 82.0),
                            (16.0, "2017-05-31 16:58:53Z", 76.0, "2017-05-31 16:59:00Z", 72.0),
                            (16.0, "2017-05-31 17:03:53Z", 80.0, "2017-05-31 17:03:58Z", 77.0),
                            (16.0, "2017-05-31 17:08:53Z", 70.0, "2017-05-31 17:08:54Z", 62.0),
                        ],
                        "labels": (
                            "start value (s)",
                            "max time",
                            "max value (s)",
                            "end time",
                            "end value (s)",
                        ),
                        "report_all_values": True,
                        "times": [1496248967000, 1496249735000, 1496250027000, 1496250339000],
                    },
                },
            }
        ]
        file_rule_failures = {"ftdc_replica_lag_check": rule_info}

        test_dir = FIXTURE_FILES.fixture_file_path("analysis", "test_repllag")
        ok_file = os.path.join(test_dir, "failure_message.txt.ok")
        with open(ok_file) as ok_file_handle:
            expected = ok_file_handle.read()

        log_raw = ftdc_analysis._ftdc_log_raw(file_rule_failures, {}, 1000)
        self.assertEqual(log_raw, expected)

    def test__get_ftdc_file_path(self):
        """
        Test that a given directory is correctly searched for diagnostic.data directories and that
        the ouput is of the correct format
        """
        dir_path = "test_reports"
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
        directory_structure = {
            "test_reports": {
                "graphs": {"test_false.txt": None},
                "fio": {
                    "mongod.0": {
                        "diagnostic.data": {
                            "metrics.2019-09-09T17-24-55Z-00000": None,
                            "metrics.2019-09-09T17-24-25Z-00000": None,
                        },
                        "mongod.log": None,
                    },
                    "mongod.1": {"diagnostic.data": {}, "mongod.log": None},
                },
                "test_false.txt": None,
                "iperf": {
                    "db-correctness": {"db-hash-check": {"test_false.txt": None}},
                    "mongod.0": {
                        "diagnostic.data": {"metrics.2019-09-09T17-24-55Z-00000": None},
                        "mongod.log": None,
                    },
                    "mongod.1": {
                        "diagnostic.data": {"metrics.2019-09-09T17-24-55Z-00000": None},
                        "mongod.log": None,
                    },
                    "test_false.txt": None,
                },
                "_post_task": {"mongod.0": {"mdiag.sh": None}, "mongod.1": {"mdiag.sh": None}},
            }
        }
        curr_dir = directory_structure[dir_path]
        queue = six.moves.queue.Queue()
        queue.put((dir_path, curr_dir))
        while not queue.empty():
            path, curr_dir = queue.get()
            os.mkdir(path)
            for sub_dir in curr_dir:
                if curr_dir[sub_dir] is None:
                    with open(os.path.join(path, sub_dir), "w") as handle:
                        handle.write("test")
                else:
                    queue.put((os.path.join(path, sub_dir), curr_dir[sub_dir]))

        ftdc_metric_paths = ftdc_analysis._get_ftdc_file_paths(dir_path)
        expected_result = {
            "mongod.0": {
                "iperf": os.path.abspath(
                    "test_reports/iperf/mongod.0/diagnostic.data/metrics.2019-09-09T17-24-55Z-00000"
                ),
                "fio": os.path.abspath(
                    "test_reports/fio/mongod.0/diagnostic.data/metrics.2019-09-09T17-24-55Z-00000"
                ),
            },
            "mongod.1": {
                "iperf": os.path.abspath(
                    "test_reports/iperf/mongod.1/diagnostic.data/metrics.2019-09-09T17-24-55Z-00000"
                )
            },
        }
        self.assertEqual(ftdc_metric_paths, expected_result)
        shutil.rmtree(dir_path)


if __name__ == "__main__":
    unittest.main()
