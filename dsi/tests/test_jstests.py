"""Tests for dsi/common/config.py"""

import unittest

from mock import patch, call

from dsi.common import jstests


class JSTestsTestCase(unittest.TestCase):
    """Unit tests for jstests library."""

    def setUp(self):
        """Create a dict that looks like a ConfigDict object """
        self.config = {
            "mongodb_setup": {"validate": {"standalone": ["10.10.10.10:27017"]}},
            "test_control": {"jstests_dir": "./jstests/hooks", "task_name": "test_config"},
        }

    @patch("dsi.common.jstests.jstest_one_host")
    def test_validate_no_jstests_dir(self, mock_jstest_one_host):
        """
        Test the run_validate script when there are no jstests_dir.

        When jstests_dir is not set, there should be no calls to jstest_one_host.
        """
        # Clear the jstests_dir setting
        del self.config["test_control"]["jstests_dir"]
        jstests.run_validate(self.config, "UnitTest")
        mock_jstest_one_host.assert_not_called()

    @patch("dsi.common.jstests.jstest_one_host")
    @patch("dsi.common.jstests._remote_exists")
    def test_validate_standalone(self, mock_remote_exists, mock_jstest_one_host):
        """
        Test the run_validate script when called on a list of standalones.

        There should be one validate-indexes-and-collections call to jstest_one_host.
        """
        mock_remote_exists.return_value = True
        jstests.run_validate(self.config, "UnitTest")
        self.assertEqual(1, mock_jstest_one_host.call_count)
        mock_jstest_one_host.assert_has_calls(
            [
                call(
                    self.config,
                    "10.10.10.10:27017",
                    "reports",
                    "UnitTest",
                    "validate-indexes-and-collections",
                )
            ]
        )

    @patch("dsi.common.jstests.jstest_one_host")
    @patch("dsi.common.jstests._remote_exists")
    def test_validate_primaries(self, mock_remote_exists, mock_jstest_one_host):
        """
        Test the run_validate script when called on a list of primaries.

        There should be a validate-indexes-and-collections call and a db-hash-check call to
        jstest_one_host for both primaries, for 4 total calls.

        """
        mock_remote_exists.return_value = True
        self.config["mongodb_setup"]["validate"] = {
            "primaries": ["10.10.10.10:27017", "10.10.10.11:27017"]
        }

        jstests.run_validate(self.config, "UnitTest")
        self.assertEqual(4, mock_jstest_one_host.call_count)

        # Because of the use of threading, the order of the calls between the primaries is
        # non-determinanistic, and we have to set any_order to True below.
        mock_jstest_one_host.assert_has_calls(
            [
                call(
                    self.config,
                    "10.10.10.10:27017",
                    "reports",
                    "UnitTest",
                    "validate-indexes-and-collections",
                ),
                call(self.config, "10.10.10.10:27017", "reports", "UnitTest", "db-hash-check"),
                call(
                    self.config,
                    "10.10.10.11:27017",
                    "reports",
                    "UnitTest",
                    "validate-indexes-and-collections",
                ),
                call(self.config, "10.10.10.11:27017", "reports", "UnitTest", "db-hash-check"),
            ],
            any_order=True,
        )

    @patch("dsi.common.jstests.jstest_one_host")
    @patch("dsi.common.jstests._remote_exists")
    def test_validate_jstests_not_found(self, mock_remote_exists, mock_jstest_one_host):
        """
        Test the run_validate script when jstests_dir is not found.

        There should be no calls to jstest_one_host.
        """
        mock_remote_exists.return_value = False
        self.config["mongodb_setup"]["validate"] = {
            "primaries": ["10.10.10.10:27017", "10.10.10.11:27017"]
        }
        jstests.run_validate(self.config, "UnitTest")
        mock_jstest_one_host.assert_not_called()
