"""Tests for dsi/common/download_mongodb.py"""
# pylint: disable=protected-access

import os
import string
import unittest

import mock
from mock import patch, Mock
from six.moves import range

from dsi.common.download_mongodb import DownloadMongodb, temp_file
from dsi.common.models.host_info import HostInfo


class DownloadMongodbTestCase(unittest.TestCase):
    """Unit tests for DownloadMongodb library."""

    def setUp(self):
        """Init a DownloadMongodb object"""
        self.config = {
            "infrastructure_provisioning": {
                "tfvars": {"ssh_user": "ec2-user", "ssh_key_file": "~/.ssh/user-aws-key.pem"},
                "out": {
                    "mongod": [
                        {"public_ip": "10.2.3.4", "private_ip": "10.0.0.1"},
                        {"public_ip": "10.2.3.5", "private_ip": "10.0.0.2"},
                        {"public_ip": "10.2.3.6", "private_ip": "10.0.0.3"},
                        {"public_ip": "10.2.3.7", "private_ip": "10.0.0.4"},
                        {"public_ip": "10.2.3.8", "private_ip": "10.0.0.5"},
                    ],
                    "mongos": [
                        {"public_ip": "10.2.3.9", "private_ip": "10.0.0.6"},
                        {"public_ip": "10.2.3.10", "private_ip": "10.0.0.7"},
                        {"public_ip": "10.2.3.11", "private_ip": "10.0.0.8"},
                    ],
                    "configsvr": [
                        {"public_ip": "10.2.3.12", "private_ip": "10.0.0.9"},
                        {"public_ip": "10.2.3.13", "private_ip": "10.0.0.10"},
                        {"public_ip": "10.2.3.14", "private_ip": "10.0.0.11"},
                    ],
                    "workload_client": [{"public_ip": "10.2.3.15", "private_ip": "10.0.0.12"}],
                },
            },
            "mongodb_setup": {"mongodb_binary_archive": "http://foo.tgz"},
        }
        self.config_no_binary = {
            "infrastructure_provisioning": {
                "tfvars": {"ssh_user": "ec2-user", "ssh_key_file": "../../aws.pem"},
                "out": {
                    "mongod": [{"public_ip": "10.2.3.4", "private_ip": "10.0.0.1"}],
                    "workload_client": [{"public_ip": "10.2.3.15", "private_ip": "10.0.0.12"}],
                },
            },
            "runtime": {},
            "mongodb_setup": {"mongo_dir": "/tmp"},
        }
        # self.downloader = None

    @patch("dsi.common.download_mongodb.host_utils.extract_hosts")
    @patch("dsi.common.download_mongodb.host_factory.make_host")
    def test_basic_use(self, mock_remote_host, mock_extract_hosts):
        """
        Init DownloadMongodb with ConfigDict structure with
        mongodb_binary specified in mongodb_setup.
        """

        mock_extract_hosts.return_value = [
            HostInfo(public_ip="dummy_ip", offset=i) for i in range(10)
        ]

        DownloadMongodb(self.config)

        calls = [mock.call(HostInfo(public_ip="dummy_ip", offset=i)) for i in range(10)]
        mock_remote_host.assert_has_calls(calls=calls, any_order=True)

    @patch("dsi.common.download_mongodb.host_factory.make_host")
    def test_mongodb_binary(self, mock_make_host):
        """
        Init DownloadMongodb with ConfigDict structure with
        mongodb_binary specified in bootstrap.
        """
        _ = mock_make_host

        mongodb_url = "http://bar.tgz"
        self.config["mongodb_setup"]["mongodb_binary_archive"] = mongodb_url

        downloader = DownloadMongodb(self.config)

        self.assertEqual(downloader.mongodb_binary_archive, mongodb_url)

    def test_temp_file(self):
        """ Test temp_file() to ensure it makes properly named random files """
        mongodb_binary_archive = self.config["mongodb_setup"]["mongodb_binary_archive"]

        def _test_temp_file(test, filename, value, uuid_len=36):
            test.assertTrue(filename.endswith(value))
            test.assertTrue(len(filename) == len(value) + uuid_len)

        _test_temp_file(self, temp_file(), "mongodb.tgz")
        _test_temp_file(self, temp_file(path=mongodb_binary_archive), "foo.tgz")
        _test_temp_file(
            self, temp_file(path=mongodb_binary_archive + "?test=ing"), "foo.tgztesting"
        )
        path = mongodb_binary_archive + "?test=ing&second=param"
        _test_temp_file(self, temp_file(path=path), "foo.tgztestingsecondparam")

        # the '/' chars wouldn't have survived the basename, which is why they are removed
        path = "".join(sorted(string.printable.split())).replace("/", "")
        _test_temp_file(
            self,
            temp_file(path=path),
            (string.digits + string.ascii_letters + "-._").replace("/", ""),
        )

        # test sanitize allows everything
        path = mongodb_binary_archive + "?test=ing"
        _test_temp_file(self, temp_file(path=path, sanitize=lambda x: x), "foo.tgz?test=ing")

    @patch("dsi.common.download_mongodb.temp_file")
    @patch("dsi.common.download_mongodb.host_factory.make_host")
    def test_remove_temp_file(self, mock_make_host, mock_temp_file):
        """test that mongo_dir and tmp_file removal."""
        # mongodb_binary_archive = self.config['mongodb_setup']['mongodb_binary_archive']
        _ = mock_make_host
        tmp_file = "/tmp/foo.tgz"
        mock_temp_file.return_value = os.path.basename(tmp_file)
        downloader = DownloadMongodb(self.config_no_binary)
        mock_host = Mock()
        mock_host.host.return_value = "host"
        commands = downloader._remote_commands(mock_host)
        rm_mongo_dir = ["rm", "-rf", "/tmp"]
        rm_tmp_file = ["rm", "-f", tmp_file]
        self.assertTrue(rm_mongo_dir in commands)
        self.assertTrue(rm_tmp_file in commands)
        self.assertTrue(commands.index(rm_mongo_dir) < commands.index(rm_tmp_file))


if __name__ == "__main__":
    unittest.main()
