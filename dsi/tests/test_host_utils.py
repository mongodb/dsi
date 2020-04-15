"""Tests for dsi/common/host_utils.py"""

import copy
import os
import shutil
import socket
import time
import unittest
from datetime import datetime

from mock import patch, MagicMock, call
from six.moves import range

from dsi.common import host_utils
from dsi.common import whereami
from dsi.common.config import ConfigDict
from test_lib.fixture_files import FixtureFiles

FIXTURE_FILES = FixtureFiles()


class HostUtilsTestCase(unittest.TestCase):
    """ Unit Tests for Host Utils library """

    def _delete_fixtures(self):
        """ delete FIXTURE_FILES path and set filename attribute """
        local_host_path = os.path.join(FIXTURE_FILES.fixture_file_path(), "fixtures")
        self.filename = os.path.join(local_host_path, "file")
        shutil.rmtree(os.path.dirname(self.filename), ignore_errors=True)

    def setUp(self):
        """ Init a ConfigDict object and load the configuration files from docs/config-specs/ """
        self.config = ConfigDict("mongodb_setup", whereami.dsi_repo_path("docs", "config-specs"))
        self.config.load()
        self.parent_dir = os.path.join(os.path.expanduser("~"), "checkout_repos_test")

        self._delete_fixtures()

    def tearDown(self):
        self._delete_fixtures()

    def test_never_timeout(self):
        """ test never_timeout"""
        self.assertFalse(host_utils.never_timeout())
        self.assertFalse(host_utils.never_timeout())

    def test_check_timed_out(self):
        """ test check_timed_out"""
        start = datetime.now()
        self.assertFalse(host_utils.check_timed_out(start, 50))
        time.sleep(51 / 1000.0)
        self.assertTrue(host_utils.check_timed_out(start, 50))

    def test_create_timer(self):
        """ test create_timer """
        start = datetime.now()
        self.assertEqual(host_utils.create_timer(start, None), host_utils.never_timeout)
        with patch("dsi.common.host_utils.partial") as mock_partial:
            self.assertTrue(host_utils.create_timer(start, 50))
            mock_partial.assert_called_once_with(host_utils.check_timed_out, start, 50)

    def test_extract_hosts(self):
        """ Test extract hosts using config info """

        default_host_info = host_utils.HostInfo(
            public_ip=None,
            # These are the user and key files used by this test.
            ssh_user="ec2-user",
            ssh_key_file=os.path.join(os.path.expanduser("~"), ".ssh", "linustorvalds.pem"),
            category=None,
            offset=-1,
        )

        def customize_host_info(new_ip, new_category, offset):
            new_host_info = copy.copy(default_host_info)
            new_host_info.public_ip = new_ip
            new_host_info.category = new_category
            new_host_info.offset = offset
            return new_host_info

        mongods = [customize_host_info("53.1.1.{}".format(i + 1), "mongod", i) for i in range(0, 9)]
        configsvrs = [
            customize_host_info("53.1.1.{}".format(i + 51), "configsvr", i) for i in range(0, 3)
        ]
        mongos = [
            customize_host_info("53.1.1.{}".format(i + 100), "mongos", i) for i in range(0, 3)
        ]
        workload_clients = [customize_host_info("53.1.1.101", "workload_client", 0)]
        localhost = [host_utils.HostInfo(public_ip="localhost", category="localhost", offset=0)]

        self.assertEqual(host_utils.extract_hosts("localhost", self.config), localhost)
        self.assertEqual(host_utils.extract_hosts("workload_client", self.config), workload_clients)
        self.assertEqual(host_utils.extract_hosts("mongod", self.config), mongods)
        self.assertEqual(host_utils.extract_hosts("mongos", self.config), mongos)
        self.assertEqual(host_utils.extract_hosts("configsvr", self.config), configsvrs)
        self.assertEqual(
            host_utils.extract_hosts("all_servers", self.config), mongods + mongos + configsvrs
        )
        self.assertEqual(
            host_utils.extract_hosts("all_hosts", self.config),
            mongods + mongos + configsvrs + workload_clients,
        )

    def test_stream_lines_timeout_on_first_line(self):
        """ Test stream_lines """
        source = [1]
        destination = MagicMock(name="destination")
        destination.write.side_effect = socket.timeout("args")
        any_lines = host_utils.stream_lines(source, destination)
        self.assertEqual(False, any_lines)
        destination.write.assert_has_calls([call(1)])

    def test_stream_lines_timeout_on_third_line(self):
        destination = MagicMock(name="destination")
        destination.write.side_effect = ["first", "second", socket.timeout("args"), "third"]

        source = [1, 2, 3]
        any_lines = host_utils.stream_lines(source, destination)
        self.assertEqual(True, any_lines)

        destination.write.assert_has_calls([call(1), call(2), call(3)])


if __name__ == "__main__":
    unittest.main()
