"""Tests for dsi/remote_host.py"""


import collections
import os
import stat
import unittest

import mock
import paramiko
from mock import patch, call, ANY, MagicMock, Mock

from dsi.common import command_runner
from dsi.common import host_utils
from dsi.common import remote_host
from dsi.common import remote_ssh_host
from dsi.common import whereami

FakeStat = collections.namedtuple("FakeStat", "st_mode")


class RemoteHostTestCase(unittest.TestCase):
    """ Unit Test for RemoteHost library """

    @patch("dsi.common.remote_host.RemoteHost.connected_ssh")
    def test_upload_files_dir(self, mock_connected_ssh):
        """We can upload directories of files"""

        ssh = mock.MagicMock(name="ssh")
        ftp = mock.MagicMock(name="ftp")
        channel = mock.MagicMock(name="channel")
        ssh.exec_command.return_value = channel, channel, channel

        mock_connected_ssh.return_value = (ssh, ftp)

        remote = remote_ssh_host.RemoteSSHHost(hostname=None, username=None, pem_file=None)
        remote._perform_exec = mock.MagicMock(name="_perform_exec")
        remote._perform_exec.return_value = 0

        local_path = whereami.dsi_repo_path("testscripts")
        remote_path = "/foo/bar"

        remote.upload_file(local_path, remote_path)

        ssh.exec_command.assert_has_calls(
            [
                call("mkdir -p /foo/bar", get_pty=False),
                call("tar xf /foo/bar.tar -C /foo/bar", get_pty=False),
                call("rm /foo/bar.tar", get_pty=False),
            ],
            any_order=False,
        )

        ftp.assert_has_calls(
            [call.put(ANY, "/foo/bar.tar"), call.chmod("/foo/bar.tar", ANY)], any_order=False
        )

    @patch("dsi.common.remote_host.RemoteHost.connected_ssh")
    def test_upload_single_file(self, mock_connected_ssh):
        """We can upload a single file"""
        ssh = mock.MagicMock(name="ssh")
        ftp = mock.MagicMock(name="ftp")
        mock_connected_ssh.return_value = (ssh, ftp)

        remote = remote_host.RemoteHost(hostname=None, username=None, pem_file=None)

        local_path = whereami.dsi_repo_path("dsi", "tests", "test_remote_host.py")
        remote_path = "/foo/bar/idk.py"

        remote.upload_file(local_path, remote_path)

        ssh.assert_not_called()

        ftp.assert_has_calls(
            [call.put(ANY, "/foo/bar/idk.py"), call.chmod("/foo/bar/idk.py", ANY)], any_order=False
        )

    @patch("paramiko.SSHClient")
    def test__upload_files_host_ex(self, ssh_client):
        """ Test run command map exception """

        with self.assertRaisesRegex(host_utils.HostException, r"wrapped exception"):
            remote = remote_ssh_host.RemoteSSHHost("53.1.1.1", "ssh_user", "ssh_key_file")
            command = {"upload_files": [{"target": "remote_path", "source": "."}]}
            remote.exec_command = MagicMock(name="exec_command")
            remote.exec_command.return_value = 0

            remote._upload_dir = MagicMock(name="_upload_single_file")
            remote._upload_dir.side_effect = host_utils.HostException("wrapped exception")

            remote._upload_single_file = MagicMock(name="_upload_single_file")
            remote._upload_single_file.side_effect = host_utils.HostException("wrapped exception")
            command_runner._run_host_command_map(remote, command, "test_id")

    @patch("paramiko.SSHClient")
    def test__upload_files_wrapped_ex(self, ssh_client):
        """ Test run command map exception """

        with self.assertRaisesRegex(host_utils.HostException, r"'mkdir', '-p', 'remote_path'"):
            remote = remote_ssh_host.RemoteSSHHost("53.1.1.1", "ssh_user", "ssh_key_file")
            command = {"upload_files": [{"target": "remote_path", "source": "."}]}
            remote.exec_command = MagicMock(name="exec_command")
            remote.exec_command.return_value = 1

            remote._upload_single_file = MagicMock(name="_upload_single_file")
            remote._upload_single_file.side_effect = paramiko.ssh_exception.SSHException(
                "wrapped exception"
            )
            command_runner._run_host_command_map(remote, command, "test_id")

    @patch("paramiko.SSHClient")
    def test_remote_host_isdir(self, mock_ssh):
        """ Test remote_isdir """

        remote = remote_ssh_host.RemoteSSHHost("53.1.1.1", "ssh_user", "ssh_key_file")
        remote.ftp.stat.return_value = FakeStat(st_mode=stat.S_IFDIR)
        isdir = remote.remote_isdir("/true")

        self.assertTrue(isdir, "expected true")
        remote.ftp.stat.assert_called_with("/true")

        remote.ftp.stat.return_value = FakeStat(st_mode=stat.S_IFLNK)
        isdir = remote.remote_isdir("/false")

        self.assertFalse(isdir, "expected False")
        remote.ftp.stat.assert_called_with("/false")

        remote.ftp = mock_ssh
        mock_ssh.stat.side_effect = os.error(2, "No such file or directory:")
        isdir = remote.remote_isdir("/exception")

        self.assertFalse(isdir, "expected False")
        remote.ftp.stat.assert_called_with("/exception")

    @patch("paramiko.SSHClient")
    def test_exists_os_error(self, mock_ssh):
        """ Test run RemoteHost.exists """

        remote = remote_host.RemoteHost("53.1.1.1", "ssh_user", "ssh_key_file")
        exists = remote.remote_exists("true_path")

        self.assertTrue(exists, "expected true")
        remote.ftp.stat.assert_called_with("true_path")

        remote.ftp = mock_ssh
        mock_ssh.stat.side_effect = os.error(2, "No such file or directory:")
        exists = remote.remote_exists("os_exception_path")

        self.assertFalse(exists, "expected False")
        remote.ftp.stat.assert_called_with("os_exception_path")

    @patch("paramiko.SSHClient")
    def test_exists_io_error(self, mock_ssh):
        """ Test run RemoteHost.exists """

        remote = remote_host.RemoteHost("53.1.1.1", "ssh_user", "ssh_key_file")
        exists = remote.remote_exists("true_path")

        self.assertTrue(exists, "expected true")
        remote.ftp.stat.assert_called_with("true_path")

        remote.ftp = mock_ssh
        mock_ssh.stat.side_effect = IOError("IOError")
        exists = remote.remote_exists("io_exception_path")

        self.assertFalse(exists, "expected False")
        remote.ftp.stat.assert_called_with("io_exception_path")

    @patch("paramiko.SSHClient")
    def test_exists_paramiko_error(self, mock_ssh):
        """ Test run RemoteHost.exists """

        remote = remote_host.RemoteHost("53.1.1.1", "ssh_user", "ssh_key_file")
        exists = remote.remote_exists("true_path")

        self.assertTrue(exists, "expected true")
        remote.ftp.stat.assert_called_with("true_path")

        remote.ftp = mock_ssh
        mock_ssh.stat.side_effect = paramiko.SFTPError("paramiko.SFTPError")
        exists = remote.remote_exists("paramiko_exception_path")

        self.assertFalse(exists, "expected False")
        remote.ftp.stat.assert_called_with("paramiko_exception_path")

    @patch("paramiko.SSHClient")
    @patch("os.makedirs")
    @patch("os.path.exists")
    def test__retrieve_file(self, mock_exists, mock_makedirs, mock_ssh):
        """ Test run RemoteHost.exists """

        mock_exists.return_value = True
        remote = remote_host.RemoteHost("53.1.1.1", "ssh_user", "ssh_key_file")
        remote._retrieve_file("remote_file", "reports/local_file")

        remote.ftp.get.assert_called_with("remote_file", "reports/local_file")
        mock_makedirs.assert_not_called()

        mock_exists.return_value = True
        remote = remote_host.RemoteHost("53.1.1.1", "ssh_user", "ssh_key_file")
        remote._retrieve_file("remote_file", "reports/mongod.0/local_file")

        remote.ftp.get.assert_called_with("remote_file", "reports/mongod.0/local_file")
        mock_makedirs.assert_not_called()

        mock_exists.return_value = True
        remote = remote_host.RemoteHost("53.1.1.1", "ssh_user", "ssh_key_file")
        remote._retrieve_file("remote_file", "reports/../local_file")

        remote.ftp.get.assert_called_with("remote_file", "local_file")
        mock_makedirs.assert_not_called()

        mock_exists.return_value = False
        remote = remote_host.RemoteHost("53.1.1.1", "ssh_user", "ssh_key_file")
        remote._retrieve_file("remote_file", "reports/local_file")

        remote.ftp.get.assert_called_with("remote_file", "reports/local_file")
        mock_makedirs.assert_called_with("reports")

    @patch("paramiko.SSHClient")
    def test_retrieve_file_for_files(self, mock_ssh):
        """ Test run RemoteHost.exists """

        # remote path does not exist
        remote = remote_host.RemoteHost("53.1.1.1", "ssh_user", "ssh_key_file")
        remote.remote_exists = Mock()
        remote.remote_isdir = Mock()
        remote._retrieve_file = Mock()
        remote.ftp.listdir = Mock()

        remote.remote_exists.return_value = False
        remote.retrieve_path("remote_file", "reports/local_file")

        remote.remote_isdir.assert_not_called()

        # remote path is a single file
        remote.remote_exists.reset_mock()
        remote.remote_isdir.reset_mock()
        remote._retrieve_file.reset_mock()
        remote.ftp.listdir.reset_mock()

        remote.remote_exists.return_value = True
        remote.remote_isdir.return_value = False
        remote.retrieve_path("remote_file", "reports/local_file")
        remote._retrieve_file.assert_called_with("remote_file", "reports/local_file")

        # remote path is a directory containing a single file
        remote.remote_exists.reset_mock()
        remote.remote_isdir.reset_mock()
        remote._retrieve_file.reset_mock()
        remote.ftp.listdir.reset_mock()

        remote.remote_exists.return_value = True
        isdir_map = {"remote_dir": True}
        remote.remote_isdir.side_effect = lambda name: isdir_map.get(name, False)
        remote.ftp.listdir.return_value = ["mongod.log"]

        remote.retrieve_path("remote_dir", "reports/local_dir")

        remote.ftp.listdir.assert_called_with("remote_dir")
        remote._retrieve_file.assert_called_with(
            "remote_dir/mongod.log", "reports/local_dir/mongod.log"
        )

        # remote path is a directory, with multiple files
        remote.remote_exists.reset_mock()
        remote.remote_isdir.reset_mock()
        remote._retrieve_file.reset_mock()
        remote.ftp.listdir.reset_mock()

        remote.remote_exists.return_value = True
        isdir_map = {"remote_dir": True}
        remote.remote_isdir.side_effect = lambda name: isdir_map.get(name, False)
        remote.ftp.listdir.return_value = [
            "mongod.log",
            "metrics.2017-04-27T09-14-33Z-00000",
            "metrics.interim",
        ]

        remote.retrieve_path("remote_dir", "reports/local_dir")

        remote.ftp.listdir.assert_called_with("remote_dir")
        self.assertTrue(
            remote._retrieve_file.mock_calls
            == [
                mock.call("remote_dir/mongod.log", "reports/local_dir/mongod.log"),
                mock.call(
                    "remote_dir/metrics.2017-04-27T09-14-33Z-00000",
                    "reports/local_dir/metrics.2017-04-27T09-14-33Z-00000",
                ),
                mock.call("remote_dir/metrics.interim", "reports/local_dir/metrics.interim"),
            ]
        )

    @patch("paramiko.SSHClient")
    def test_retrieve_file_with_dirs(self, mock_ssh):
        """ Test run RemoteHost.exists """

        remote = remote_host.RemoteHost("53.1.1.1", "ssh_user", "ssh_key_file")
        remote.remote_exists = Mock()
        remote.remote_isdir = Mock()
        remote._retrieve_file = Mock()
        remote.ftp.listdir = Mock()

        # remote path is a directory, with 1 directory with a single empty dir
        remote.remote_exists.reset_mock()
        remote.remote_isdir.reset_mock()
        remote._retrieve_file.reset_mock()
        remote.ftp.listdir.reset_mock()

        remote.remote_exists.return_value = True
        isdir_map = {"remote_dir": True, "remote_dir/data": True}
        remote.remote_isdir.side_effect = lambda name: isdir_map.get(name, False)

        listdir_map = {"remote_dir": ["data"]}
        remote.ftp.listdir.side_effect = lambda name: listdir_map.get(name, [])

        remote.retrieve_path("remote_dir", "reports/local_dir")
        self.assertTrue(
            remote.ftp.listdir.mock_calls == [mock.call("remote_dir"), mock.call("remote_dir/data")]
        )
        # remote.ftp.listdir.assert_called_with('remote_dir')
        remote._retrieve_file.assert_not_called()

        # remote path is a directory, with 1 directory (with a single file)
        remote.remote_exists.reset_mock()
        remote.remote_isdir.reset_mock()
        remote._retrieve_file.reset_mock()
        remote.ftp.listdir.reset_mock()

        remote.remote_exists.return_value = True
        isdir_map = {"remote_dir": True, "remote_dir/data": True}
        remote.remote_isdir.side_effect = lambda name: isdir_map.get(name, False)

        listdir_map = {"remote_dir": ["data"], "remote_dir/data": ["metrics.interim"]}
        remote.ftp.listdir.side_effect = lambda name: listdir_map.get(name, [])

        remote.retrieve_path("remote_dir", "reports/local_dir")
        self.assertTrue(
            remote.ftp.listdir.mock_calls == [mock.call("remote_dir"), mock.call("remote_dir/data")]
        )
        # remote.ftp.listdir.assert_called_with('remote_dir')
        remote._retrieve_file.assert_called_with(
            "remote_dir/data/metrics.interim", "reports/local_dir/data/metrics.interim"
        )

        # remote path is a directory, with multiple files
        remote.remote_exists.reset_mock()
        remote.remote_isdir.reset_mock()
        remote._retrieve_file.reset_mock()
        remote.ftp.listdir.reset_mock()

        remote.remote_exists.return_value = True
        isdir_map = {"remote_dir": True}
        remote.remote_isdir.side_effect = lambda name: isdir_map.get(name, False)

        listdir_map = {"remote_dir": ["data", "logs"]}
        remote.ftp.listdir.side_effect = lambda name: listdir_map.get(name, [])

        remote.retrieve_path("remote_dir", "reports/local_dir")
        remote.ftp.listdir.assert_called_with("remote_dir")
        self.assertTrue(
            remote._retrieve_file.mock_calls
            == [
                mock.call("remote_dir/data", "reports/local_dir/data"),
                mock.call("remote_dir/logs", "reports/local_dir/logs"),
            ]
        )

    @patch("paramiko.SSHClient")
    def test_retrieve_files_and_dirs(self, mock_ssh):
        """ Test run RemoteHost.exists """

        remote = remote_host.RemoteHost("53.1.1.1", "ssh_user", "ssh_key_file")
        remote.remote_exists = Mock()
        remote.remote_isdir = Mock()
        remote._retrieve_file = Mock()
        remote.ftp.listdir = Mock()

        # remote path is a directory, with files and directories
        remote.remote_exists.reset_mock()
        remote.remote_isdir.reset_mock()
        remote._retrieve_file.reset_mock()
        remote.ftp.listdir.reset_mock()

        remote.remote_exists.return_value = True

        isdir_map = {
            "remote_dir": True,
            "remote_dir/data": True,
            "remote_dir/empty": True,
            "remote_dir/logs": True,
        }

        remote.remote_isdir.side_effect = lambda name: isdir_map.get(name, False)

        listdir_map = {
            "remote_dir": ["data", "empty", "file", "logs"],
            "remote_dir/data": ["metrics.interim", "metrics.2017-04-27T09-14-33Z-00000"],
            "remote_dir/logs": ["mongod.log"],
        }
        remote.ftp.listdir.side_effect = lambda name: listdir_map.get(name, [])

        remote.retrieve_path("remote_dir", "reports/local_dir")

        # note empty is not here so it was not called
        self.assertTrue(
            remote._retrieve_file.mock_calls
            == [
                mock.call(
                    "remote_dir/data/metrics.interim", "reports/local_dir/data/metrics.interim"
                ),
                mock.call(
                    "remote_dir/data/metrics.2017-04-27T09-14-33Z-00000",
                    "reports/local_dir/data/metrics.2017-04-27T09-14-33Z-00000",
                ),
                mock.call("remote_dir/file", "reports/local_dir/file"),
                mock.call("remote_dir/logs/mongod.log", "reports/local_dir/logs/mongod.log"),
            ]
        )


if __name__ == "__main__":
    unittest.main()
