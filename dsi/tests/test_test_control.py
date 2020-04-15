"""
Tests for dsi/test_control.py
"""

import os
import shutil
import subprocess
import tempfile
import unittest

from mock import patch, Mock
from testfixtures import LogCapture

from dsi.common import host_utils
from dsi.common.command_runner import print_trace
from dsi.common.config import ConfigDict
from dsi.common.remote_host import RemoteHost
from dsi.common.utils import mkdir_p
from dsi.test_control import copy_timeseries
from dsi.test_control import run_test
from dsi.test_control import run_tests
from test_lib.fixture_files import FixtureFiles

FIXTURE_FILES = FixtureFiles()


class RunTestTestCase(unittest.TestCase):
    """
    Test for test_control.run_test()
    """

    def setUp(self):
        self.test_config = {
            "id": "dummy_test",
            "type": "dummy_test_kind",
            "cmd": "dummy shell command",
        }

        self.god_config = {
            "test_control": {
                "mongodb_url": "dummy_mongodb_url",
                "is_production": True,
                "timeouts": {"no_output_ms": 100},
                "numactl_prefix_for_workload_client": "dummy_numa_prefix",
                "out": {"exit_codes": {}},
            }
        }
        # Change to a temporary directory for this test because the report
        # file is generated as a relative path to the CWD.
        self.original_cwd = os.getcwd()
        self.tempdir = tempfile.mkdtemp()
        os.chdir(self.tempdir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tempdir)

    @patch("dsi.common.command_runner.make_workload_runner_host")
    def test_run_test_success(self, mock_make_host):
        """
        run_test() returns the status of a successful test run.
        """
        mock_host = Mock(spec=RemoteHost)
        mock_host.exec_command = Mock(return_value=0)
        mock_make_host.return_value = mock_host

        # Implicitly assert did not raise.
        res = run_test(self.test_config, self.god_config)
        self.assertEqual(res.status, 0)

    @patch("dsi.common.command_runner.make_workload_runner_host")
    def test_run_test_error(self, mock_make_host):
        """
        run_test() throws for a failed test run.
        """
        mock_host = Mock(spec=RemoteHost)
        mock_host.exec_command = Mock(return_value=1)
        mock_make_host.return_value = mock_host

        self.assertRaises(
            subprocess.CalledProcessError, lambda: run_test(self.test_config, self.god_config)
        )


class RunTestsTestCase(unittest.TestCase):
    """
    Unit Test for test_control.run_tests
    """

    def setUp(self):
        """Create a dict that looks like a ConfigDict object """
        self.config = {
            "bootstrap": {"canaries": "none"},
            "infrastructure_provisioning": {
                "tfvars": {"ssh_user": "test_ssh_user", "ssh_key_file": "mock/ssh/key/file"},
                "out": {
                    "mongod": [
                        {"public_ip": "53.1.1.1", "private_ip": "10.2.1.1"},
                        {"public_ip": "53.1.1.9", "private_ip": "10.2.1.9"},
                    ],
                    "mongos": [{"public_ip": "53.1.1.102", "private_ip": "10.2.1.102"}],
                    "configsvr": [{"public_ip": "53.1.1.53", "private_ip": "10.2.1.53"}],
                    "workload_client": [{"public_ip": "53.1.1.101", "private_ip": "10.2.1.200"}],
                },
            },
            "mongodb_setup": {
                "post_test": [
                    {"on_all_servers": {"retrieve_files": {"data/logs/": "./"}}},
                    {
                        "on_mongod": {
                            "retrieve_files": {"data/dbs/diagnostic.data": "./diagnostic.data"}
                        }
                    },
                    {
                        "on_configsvr": {
                            "retrieve_files": {"data/dbs/diagnostic.data": "./diagnostic.data"}
                        }
                    },
                ],
                "mongod_config_file": {"storage": {"engine": "wiredTiger"}},
            },
            "runtime": {"task_id": "STAY IN YOUR VEHICLE CITIZEN"},
            "test_control": {
                "task_name": "test_config",
                "numactl_prefix_for_workload_client": "numactl --interleave=all --cpunodebind=1",
                "reports_dir_basename": "reports",
                "perf_json": {"path": "perf.json"},
                "output_file": {
                    "mongoshell": "test_output.log",
                    "ycsb": "test_output.log",
                    "fio": "fio.json",
                    "iperf": "iperf.json",
                },
                "timeouts": {"no_output_ms": 5000},
                "run": [
                    {
                        "id": "benchRun",
                        "type": "shell",
                        "cmd": "$DSI_PATH/workloads/run_workloads.py -c workloads.yml",
                        "config_filename": "workloads.yml",
                        "output_files": ["mock_output0.txt", "mock_output0.txt"],
                        "workload_config": "mock_workload_config",
                    },
                    {
                        "id": "ycsb_load",
                        "type": "ycsb",
                        "cmd": "cd YCSB/ycsb-mongodb; ./bin/ycsb load mongodb -s -P "
                        + "workloads/workloadEvergreen -threads 8; sleep 1;",
                        "config_filename": "workloadEvergreen",
                        "workload_config": "mock_workload_config",
                        "skip_validate": True,
                    },
                    {
                        "id": "fio",
                        "type": "fio",
                        "cmd": "./fio-test.sh some_hostname",
                        "skip_validate": True,
                    },
                ],
                "jstests_dir": "./jstests/hooks",
                "post_test": [
                    {
                        "on_workload_client": {
                            "retrieve_files": {
                                "workloads/workload_timestamps.csv": "../workloads_timestamps.csv"
                            }
                        }
                    }
                ],
                'out': {'exit_codes': {}}
            }
        }

        # Do os.path.join here since fixture_file_path barfs if file not found.
        self.reports_container = os.path.join(FIXTURE_FILES.fixture_file_path(), 'container')
        self.reports_path = os.path.join(self.reports_container, 'reports_tests')

        mkdir_p(self.reports_path)

    def tearDown(self):
        shutil.rmtree(self.reports_container)
        if os.path.exists("test_control.out.yml"):
            os.remove("test_control.out.yml")

    @patch("os.walk")
    @patch("dsi.test_control.extract_hosts")
    @patch("shutil.copyfile")
    def test_copy_timeseries(self, mock_copyfile, mock_hosts, mock_walk):
        """ Test run RunTest.copy_timeseries. """

        mock_walk.return_value = []
        mock_hosts.return_value = []
        copy_timeseries(self.config)
        self.assertFalse(mock_copyfile.called)

        mock_walk.return_value = []
        mock_hosts.return_value = []
        copy_timeseries(self.config)
        self.assertFalse(mock_copyfile.called)

        mock_walk.reset_mock()
        mock_hosts.reset_mock()
        mock_copyfile.reset_mock()

        mock_walk.return_value = [("/dirpath", ("dirnames",), ())]

        dummy_host_info = host_utils.HostInfo(
            public_ip="10.0.0.0", category="mongod", offset=0
        )

        mock_hosts.return_value = [dummy_host_info]

        copy_timeseries(self.config)
        self.assertFalse(mock_copyfile.called)

        mock_walk.reset_mock()
        mock_hosts.reset_mock()
        mock_copyfile.reset_mock()
        mock_walk.return_value = [("/dirpath", ("dirnames",), ("baz",))]
        mock_hosts.return_value = [dummy_host_info]

        copy_timeseries(self.config)
        self.assertFalse(mock_copyfile.called)

        mock_walk.reset_mock()
        mock_hosts.reset_mock()
        mock_copyfile.reset_mock()
        mock_walk.return_value = [
            ("/dirpath", ("dirnames",), ("10.0.0.0--notmatching",)),
            ("/foo/bar", (), ("spam", "eggs")),
        ]
        mock_hosts.return_value = [dummy_host_info]

        copy_timeseries(self.config)
        self.assertFalse(mock_copyfile.called)

        mock_walk.reset_mock()
        mock_hosts.reset_mock()
        mock_copyfile.reset_mock()
        mock_walk.return_value = [("/dirpath", ("dirnames",), ("matching--10.0.0.0",))]
        mock_hosts.return_value = [dummy_host_info]

        copy_timeseries(self.config)
        self.assertTrue(
            mock_copyfile.called_with(
                "/dirpath/matching--10.0.0.0", "reports/mongod.0/matching-dirpath"
            )
        )

        mock_walk.reset_mock()
        mock_hosts.reset_mock()
        mock_copyfile.reset_mock()
        mock_walk.return_value = [
            ("/dirpath0", ("dirnames0",), ("file0--10.0.0.0",)),
            ("/dirpath1", ("dirnames1",), ("file1--10.0.0.1",)),
            ("/dirpath2", ("dirnames2",), ("file2--10.0.0.2",)),
        ]
        mock_hosts.return_value = [dummy_host_info, dummy_host_info]

        copy_timeseries(self.config)
        self.assertTrue(mock_copyfile.called)
        self.assertTrue(
            mock_copyfile.called_with(
                "/dirpath0/file0--10.0.0.0", "reports/mongod.0/matching-dirpath0"
            )
        )
        self.assertTrue(
            mock_copyfile.called_with(
                "/dirpath1/file1--10.0.0.1", "reports/mongod.1/matching-dirpath1"
            )
        )

    @patch("types.FrameType")
    def test_print_trace_mock_exception(self, mock_frame):
        """ Test test_control.print_trace with mock frame and mock exception"""
        with LogCapture() as log_capture:
            mock_frame.f_locals = {
                "value": "mock_value",
                "target": "on_mock_key",
                "command": "mock_command",
            }
            mock_trace = (
                (None, None, None, "mock_top_function"),
                (mock_frame, None, None, None),
                (mock_frame, None, None, "run_host_command"),
                (None, "mock_file", -1, "mock_bottom_function"),
            )
            mock_exception = Exception("mock_exception")
            print_trace(mock_trace, mock_exception)
            error_msg = "Exception originated in: mock_file:mock_bottom_function:-1\n"
            error_msg = error_msg + "Exception msg: mock_exception\nmock_top_function:\n    "
            error_msg = error_msg + "in task: on_mock_key\n        in command: mock_command"
        list_errors = list(log_capture.actual())
        self.assertEqual(error_msg, list_errors[0][2])

    # pylint: disable=unused-argument
    @patch("dsi.test_control.run_pre_post_commands")
    @patch("dsi.test_control.run_test")
    @patch("dsi.test_control.parse_test_results", return_value=["status", "CedarTest"])
    @patch("dsi.test_control.prepare_reports_dir")
    @patch("subprocess.check_call")
    @patch("dsi.test_control.print_perf_json")
    @patch("dsi.test_control.cedar")
    def test_pre_post_commands_ordering(
        self,
        mock_cedar,
        mock_copy_perf,
        mock_check_call,
        mock_prep_rep,
        mock_parse_results,
        mock_run_test,
        mock_pre_post,
    ):
        """Test that pre and post commands are called in the right order"""
        real_config_dict = ConfigDict("test_control")
        real_config_dict.raw = self.config
        run_tests(real_config_dict)

        # We will check that the calls to run_pre_post_commands() happened in expected order
        expected_args = [
            "pre_task",
            "pre_test",
            "post_test",
            "between_tests",
            "pre_test",
            "post_test",
            "between_tests",
            "pre_test",
            "post_test",
            "post_task",
        ]
        observed_args = [args[0][0] for args in mock_pre_post.call_args_list]
        self.assertEqual(expected_args, observed_args)

    # pylint: disable=unused-argument
    @patch("dsi.test_control.run_pre_post_commands")
    @patch("dsi.test_control.parse_test_results", return_value=("status", ["CedarTest"]))
    @patch("dsi.test_control.prepare_reports_dir")
    @patch("subprocess.check_call")
    @patch("dsi.test_control.print_perf_json")
    @patch("dsi.test_control.cedar")
    def test_run_test_exception(
        self,
        mock_cedar,
        mock_copy_perf,
        mock_check_call,
        mock_prep_rep,
        mock_parse_results,
        mock_pre_post,
    ):
        """
        Test CalledProcessErrors with cause run_tests return false but other errors will
        cause it to return true
        """
        real_config_dict = ConfigDict("test_control")
        real_config_dict.raw = self.config

        # pylint: disable=bad-continuation
        with patch(
            "dsi.test_control.run_test",
            side_effect=[subprocess.CalledProcessError(99, "failed-cmd"), 0, 0],
        ):
            utter_failure = run_tests(real_config_dict)
            self.assertFalse(utter_failure)
            mock_copy_perf.assert_called()

        with patch("dsi.test_control.run_test", side_effect=[ValueError(), 0, 0]):
            utter_failure = run_tests(real_config_dict)
            self.assertTrue(utter_failure)

    # pylint: disable=unused-argument
    @patch("dsi.test_control.run_pre_post_commands")
    @patch("dsi.test_control.run_test")
    @patch("dsi.test_control.parse_test_results", return_value=("status", ["CedarTest"]))
    @patch("dsi.test_control.prepare_reports_dir")
    @patch("subprocess.check_call")
    @patch("dsi.test_control.print_perf_json")
    @patch("dsi.common.cedar.send")
    def test_cedar_report(
        self,
        mock_cedar_send,
        mock_copy_perf,
        mock_check_call,
        mock_prep_rep,
        mock_parse_results,
        mock_run_test,
        mock_pre_post,
    ):
        """Test that cedar report is called the correct number of times"""
        real_config_dict = ConfigDict("test_control")
        real_config_dict.raw = self.config
        run_tests(real_config_dict)

        run_tests(real_config_dict)

        mock_cedar_send.assert_called()


if __name__ == "__main__":
    unittest.main()
