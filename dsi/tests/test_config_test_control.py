""" Test config_test_control.py """


import logging
import os
import unittest

from mock import Mock, patch
from testfixtures import LogCapture

from dsi import test_control
from dsi.common.config import ConfigDict
from dsi.common.remote_host import RemoteHost
from test_lib.fixture_files import FixtureFiles

FIXTURE_FILES = FixtureFiles()


class TestConfigTestControl(unittest.TestCase):
    """ Test config_test_control.py"""

    def setUp(self):
        """
        Setup basic environment
        """
        # Mocking `ConfigDict.assert_valid_ids` because it enforces structural constraints on yaml
        # files that aren't necessary here.
        with patch("dsi.common.config.ConfigDict.assert_valid_ids") as mock_assert_valid_ids:
            self.config = ConfigDict(
                "test_control", FIXTURE_FILES.fixture_file_path("config_test_control")
            )
            self.config.load()
            mock_assert_valid_ids.assert_called_once()

    def tearDown(self):
        file_name = FIXTURE_FILES.fixture_file_path("workloads.yml")
        if os.path.exists(file_name):
            os.remove(file_name)

    def test_benchrun_workload_config(self):
        """
        Test that generate_config_files works with a benchrun workload
        """
        test = self.config["test_control"]["run"][0]
        mock_host = Mock(spec=RemoteHost)
        test_control.generate_config_file(test, FIXTURE_FILES.fixture_file_path(), mock_host)
        self.assertEqual(
            FIXTURE_FILES.load_yaml_file("config_test_control", "workloads.yml"),
            FIXTURE_FILES.load_yaml_file("config_test_control", "workloads.benchrun.yml.ok"),
            "workloads.yml doesn't match expected for test_control.yml",
        )
        mock_host.upload_file.assert_called_once_with(
            FIXTURE_FILES.fixture_file_path(test["config_filename"]), test["config_filename"]
        )

    def test_ycsb_workload_config(self):
        """
        Test that generate_config_files works with a ycsb run
        """
        test = self.config["test_control"]["run"][1]
        mock_host = Mock(spec=RemoteHost)
        test_control.generate_config_file(
            test, FIXTURE_FILES.fixture_file_path("config_test_control"), mock_host
        )
        self.assertEqual(
            FIXTURE_FILES.load_yaml_file("config_test_control", "workloadEvergreen"),
            FIXTURE_FILES.load_yaml_file("config_test_control", "workloadEvergreen.ok"),
            "workloadEvergreen doesn't match expected for test_control.yml",
        )
        mock_host.upload_file.assert_called_once_with(
            FIXTURE_FILES.fixture_file_path("config_test_control", test["config_filename"]),
            test["config_filename"],
        )

    @patch("dsi.test_control.open")
    def test_generate_config_no_config(self, mock_open):
        """
        Test that generate_config_file doesn't create a workload file and logs the correct message
        if there is no config file
        """
        test = self.config["test_control"]["run"][2]
        mock_host = Mock(spec=RemoteHost)
        with LogCapture(level=logging.WARNING) as warning:
            test_control.generate_config_file(test, FIXTURE_FILES.repo_root_file_path(), mock_host)
        warning.check(("dsi.test_control", "WARNING", "No workload config in test control"))
        mock_open.assert_not_called()
        mock_host.upload_file.assert_not_called()


if __name__ == "__main__":
    unittest.main()
